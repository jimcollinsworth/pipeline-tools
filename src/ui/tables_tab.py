"""
View & Export Tab (Pixeltable DataTable Viewer & AI Report Synthesis)
=====================================================================
This module renders the Data Viewing and AI Document Export workbench.

Key UI & WebSocket Event Architecture Principles:
-------------------------------------------------
1. Decoupled Single-Responsibility Event Flow:
   - CRITICAL LESSON / ANTIPATTERN TRIED:
     If `domain_dropdown.change` or `tab.select` simultaneously updates downstream dropdown values
     AND emits a full `gr.Dataframe` update, Gradio's reactive engine immediately triggers the
     downstream `.change` handlers. This floods the WebSocket queue with 3-4 simultaneous DataFrame
     re-render instructions for the same Svelte component, locking the browser UI thread in an
     infinite loop (`processing | 8.2/0.5s`) until Chrome crashes with `Error code: Out of Memory`.
   - THE FIX:
     * `domain_dropdown.change` ONLY updates `table_dropdown` choices (`outputs=[table_dropdown]`).
     * `table_dropdown.change` sequentially loads the table data once (`outputs=[stats, dataframe]`).
     * `tab.select` ONLY synchronizes dropdown choices/values without blasting duplicate parallel queries.

2. Zero-Query Interactive Row Selection:
   - Clicking a table row passes the loaded `data_view_table` directly to `on_select_table_row`.
   - Populates the Media Inspector drawer in 0ms from client memory with zero database queries.

3. Zero-Memory Media Streaming:
   - Image, audio, video, and PDF previews use direct `/gradio_api/file={safe_path}` streaming endpoints.
   - Eliminates Python RAM bloat and allows the browser to cache and lazily load media on demand.
"""

import os
import gradio as gr
import pandas as pd
from typing import List
from pathlib import Path
from src.core.config import get_settings, update_last_entry
from src.db.manager import DBManager
from src.core.llm_service import LLMService
from src.export.exporter import MarkdownExporter
from src.controllers.tables_controller import TablesController


