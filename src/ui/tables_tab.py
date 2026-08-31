import os
import gradio as gr
import pandas as pd
from typing import List
from pathlib import Path
from src.core.config import get_settings, update_last_entry
from src.db.manager import DBManager
from src.core.llm_service import LLMService
from src.export.exporter import MarkdownExporter


def render_tables_tab():
    settings = get_settings()

    domains = DBManager.list_dirs()
    if not domains:
        domains = ["default"]
    initial_domain = settings.last_domain if settings.last_domain in domains else domains[0]

    tables = DBManager.list_tables(initial_domain)
    if not tables:
        tables = ["raw_assets"]
    initial_table = settings.last_table if settings.last_table in tables else tables[0]

    initial_provider = settings.last_provider or settings.default_provider or "Ollama"
    initial_models = LLMService.list_models_for_provider(initial_provider)
    if not initial_models:
        initial_models = [settings.default_ollama_model or "llama3.2"]

    with gr.Column():
        gr.Markdown("### 📊 View & Export (Pixeltable DataTables & Markdown Reports)")
        
        with gr.Row():
            domain_dropdown = gr.Dropdown(
                label="Domain / Directory",
                choices=domains,
                value=initial_domain,
                allow_custom_value=True,
                scale=2
            )
            table_dropdown = gr.Dropdown(
                label="Table Name",
                choices=tables,
                value=initial_table,
                allow_custom_value=True,
                scale=2
            )
            limit_slider = gr.Slider(minimum=5, maximum=200, value=50, step=5, label="Max Rows to Fetch", scale=2)
            lightweight_toggle = gr.Checkbox(label="⚡ Lightweight Preview", value=True, scale=1)
            load_table_btn = gr.Button("🔍 Load / Refresh Table", variant="primary", scale=1)

        table_stats_markdown = gr.Markdown("#### Table Stats: *Click 'Load / Refresh Table' or select a table to view data.*")

        data_view_table = gr.Dataframe(
            headers=["Column 1", "Column 2", "Column 3"],
            datatype=["str", "str", "str"],
            value=[],
            interactive=False,
            wrap=True
        )

        # Interactive Media Inspector Drawer (Opens when row is clicked)
        with gr.Group(visible=False, elem_classes=["status-panel"]) as media_inspector_group:
            with gr.Row():
                gr.Markdown("#### 🔬 Selected Record Media Inspector", scale=4)
                close_inspector_btn = gr.Button("✖️ Close Inspector", size="sm", scale=1)

            with gr.Row():
                inspector_image = gr.Image(label="🖼️ Image Preview", visible=False, scale=2, interactive=False)
                inspector_audio = gr.Audio(label="🎵 Audio Playback", visible=False, scale=2, interactive=False)
                inspector_video = gr.Video(label="🎬 Video Player", visible=False, scale=2, interactive=False)

                with gr.Column(scale=3):
                    inspector_details = gr.Markdown("*(Select a row in the table above to inspect full media & metadata)*")
                    inspector_content = gr.Textbox(label="📄 Extracted Content / Text", lines=6, visible=False, interactive=False)

        gr.Markdown("---")
        with gr.Group(elem_classes=["status-panel"]):
            gr.Markdown("### 📝 Prompt-Driven Markdown Document Export")

            with gr.Accordion("💡 Prompt Guide & Example Presets (Click to Apply)", open=False):
                gr.Markdown(
                    """
                    **How Markdown Export Works**:
                    * **🤖 LLM Synthesis Mode**: Synthesizes table records (`{table_context}`) with Ollama or Gemini into a structured Markdown report.
                    * **📄 Direct Template Mode**: Formats rows using column placeholders (`{file_name}`, `{visual_summary}`, `{object_tags}`) without an LLM.
                    """
                )
                with gr.Row():
                    preset_entity_btn = gr.Button("🏷️ Entity & Keyword Intelligence", size="sm")
                    preset_visual_btn = gr.Button("🎨 Visual & Scene Breakdown", size="sm")
                with gr.Row():
                    preset_summary_btn = gr.Button("📋 Thematic Summary & Executive Brief", size="sm")
                    preset_catalog_btn = gr.Button("📁 Direct Structured Catalog", size="sm")

            with gr.Row():
                export_mode_radio = gr.Radio(
                    label="Export Mode",
                    choices=["🤖 LLM Synthesis (AI-Generated)", "📄 Direct Template (No LLM)"],
                    value="🤖 LLM Synthesis (AI-Generated)",
                    scale=2
                )
                export_rows_slider = gr.Slider(
                    minimum=1,
                    maximum=200,
                    value=25,
                    step=1,
                    label="Max Records to Include",
                    scale=2
                )

            with gr.Row(visible=True) as llm_controls_row:
                export_provider_dropdown = gr.Dropdown(
                    label="AI Provider",
                    choices=LLMService.PROVIDERS,
                    value=initial_provider,
                    scale=1
                )
                export_model_dropdown = gr.Dropdown(
                    label="Model Identifier",
                    choices=initial_models,
                    value=settings.last_model or initial_models[0],
                    allow_custom_value=True,
                    scale=2
                )

            available_columns_info = gr.Markdown(
                "💡 **Available Column Placeholders:** *Load a table above to see available columns.*"
            )

            system_prompt_input = gr.Textbox(
                label="System Prompt",
                value=MarkdownExporter.PRESETS["Entity & Keyword Intelligence"]["system_prompt"],
                lines=2,
                placeholder="Enter system instructions or leave empty for default concise response..."
            )

            export_prompt_input = gr.Textbox(
                label="User Synthesis / Template Prompt",
                value=MarkdownExporter.PRESETS["Entity & Keyword Intelligence"]["prompt_template"],
                lines=6,
                placeholder="Enter prompt template. Use {domain}, {table}, {total_rows}, {table_context} or individual {column_name} placeholders."
            )

            with gr.Row():
                custom_filename_input = gr.Textbox(
                    label="Custom Output Filename (Optional)",
                    placeholder="e.g. entities_summary_2026",
                    scale=3
                )
                generate_export_btn = gr.Button("⚡ Generate & Export Markdown Report", variant="primary", scale=2)

            export_status_box = gr.Markdown("#### Export Status: *Ready to export.*")

            with gr.Row():
                with gr.Column(scale=3):
                    export_preview_markdown = gr.Markdown(
                        "*(Exported Markdown report preview will appear here upon completion)*",
                        elem_classes=["status-panel"]
                    )
                with gr.Column(scale=1):
                    download_file_component = gr.File(label="📥 Download Exported Markdown File", interactive=False)

    # Event handlers
    def on_load_table(domain, table_name, limit, is_lightweight=True):
        if not domain or not table_name:
            return "⚠️ Please provide both Domain and Table name.", gr.update(headers=[], value=[]), "💡 **Available Column Placeholders:** *None*"

        clean_dir = domain.strip() if domain else "default"
        clean_tbl = table_name.strip() if table_name else "raw_assets"
        update_last_entry(last_domain=clean_dir, last_table=clean_tbl)

        res = DBManager.get_table_data(clean_dir, clean_tbl, limit=int(limit), lightweight=is_lightweight)
        if res.get("error"):
            return (
                f"❌ **Error loading table `{clean_dir}.{clean_tbl}`:**\n```\n{res.get('error')}\n```",
                gr.update(headers=["Error"], value=[[res.get('error')]]),
                "💡 **Available Column Placeholders:** *Error loading table.*"
            )

        cols = res.get("columns", [])
        datatypes = res.get("datatypes", ["str"] * len(cols))
        data = res.get("data", [])
        total = res.get("total_rows", len(data))
        mode_label = "⚡ Lightweight" if is_lightweight else "🔍 Full Media"

        stats_text = f"✅ **Table `{res.get('domain', clean_dir)}.{res.get('table', clean_tbl)}`** ({mode_label}) — Displaying {len(data)} of {total} total rows.\nColumns: `{', '.join(cols)}`"
        cols_pills = ", ".join([f"`{{{c}}}`" for c in cols if c != "media_preview"]) if cols else "*None*"
        cols_text = f"💡 **Available Column Placeholders:** {cols_pills} | Standard: `{{domain}}`, `{{table}}`, `{{total_rows}}`, `{{table_context}}`"

        return stats_text, gr.update(headers=cols, datatype=datatypes, value=data), cols_text

    def on_domain_change(domain, limit, is_lightweight):
        if not domain:
            return gr.update(choices=[], value=""), "⚠️ Select a domain.", gr.update(headers=[], value=[]), "💡 **Available Column Placeholders:** *None*"
        clean_dir = domain.strip()
        update_last_entry(last_domain=clean_dir)
        tables_list = DBManager.list_tables(clean_dir)
        if not tables_list:
            tables_list = ["raw_assets"]

        curr_settings = get_settings()
        selected_tbl = curr_settings.last_table if curr_settings.last_table in tables_list else tables_list[0]
        stats_text, df_update, cols_text = on_load_table(clean_dir, selected_tbl, limit, is_lightweight)
        return gr.update(choices=tables_list, value=selected_tbl), stats_text, df_update, cols_text

    def on_export_provider_change(provider):
        models = LLMService.list_models_for_provider(provider)
        if not models:
            models = ["gemini-3.6-flash"] if provider == "Gemini" else ["llama3.2"]
        return gr.update(choices=models, value=models[0])

    def load_preset(preset_key):
        preset = MarkdownExporter.PRESETS.get(preset_key)
        if not preset:
            return gr.update(), gr.update(), gr.update()
        mode_val = "🤖 LLM Synthesis (AI-Generated)" if preset["mode"] == "llm" else "📄 Direct Template (No LLM)"
        return mode_val, preset["system_prompt"], preset["prompt_template"]

    def on_export_mode_change(mode_selection):
        is_llm = "LLM" in mode_selection
        return gr.update(visible=is_llm), gr.update(visible=is_llm)

    def on_select_table_row(evt: gr.SelectData, domain, table_name):
        """Populate and display the Media Inspector drawer when a table row is clicked."""
        if not evt or evt.index is None:
            return gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()

        row_idx = evt.index[0] if isinstance(evt.index, (list, tuple)) else 0
        clean_dir = domain.strip() if domain else "default"
        clean_tbl = table_name.strip() if table_name else "raw_assets"

        res = DBManager.get_table_data(clean_dir, clean_tbl, limit=100, lightweight=False)
        cols = res.get("columns", [])
        data = res.get("data", [])

        if row_idx >= len(data):
            return gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()

        row_dict = dict(zip(cols, data[row_idx]))
        file_path = str(row_dict.get("file_path", ""))
        file_name = str(row_dict.get("file_name", "Unknown File"))
        modality = str(row_dict.get("modality", "")).lower()
        file_type = str(row_dict.get("file_type", "")).lower()
        content = str(row_dict.get("content", ""))
        size = row_dict.get("file_size", "")

        summary_lines = [
            f"### 📄 **{file_name}**",
            f"- **Modality:** `{modality}` | **Format:** `{file_type}` | **Size:** {size} bytes",
            f"- **File Path:** `{file_path}`"
        ]
        for k, v in row_dict.items():
            if k not in ["id", "file_name", "file_path", "rel_path", "modality", "file_type", "file_size", "content", "media_preview", "doc", "image", "audio", "video", "metadata", "created_at"] and v:
                summary_lines.append(f"- **{k}:** {v}")

        details_md = "\n".join(summary_lines)

        file_exists = os.path.exists(file_path) if file_path else False
        img_val = file_path if (modality == "images" or file_type in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"]) and file_exists else None
        audio_val = file_path if (modality == "audio" or file_type in [".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"]) and file_exists else None
        video_val = file_path if (modality == "video" or file_type in [".mp4", ".webm", ".mov", ".avi", ".mkv"]) and file_exists else None
        has_content = bool(content and content.strip())

        return (
            gr.update(visible=True),
            gr.update(value=img_val, visible=bool(img_val)),
            gr.update(value=audio_val, visible=bool(audio_val)),
            gr.update(value=video_val, visible=bool(video_val)),
            details_md,
            gr.update(value=content if has_content else "", visible=has_content)
        )

    def on_generate_export(
        domain, table_name, mode_selection, provider, model,
        max_rows, system_prompt, prompt_template, custom_filename,
        progress=gr.Progress(track_tqdm=True)
    ):
        if not domain or not table_name:
            gr.Warning("Please select a domain and table first.")
            yield "### ⚠️ Missing Target Table\nPlease select a Domain and Table above.", "", None
            return

        if not prompt_template or not prompt_template.strip():
            gr.Warning("Please enter a prompt template.")
            yield "### ⚠️ Missing Prompt Template\nPlease enter a synthesis prompt or row template.", "", None
            return

        mode_key = "llm" if "LLM" in mode_selection else "direct"
        yield f"⏳ **Generating Markdown report for `{domain}.{table_name}` ({mode_key.upper()} mode)...**", "", None

        def cb(cur, total, msg):
            pct = cur / total if total else 0.5
            progress(pct, desc=msg)

        try:
            res = MarkdownExporter.generate_report(
                domain=domain,
                table_name=table_name,
                prompt_template=prompt_template,
                system_prompt=system_prompt,
                provider=provider,
                model=model,
                mode=mode_key,
                max_rows=int(max_rows),
                custom_filename=custom_filename,
                progress_callback=cb
            )

            if res.get("status") == "success":
                file_path = res.get("file_path")
                file_name = res.get("file_name")
                content = res.get("markdown_content", "")
                total_rows = res.get("row_count", 0)

                gr.Info(f"Report exported successfully: {file_name}")
                status_msg = (
                    f"### ✅ Export Completed Successfully!\n"
                    f"- **File Saved:** `{file_path}`\n"
                    f"- **Records Included:** {total_rows}\n"
                    f"- **Generation Mode:** {mode_selection}\n"
                    f"- **Engine / Model:** `{provider}` ({model if mode_key == 'llm' else '-'})\n"
                )
                yield status_msg, content, file_path
            else:
                err_msg = res.get("message", "Unknown error during export")
                gr.Error(f"Export failed: {err_msg}")
                yield f"### ❌ Export Failed\n```\n{err_msg}\n```", "", None

        except Exception as e:
            gr.Error(f"Unexpected export exception: {str(e)}")
            yield f"### ❌ Export Error\n```\n{type(e).__name__}: {str(e)}\n```", "", None

    # Wire event listeners
    domain_dropdown.change(
        fn=on_domain_change,
        inputs=[domain_dropdown, limit_slider, lightweight_toggle],
        outputs=[table_dropdown, table_stats_markdown, data_view_table, available_columns_info]
    )

    table_dropdown.change(
        fn=on_load_table,
        inputs=[domain_dropdown, table_dropdown, limit_slider, lightweight_toggle],
        outputs=[table_stats_markdown, data_view_table, available_columns_info]
    )

    load_table_btn.click(
        fn=on_load_table,
        inputs=[domain_dropdown, table_dropdown, limit_slider, lightweight_toggle],
        outputs=[table_stats_markdown, data_view_table, available_columns_info]
    )

    lightweight_toggle.change(
        fn=on_load_table,
        inputs=[domain_dropdown, table_dropdown, limit_slider, lightweight_toggle],
        outputs=[table_stats_markdown, data_view_table, available_columns_info]
    )

    data_view_table.select(
        fn=on_select_table_row,
        inputs=[domain_dropdown, table_dropdown],
        outputs=[media_inspector_group, inspector_image, inspector_audio, inspector_video, inspector_details, inspector_content]
    )

    close_inspector_btn.click(
        fn=lambda: gr.update(visible=False),
        outputs=[media_inspector_group]
    )

    export_provider_dropdown.change(
        fn=on_export_provider_change,
        inputs=[export_provider_dropdown],
        outputs=[export_model_dropdown]
    )

    preset_entity_btn.click(
        fn=lambda: load_preset("Entity & Keyword Intelligence"),
        inputs=[],
        outputs=[export_mode_radio, system_prompt_input, export_prompt_input]
    )

    preset_visual_btn.click(
        fn=lambda: load_preset("Visual & Scene Breakdown"),
        inputs=[],
        outputs=[export_mode_radio, system_prompt_input, export_prompt_input]
    )

    preset_summary_btn.click(
        fn=lambda: load_preset("Thematic Summary & Executive Brief"),
        inputs=[],
        outputs=[export_mode_radio, system_prompt_input, export_prompt_input]
    )

    preset_catalog_btn.click(
        fn=lambda: load_preset("Direct Structured Catalog"),
        inputs=[],
        outputs=[export_mode_radio, system_prompt_input, export_prompt_input]
    )

    export_mode_radio.change(
        fn=on_export_mode_change,
        inputs=[export_mode_radio],
        outputs=[llm_controls_row, system_prompt_input]
    )

    generate_export_btn.click(
        fn=on_generate_export,
        inputs=[
            domain_dropdown,
            table_dropdown,
            export_mode_radio,
            export_provider_dropdown,
            export_model_dropdown,
            export_rows_slider,
            system_prompt_input,
            export_prompt_input,
            custom_filename_input
        ],
        outputs=[export_status_box, export_preview_markdown, download_file_component]
    )
