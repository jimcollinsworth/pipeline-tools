import gradio as gr
import pandas as pd
from pathlib import Path
from src.core.config import get_settings, update_last_entry, sanitize_identifier
from src.ingest.scanner import scan_directory
from src.db.manager import DBManager

def get_directory_choices(current_path=None):
    """Generate intelligent path suggestions for type-ahead dropdown."""
    choices = set()
    cwd = Path.cwd()
    home = Path.home()
    
    choices.add(str(cwd))
    choices.add(str(home))
    
    curr = get_settings().default_ingest_dir
    if curr and Path(curr).exists():
        choices.add(str(Path(curr)))

    # Discover immediate subdirectories of CWD & Home
    for base in [cwd, home]:
        try:
            for child in base.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    choices.add(str(child))
        except Exception:
            pass

    # If current_path exists, include it and its subdirectories
    if current_path:
        try:
            p = Path(current_path.strip())
            if p.exists() and p.is_dir():
                choices.add(str(p))
                for child in p.iterdir():
                    if child.is_dir() and not child.name.startswith("."):
                        choices.add(str(child))
        except Exception:
            pass

    return sorted(list(choices))

def render_ingest_tab(tab=None):
    settings = get_settings()
    default_path = settings.default_ingest_dir or str(Path.cwd())

    with gr.Column(scale=1):
        gr.Markdown("### 📂 Ingestion & Directory Scanner")
        
        with gr.Row():
            dir_input = gr.Dropdown(
                label="Source Directory Path (Type or select from tree)",
                choices=get_directory_choices(default_path),
                value=default_path,
                allow_custom_value=True,
                filterable=True,
                scale=4
            )
            scan_btn = gr.Button("🔍 Scan Directory", variant="primary", scale=1)

        with gr.Row():
            modality_filters = gr.CheckboxGroup(
                label="Include Modalities",
                choices=["docs", "images", "audio", "video", "other"],
                value=["docs", "images", "audio", "video"],
                scale=3
            )
            recursive_check = gr.Checkbox(label="Recursive Subdirectories", value=True, scale=1)

        summary_markdown = gr.Markdown("#### Scan Summary: *No directory scanned yet.*")

        files_table = gr.Dataframe(
            headers=["Name", "Modality", "Type", "Size", "Relative Path", "Absolute Path"],
            datatype=["str", "str", "str", "str", "str", "str"],
            value=[],
            interactive=False,
            wrap=True,
            min_width=800
        )

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
            ingest_btn = gr.Button("⚡ Ingest Scanned Files into Pixeltable", variant="primary", scale=1)

        with gr.Group(elem_classes=["status-panel"]):
            ingest_status_box = gr.Markdown("#### Ingestion Status: *Ready*")

    def on_dir_change(selected_path):
        """Update choices dynamically when user selects or types a path."""
        if not selected_path:
            return gr.update()
        new_choices = IngestController.get_directory_suggestions(selected_path)
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

    def on_scan(path_str, modalities, recursive, progress=gr.Progress(track_tqdm=True)):
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
            return res["summary"], [], [], gr.update()

        if res["status"] == "empty":
            gr.Info(f"No matching files found in {path_str}")

        return (
            res["summary"],
            res["files_table"],
            res["scanned_files"],
            gr.update(choices=res["directory_choices"])
        )

    def on_ingest(files_data, domain, table_name, overwrite, progress=gr.Progress(track_tqdm=True)):
        if not files_data:
            gr.Warning("No scanned files to ingest. Scan a directory first.")
            yield "### ⚠️ No Files to Ingest\n> Please scan a directory containing documents/media first."
            return

        def cb(cur, total, detail):
            pct = (cur / total) if total else 0.5
            progress(pct, desc=detail)

        yield f"⏳ **Ingestion Started...** Target: `{domain}.{table_name}` for {len(files_data)} files..."

        res = IngestController.ingest_files_flow(
            domain=domain,
            table_name=table_name,
            scanned_files=files_data,
            overwrite=overwrite,
            progress_callback=cb
        )

        if res["status"] == "success":
            gr.Info(f"Successfully ingested {len(files_data)} files into {res.get('safe_domain')}.{res.get('safe_table')}!")
        else:
            gr.Error("Ingestion encountered an issue.")

        yield res["message"]

    dir_input.change(
        fn=on_dir_change,
        inputs=[dir_input],
        outputs=[dir_input]
    )

    domain_dropdown.change(
        fn=on_ingest_domain_change,
        inputs=[domain_dropdown],
        outputs=[table_dropdown]
    )

    scan_btn.click(
        fn=on_scan,
        inputs=[dir_input, modality_filters, recursive_check],
        outputs=[summary_markdown, files_table, scanned_state, dir_input]
    )

    ingest_btn.click(
        fn=on_ingest,
        inputs=[scanned_state, domain_dropdown, table_dropdown, overwrite_check],
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