def render_tables_tab(tab=None):
    """Render the Pixeltable DataTables viewer, media inspector, and AI report exporter."""
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
                scale=3
            )
            table_dropdown = gr.Dropdown(
                label="Table Name",
                choices=tables,
                value=initial_table,
                allow_custom_value=True,
                scale=3
            )
            limit_slider = gr.Slider(minimum=5, maximum=100, value=25, step=5, label="Max Rows to Fetch", scale=2)
            lightweight_toggle = gr.Checkbox(label="⚡ Lightweight Preview", value=True, scale=1)

        with gr.Row():
            undo_table_btn = gr.Button("↩️ Undo Last Operation", variant="secondary", scale=2)
            delete_table_btn = gr.Button("🗑️ Delete Table", variant="secondary", scale=2)
            delete_domain_btn = gr.Button("⚠️ Delete Domain & All Tables", variant="secondary", scale=2)

        # Deletion confirmation drawer
        with gr.Group(visible=False, elem_classes=["status-panel"]) as delete_confirm_group:
            confirm_message_markdown = gr.Markdown("### ⚠️ Confirm Permanent Deletion")
            with gr.Row():
                confirm_delete_action_btn = gr.Button("❌ Yes, Permanently Delete", variant="primary", scale=2)
                cancel_delete_action_btn = gr.Button("↩️ Cancel", variant="secondary", scale=1)
            pending_delete_type_state = gr.State("")

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
            gr.Markdown("### 📝 Prompt-Driven AI Markdown Document Export")

            with gr.Accordion("💡 Prompt Guide & Example Presets (Click to Apply)", open=False):
                gr.Markdown(
                    """
                    **How AI Markdown Document Export Works**:
                    * **🤖 AI Dataset Synthesis**: Ollama or Gemini processes up to `{max_records}` table rows into a comprehensive, styled Markdown report.
                    * **💡 Context & Variables**: Use `{table_context}` to inject full multi-record data blocks, plus `{domain}`, `{table}`, and `{total_rows}`.
                    """
                )
                with gr.Row():
                    preset_entity_btn = gr.Button("🏷️ Entity & Keyword Intelligence", size="sm")
                    preset_visual_btn = gr.Button("🎨 Visual & Scene Breakdown", size="sm")
                with gr.Row():
                    preset_summary_btn = gr.Button("📋 Thematic Summary & Executive Brief", size="sm")
                    preset_catalog_btn = gr.Button("📁 Structured Media Catalog Dossier", size="sm")

            with gr.Row():
                export_provider_dropdown = gr.Dropdown(
                    label="AI Provider",
                    choices=LLMService.PROVIDERS,
                    value=initial_provider,
                    scale=2
                )
                export_model_dropdown = gr.Dropdown(
                    label="Model Identifier",
                    choices=initial_models,
                    value=settings.last_model or initial_models[0],
                    allow_custom_value=True,
                    scale=3
                )
                export_rows_slider = gr.Slider(
                    minimum=1,
                    maximum=200,
                    value=25,
                    step=1,
                    label="Max Records to Include",
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
                label="User Synthesis Prompt Template",
                value=MarkdownExporter.PRESETS["Entity & Keyword Intelligence"]["prompt_template"],
                lines=6,
                placeholder="Enter synthesis prompt template. Use {domain}, {table}, {total_rows}, {table_context} or individual {column_name} placeholders."
            )

            with gr.Row():
                custom_filename_input = gr.Textbox(
                    label="Custom Output Filename (Optional)",
                    placeholder="e.g. entities_summary_2026",
                    scale=3
                )
                generate_export_btn = gr.Button("⚡ Generate & Export AI Markdown Report", variant="primary", scale=2)

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
        res = TablesController.handle_load_table(domain, table_name, limit=limit, is_lightweight=is_lightweight)
        return res["stats_text"], gr.update(headers=res["columns"], datatype=res["datatypes"], value=res["data"]), res["placeholders_text"]

    def on_domain_change(domain):
        """Update table dropdown choices when domain selection changes."""
        res = TablesController.handle_domain_change(domain)
        return gr.update(choices=res["choices"], value=res["value"])

    def on_export_provider_change(provider):
        models = LLMService.list_models_for_provider(provider)
        if not models:
            models = ["gemini-3.7-flash"] if provider == "Gemini" else ["llama3.2"]
        return gr.update(choices=models, value=models[0])

    def load_preset(preset_key):
        preset = MarkdownExporter.PRESETS.get(preset_key)
        if not preset:
            return gr.update(), gr.update()
        return preset["system_prompt"], preset["prompt_template"]

    def on_select_table_row(evt: gr.SelectData, current_df, domain, table_name):
        """Populate and display the Media Inspector drawer when a table row is clicked without re-querying the database."""
        if not evt or evt.index is None:
            return gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()

        row_idx = evt.index[0] if isinstance(evt.index, (list, tuple)) else 0
        insp = TablesController.handle_row_inspection(row_idx, current_df, domain, table_name)
        return (
            gr.update(visible=True),
            gr.update(value=insp["image_path"], visible=insp["has_image"]),
            gr.update(value=insp["audio_path"], visible=insp["has_audio"]),
            gr.update(value=insp["video_path"], visible=insp["has_video"]),
            insp["details_markdown"],
            gr.update(value=insp["content_text"], visible=insp["has_content"])
        )

    def on_generate_export(
        domain, table_name, provider, model,
        max_rows, system_prompt, prompt_template, custom_filename,
        progress=gr.Progress(track_tqdm=False)
    ):
        def cb(cur, total, msg):
            pct = cur / total if total else 0.5
            progress(pct, desc=msg)

        res = TablesController.handle_export_report(
            domain=domain,
            table_name=table_name,
            provider=provider,
            model=model,
            max_rows=max_rows,
            system_prompt=system_prompt,
            prompt_template=prompt_template,
            custom_filename=custom_filename,
            progress_callback=cb
        )

        if res["status"] == "success":
            gr.Info(f"AI report exported successfully: {res.get('file_name')}")
            return res["message"], res["content"], res["file_path"]
        else:
            gr.Error("Export failed")
            return res["message"], "", None

    # -------------------------------------------------------------------------
    # Wire Event Listeners (Decoupled Single-Responsibility Architecture)
    # -------------------------------------------------------------------------
    # Rule 1: Parent dropdown (domain_dropdown) only updates child dropdown choices.
    # It does NOT directly update the DataFrame to prevent duplicate event cascades.
    domain_dropdown.change(
        fn=on_domain_change,
        inputs=[domain_dropdown],
        outputs=[table_dropdown]
    )

    # Rule 2: Child dropdown (table_dropdown) sequentially loads the table data once.
    table_dropdown.change(
        fn=on_load_table,
        inputs=[domain_dropdown, table_dropdown, limit_slider, lightweight_toggle],
        outputs=[table_stats_markdown, data_view_table, available_columns_info]
    )

    # Rule 3: Parameter controls (limit slider & lightweight toggle) refresh the view on change.
    limit_slider.change(
        fn=on_load_table,
        inputs=[domain_dropdown, table_dropdown, limit_slider, lightweight_toggle],
        outputs=[table_stats_markdown, data_view_table, available_columns_info]
    )

    lightweight_toggle.change(
        fn=on_load_table,
        inputs=[domain_dropdown, table_dropdown, limit_slider, lightweight_toggle],
        outputs=[table_stats_markdown, data_view_table, available_columns_info]
    )

    # Rule 4: Zero-query row inspection. Passing data_view_table directly allows extracting
    # the selected row in 0ms from client memory with zero database queries.
    data_view_table.select(
        fn=on_select_table_row,
        inputs=[data_view_table, domain_dropdown, table_dropdown],
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
        outputs=[system_prompt_input, export_prompt_input]
    )

    preset_visual_btn.click(
        fn=lambda: load_preset("Visual & Multimodal Scene Analysis"),
        inputs=[],
        outputs=[system_prompt_input, export_prompt_input]
    )

    preset_summary_btn.click(
        fn=lambda: load_preset("Thematic Summary & Executive Brief"),
        inputs=[],
        outputs=[system_prompt_input, export_prompt_input]
    )

    preset_catalog_btn.click(
        fn=lambda: load_preset("Structured Media Catalog Dossier"),
        inputs=[],
        outputs=[system_prompt_input, export_prompt_input]
    )

    generate_export_btn.click(
        fn=on_generate_export,
        inputs=[
            domain_dropdown,
            table_dropdown,
            export_provider_dropdown,
            export_model_dropdown,
            export_rows_slider,
            system_prompt_input,
            export_prompt_input,
            custom_filename_input
        ],
        outputs=[export_status_box, export_preview_markdown, download_file_component]
    )

    def on_undo_table(domain, table_name, limit, is_lightweight):
        clean_dir = domain.strip() if domain else "default"
        clean_tbl = table_name.strip() if table_name else "raw_assets"
        res = DBManager.undo_last_operation(clean_dir, clean_tbl)
        status_msg = res.get("message", "Undo completed.")
        prefix = "✅" if res.get("status") == "success" else ("ℹ️" if res.get("status") == "info" else "❌")
        stats_text, df_update, cols_text = on_load_table(clean_dir, clean_tbl, limit, is_lightweight)
        combined_stats = f"#### Undo Status: {prefix} {status_msg}\n\n{stats_text}"
        return combined_stats, df_update, cols_text

    undo_table_btn.click(
        fn=on_undo_table,
        inputs=[domain_dropdown, table_dropdown, limit_slider, lightweight_toggle],
        outputs=[table_stats_markdown, data_view_table, available_columns_info]
    )

    def on_request_delete_table(domain, table_name):
        clean_dir = domain.strip() if domain else "default"
        clean_tbl = table_name.strip() if table_name else "raw_assets"
        msg = f"### ⚠️ Confirm Table Deletion\n\nAre you sure you want to permanently delete table **`{clean_dir}.{clean_tbl}`**?\n\n*All rows and computed columns in this table will be permanently deleted.*"
        return gr.update(visible=True), msg, "table"

    delete_table_btn.click(
        fn=on_request_delete_table,
        inputs=[domain_dropdown, table_dropdown],
        outputs=[delete_confirm_group, confirm_message_markdown, pending_delete_type_state]
    )

    def on_request_delete_domain(domain):
        clean_dir = domain.strip() if domain else "default"
        tables = DBManager.list_tables(clean_dir)
        tbls_msg = f"connected tables: {', '.join(f'`{t}`' for t in tables)}" if tables else "empty domain"
        msg = f"### ⚠️ Confirm Domain & All Tables Deletion\n\nAre you sure you want to permanently delete domain **`{clean_dir}`** and all its tables ({tbls_msg})?\n\n*This will drop the entire domain folder and all contained tables.*"
        return gr.update(visible=True), msg, "domain"

    delete_domain_btn.click(
        fn=on_request_delete_domain,
        inputs=[domain_dropdown],
        outputs=[delete_confirm_group, confirm_message_markdown, pending_delete_type_state]
    )

    cancel_delete_action_btn.click(
        fn=lambda: gr.update(visible=False),
        outputs=[delete_confirm_group]
    )

    def on_confirm_delete(delete_type, domain, table_name, limit, is_lightweight):
        clean_dir = domain.strip() if domain else "default"
        clean_tbl = table_name.strip() if table_name else "raw_assets"
        
        if delete_type == "table":
            res = DBManager.delete_table_with_details(clean_dir, clean_tbl)
        else:
            res = DBManager.delete_domain_with_details(clean_dir)

        latest_domains = DBManager.list_dirs()
        if not latest_domains:
            latest_domains = ["default"]
        new_dom = latest_domains[0]

        latest_tables = DBManager.list_tables(new_dom)
        if not latest_tables:
            latest_tables = ["raw_assets"]
        new_tbl = latest_tables[0]

        update_last_entry(last_domain=new_dom, last_table=new_tbl)
        stats_text, df_update, cols_text = on_load_table(new_dom, new_tbl, limit, is_lightweight)
        prefix = "✅" if res.get("status") == "success" else "❌"
        del_msg = f"#### Status: {prefix} {res.get('message', '')}\n\n{stats_text}"

        return (
            gr.update(visible=False),
            gr.update(choices=latest_domains, value=new_dom),
            gr.update(choices=latest_tables, value=new_tbl),
            del_msg,
            df_update,
            cols_text
        )

    confirm_delete_action_btn.click(
        fn=on_confirm_delete,
        inputs=[pending_delete_type_state, domain_dropdown, table_dropdown, limit_slider, lightweight_toggle],
        outputs=[delete_confirm_group, domain_dropdown, table_dropdown, table_stats_markdown, data_view_table, available_columns_info]
    )

    if tab is not None:
        def on_tab_select(current_domain, current_table):
            latest_domains = DBManager.list_dirs() or ["default"]
            curr_settings = get_settings()
            dom = curr_settings.last_domain if curr_settings.last_domain in latest_domains else (
                current_domain if current_domain in latest_domains else latest_domains[0]
            )
            
            latest_tables = DBManager.list_tables(dom) or ["raw_assets"]
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
