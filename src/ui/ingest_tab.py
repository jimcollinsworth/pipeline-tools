import os
import gradio as gr
import pandas as pd
from pathlib import Path
from src.core.config import get_settings, update_last_entry, sanitize_identifier
from src.ingest.scanner import scan_directory
from src.db.manager import DBManager
from src.controllers.ingest_controller import IngestController

def render_ingest_tab(tab=None):
    settings = get_settings()
    default_path = settings.default_ingest_dir or str(Path.cwd())
    initial_file_choices = IngestController.get_file_suggestions()
    initial_file_val = initial_file_choices[0] if initial_file_choices else ""

    with gr.Column(scale=1):
        gr.Markdown("### 📂 Ingestion & Document Scanner")

        ingest_mode_radio = gr.Radio(
            choices=["📁 Directory Multi-Asset Scanner", "📄 Single Row-Oriented File (CSV)"],
            value="📁 Directory Multi-Asset Scanner",
            label="Ingestion Mode"
        )

        # Mode 1: Directory Multi-Asset Scanner Controls
        with gr.Group(visible=True) as directory_controls_group:
            with gr.Row():
                dir_input = gr.Dropdown(
                    label="Source Directory Path (Type or select from tree)",
                    choices=IngestController.get_directory_suggestions(default_path),
                    value=default_path,
                    allow_custom_value=True,
                    filterable=True,
                    scale=4
                )
                scan_dir_btn = gr.Button("🔍 Scan Directory", variant="primary", scale=1)

            with gr.Row():
                modality_filters = gr.CheckboxGroup(
                    label="Include Modalities",
                    choices=["docs", "images", "audio", "video", "other"],
                    value=["docs", "images", "audio", "video"],
                    scale=3
                )
                recursive_check = gr.Checkbox(label="Recursive Subdirectories", value=True, scale=1)

        # Mode 2: Single Row-Oriented CSV File Controls
        with gr.Group(visible=False) as single_file_controls_group:
            with gr.Row():
                file_input = gr.Dropdown(
                    label="Source CSV / TSV File Path (Type or select file)",
                    choices=initial_file_choices,
                    value=initial_file_val,
                    allow_custom_value=True,
                    filterable=True,
                    scale=4
                )
                scan_file_btn = gr.Button("🔍 Inspect CSV File", variant="primary", scale=1)

            with gr.Row():
                primary_text_col_dropdown = gr.Dropdown(
                    label="Primary Text / Content Column",
                    choices=["(Auto / All Columns)"],
                    value="(Auto / All Columns)",
                    allow_custom_value=True,
                    scale=3,
                    info="Selected column populates {content}. All other CSV columns remain accessible via {col_name} placeholders."
                )

        summary_markdown = gr.Markdown("#### Scan Summary: *No directory scanned yet.*")

        files_table = gr.Dataframe(
            headers=["Preview", "Name", "Modality", "Type", "Size", "Relative Path", "Absolute Path"],
            datatype=["html", "str", "str", "str", "str", "str", "str"],
            value=[],
            interactive=False,
            wrap=True,
            min_width=800
        )

        # Interactive Media Inspector Drawer for scanned files
        with gr.Group(visible=False, elem_classes=["status-panel"]) as ingest_media_inspector_group:
            with gr.Row():
                gr.Markdown("#### 🔬 Scanned File Media Inspector", scale=4)
                ingest_close_inspector_btn = gr.Button("✖️ Close Inspector", size="sm", scale=1)

            with gr.Row():
                ingest_inspector_image = gr.Image(label="🖼️ Image Preview", visible=False, scale=2, interactive=False)
                ingest_inspector_audio = gr.Audio(label="🎵 Audio Playback", visible=False, scale=2, interactive=False)
                ingest_inspector_video = gr.Video(label="🎬 Video Player", visible=False, scale=2, interactive=False)

                with gr.Column(scale=3):
                    ingest_inspector_details = gr.Markdown("*(Select a row in the table above to preview media & details)*")
                    ingest_inspector_content = gr.Textbox(label="📄 Extracted Content / Text", lines=6, visible=False, interactive=False)

        # State to store scanned files in memory for ingestion
        scanned_state = gr.State([])

        domains = DBManager.list_dirs()
        if not domains:
            domains = ["default"]
        initial_domain = settings.last_domain if settings.last_domain in domains else domains[0]

        tables = DBManager.list_tables(initial_domain)
        if not tables:
            tables = ["raw_assets"]
        initial_table = settings.last_table if settings.last_table in tables else tables[0]

        gr.Markdown("---")
        gr.Markdown("### 📥 Pixeltable Ingestion Target")
        with gr.Row():
            domain_dropdown = gr.Dropdown(
                label="Pixeltable Domain / Directory (Select or type new)",
                choices=domains,
                value=initial_domain,
                allow_custom_value=True,
                scale=2
            )
            table_dropdown = gr.Dropdown(
                label="Table Name (Select or type new)",
                choices=tables,
                value=initial_table,
                allow_custom_value=True,
                scale=2
            )
            overwrite_check = gr.Checkbox(
                label="Overwrite if Exists (Preserves Lineage History)",
                value=False,
                scale=2
            )

        with gr.Row():
            ingest_btn = gr.Button("⚡ Ingest into Pixeltable", variant="primary", scale=1)

        with gr.Group(elem_classes=["status-panel"]):
            ingest_status_box = gr.Markdown("#### Ingestion Status: *Ready*")

    def on_mode_change(selected_mode):
        is_csv = ("single" in selected_mode.lower() or "csv" in selected_mode.lower())
        summary_text = "#### Scan Summary: *No CSV file inspected yet.*" if is_csv else "#### Scan Summary: *No directory scanned yet.*"
        default_headers = ["Column 1", "Column 2", "Column 3"] if is_csv else ["Preview", "Name", "Modality", "Type", "Size", "Relative Path", "Absolute Path"]
        default_dt = ["str", "str", "str"] if is_csv else ["html", "str", "str", "str", "str", "str", "str"]
        return (
            gr.update(visible=not is_csv),
            gr.update(visible=is_csv),
            summary_text,
            gr.update(headers=default_headers, datatype=default_dt, value=[]),
            []
        )

    def on_dir_change(selected_path):
        """Update choices dynamically when user selects or types a path."""
        if not selected_path:
            return gr.update()
        new_choices = IngestController.get_directory_suggestions(selected_path)
        return gr.update(choices=new_choices)

    def on_file_change(selected_path):
        """Update file choices dynamically when user selects or types a path."""
        if not selected_path:
            return gr.update()
        new_choices = IngestController.get_file_suggestions(selected_path)
        return gr.update(choices=new_choices)

    def on_ingest_domain_change(selected_domain):
        if not selected_domain:
            return gr.update(choices=["raw_assets"], value="raw_assets")
        clean_dir = selected_domain.strip()
        tables_list = DBManager.list_tables(clean_dir)
        if not tables_list:
            tables_list = ["raw_assets"]
        curr_settings = get_settings()
        selected_tbl = curr_settings.last_table if curr_settings.last_table in tables_list else tables_list[0]
        return gr.update(choices=tables_list, value=selected_tbl)

    def on_scan_directory(path_str, modalities, recursive, progress=gr.Progress(track_tqdm=False)):
        def cb(pct, desc):
            progress(pct, desc=desc)

        res = IngestController.scan_directory_flow(
            path_str=path_str,
            modalities=modalities,
            recursive=recursive,
            progress_callback=cb
        )

        if res["status"] == "error":
            gr.Error(res["summary"])
            return res["summary"], gr.update(headers=["Status"], value=[]), [], gr.update()

        if res["status"] == "empty":
            gr.Info(f"No matching files found in {path_str}")

        return (
            res["summary"],
            gr.update(
                headers=res.get("headers", ["Preview", "Name", "Modality", "Type", "Size", "Relative Path", "Absolute Path"]),
                datatype=res.get("datatypes", ["html", "str", "str", "str", "str", "str", "str"]),
                value=res["files_table"]
            ),
            res["scanned_files"],
            gr.update(choices=res["directory_choices"])
        )

    def on_scan_single_file(file_path, progress=gr.Progress(track_tqdm=False)):
        def cb(pct, desc):
            progress(pct, desc=desc)

        res = IngestController.scan_single_file_flow(file_path, progress_callback=cb)
        if res["status"] == "error":
            gr.Error(res["summary"])
            return res["summary"], gr.update(headers=["Status"], value=[]), [], gr.update(), gr.update(choices=["(Auto / All Columns)"], value="(Auto / All Columns)")

        cols = res.get("columns", [])
        text_col_choices = ["(Auto / All Columns)"] + cols

        # Auto-detect common text column names
        best_choice = "(Auto / All Columns)"
        for candidate in ["content", "text", "description", "body", "summary", "notes", "headline", "comment"]:
            for c in cols:
                if candidate in c.lower():
                    best_choice = c
                    break
            if best_choice != "(Auto / All Columns)":
                break

        return (
            res["summary"],
            gr.update(headers=res["headers"], value=res["files_table"]),
            res["scanned_files"],
            gr.update(choices=res["file_choices"], value=file_path),
            gr.update(choices=text_col_choices, value=best_choice)
        )

    def on_ingest(files_data, domain, table_name, overwrite, mode, single_file_path, text_column, progress=gr.Progress(track_tqdm=False)):
        is_csv = ("single" in mode.lower() or "csv" in mode.lower())
        if is_csv and not single_file_path and not files_data:
            gr.Warning("No CSV file selected. Please select and inspect a CSV file first.")
            return "### ⚠️ No CSV File to Ingest\n> Please select and inspect a CSV file first."

        if not is_csv and not files_data:
            gr.Warning("No scanned files to ingest. Scan a directory first.")
            return "### ⚠️ No Files to Ingest\n> Please scan a directory containing documents/media first."

        def cb(cur, total, detail):
            pct = (cur / total) if total else 0.5
            progress(pct, desc=detail)

        res = IngestController.ingest_files_flow(
            domain=domain,
            table_name=table_name,
            scanned_files=files_data,
            overwrite=overwrite,
            mode=mode,
            single_file_path=single_file_path,
            text_column=text_column,
            progress_callback=cb
        )

        if res["status"] == "success":
            gr.Info(f"Ingestion successful into {res.get('safe_domain')}.{res.get('safe_table')}!")
        else:
            gr.Error("Ingestion encountered an issue.")

        return res["message"]

    ingest_mode_radio.change(
        fn=on_mode_change,
        inputs=[ingest_mode_radio],
        outputs=[directory_controls_group, single_file_controls_group, summary_markdown, files_table, scanned_state]
    )

    dir_input.change(
        fn=on_dir_change,
        inputs=[dir_input],
        outputs=[dir_input]
    )

    file_input.change(
        fn=on_file_change,
        inputs=[file_input],
        outputs=[file_input]
    )

    domain_dropdown.change(
        fn=on_ingest_domain_change,
        inputs=[domain_dropdown],
        outputs=[table_dropdown]
    )

    scan_dir_btn.click(
        fn=on_scan_directory,
        inputs=[dir_input, modality_filters, recursive_check],
        outputs=[summary_markdown, files_table, scanned_state, dir_input]
    )

    scan_file_btn.click(
        fn=on_scan_single_file,
        inputs=[file_input],
        outputs=[summary_markdown, files_table, scanned_state, file_input, primary_text_col_dropdown]
    )

    def on_select_scanned_row(evt: gr.SelectData, current_df, scanned_files):
        if not evt or evt.index is None:
            return gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
        row_idx = evt.index[0] if isinstance(evt.index, (list, tuple)) else 0
        file_path = ""
        file_name = ""
        modality = ""
        file_type = ""
        size = ""

        if scanned_files and 0 <= row_idx < len(scanned_files):
            sf = scanned_files[row_idx]
            file_path = sf.get("abs_path", "")
            file_name = sf.get("name", Path(file_path).name if file_path else "Unknown")
            modality = str(sf.get("modality", "")).lower()
            file_type = str(sf.get("extension", "")).lower()
            size = sf.get("size", "")
        elif hasattr(current_df, "iloc") and 0 <= row_idx < len(current_df):
            r = current_df.iloc[row_idx].to_dict()
            file_name = str(r.get("Name", ""))
            modality = str(r.get("Modality", "")).lower()
            file_type = str(r.get("Type", "")).lower()
            size = str(r.get("Size", ""))
            file_path = str(r.get("Absolute Path", ""))

        file_exists = os.path.exists(file_path) if file_path else False
        img_val = file_path if (modality == "images" or file_type in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"]) and file_exists else None
        audio_val = file_path if (modality == "audio" or file_type in [".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"]) and file_exists else None
        video_val = file_path if (modality == "video" or file_type in [".mp4", ".webm", ".mov", ".avi", ".mkv"]) and file_exists else None

        content = DBManager.extract_file_content(file_path, modality, file_type) if file_exists else ""
        has_content = bool(content and content.strip())

        details_md = f"### 📄 **{file_name}**\n- **Modality:** `{modality}` | **Type:** `{file_type}` | **Size:** {size}\n- **Path:** `{file_path}`"

        return (
            gr.update(visible=True),
            gr.update(value=img_val, visible=bool(img_val)),
            gr.update(value=audio_val, visible=bool(audio_val)),
            gr.update(value=video_val, visible=bool(video_val)),
            details_md,
            gr.update(value=content if has_content else "", visible=has_content)
        )

    files_table.select(
        fn=on_select_scanned_row,
        inputs=[files_table, scanned_state],
        outputs=[ingest_media_inspector_group, ingest_inspector_image, ingest_inspector_audio, ingest_inspector_video, ingest_inspector_details, ingest_inspector_content]
    )

    ingest_close_inspector_btn.click(
        fn=lambda: gr.update(visible=False),
        outputs=[ingest_media_inspector_group]
    )

    ingest_btn.click(
        fn=on_ingest,
        inputs=[scanned_state, domain_dropdown, table_dropdown, overwrite_check, ingest_mode_radio, file_input, primary_text_col_dropdown],
        outputs=[ingest_status_box]
    )

    if tab is not None:
        def on_tab_select(current_domain, current_table):
            latest_domains = DBManager.list_dirs()
            if not latest_domains:
                latest_domains = ["default"]
            curr_settings = get_settings()
            dom = curr_settings.last_domain if curr_settings.last_domain in latest_domains else (
                current_domain if current_domain in latest_domains else latest_domains[0]
            )
            latest_tables = DBManager.list_tables(dom)
            if not latest_tables:
                latest_tables = ["raw_assets"]
            tbl = curr_settings.last_table if curr_settings.last_table in latest_tables else (
                current_table if current_table in latest_tables else latest_tables[0]
            )
            return (
                gr.update(choices=latest_domains, value=dom),
                gr.update(choices=latest_tables, value=tbl)
            )

        tab.select(
            fn=on_tab_select,
            inputs=[domain_dropdown, table_dropdown],
            outputs=[domain_dropdown, table_dropdown]
        )
