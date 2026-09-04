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
    initial_model = settings.last_model if settings.last_model in initial_models else initial_models[0]

    with gr.Column():
        gr.Markdown("### 📊 View & Export (Pixeltable DataTables & Markdown Reports)")

        with gr.Accordion("💡 View, Media Inspector & AI Export Guide (Click to Expand)", open=False):
            gr.HTML("""
            <div style="max-height: 280px; overflow-y: auto; padding: 12px 16px; background: rgba(0,0,0,0.02); border: 1px solid #e5e7eb; border-radius: 8px; font-size: 13px; line-height: 1.6;">
                <h4 style="margin-top: 0; color: #3b82f6;">📄 View & Export Strategies</h4>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 12px; font-size: 12px;">
                    <thead>
                        <tr style="border-bottom: 2px solid #ddd; text-align: left;">
                            <th style="padding: 6px;">Strategy</th>
                            <th style="padding: 6px;">Output File Path</th>
                            <th style="padding: 6px;">Best For</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr style="border-bottom: 1px solid #eee;">
                            <td style="padding: 6px;"><strong>📄 Single Synthesis</strong></td>
                            <td style="padding: 6px;"><code>exports/{domain}_{table}_report_{timestamp}.md</code></td>
                            <td style="padding: 6px;">Aggregates multiple rows into one comprehensive dossier, newspaper broadsheet, or executive briefing.</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px;"><strong>🗂️ Per-Row Sidecars</strong></td>
                            <td style="padding: 6px;"><code>exports/{source_stem}_meta.md</code></td>
                            <td style="padding: 6px;">Executes 1 LLM call per row to produce standalone sidecar files with YAML frontmatter, media links, and live streaming previews.</td>
                        </tr>
                    </tbody>
                </table>
                <h4 style="color: #3b82f6;">✨ Key Capabilities & Safeguards</h4>
                <ul style="line-height: 1.6; margin-bottom: 0;">
                    <li><strong>Standardized YAML Frontmatter:</strong> Every exported Markdown file starts with a complete, self-documenting YAML header containing run metadata, model details, domain/table source, and exact prompts used.</li>
                    <li><strong>Zero-Memory Database Streaming:</strong> Multi-megabyte text cells are sliced directly inside the PostgreSQL engine to keep memory usage under 0.1 MB and Gradio WebSocket payloads under 50 KB.</li>
                    <li><strong>🔬 Selected Record Media Inspector:</strong> Click on any row in the preview table to open the on-demand inspector drawer for high-res images, audio playback, video playback, and extracted text.</li>
                    <li><strong>Fast Markdown Invariant:</strong> Presets enforce clean GitHub-flavored Markdown and forbid heavy raw HTML or inline SVG code, keeping row generation latency at 1–2 seconds.</li>
                </ul>
            </div>
            """)
        
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
            provider_dropdown = gr.Dropdown(
                label="LLM Provider",
                choices=["Ollama", "Gemini"],
                value=initial_provider,
                scale=2
            )
            model_dropdown = gr.Dropdown(
                label="Model",
                choices=initial_models,
                value=initial_model,
                allow_custom_value=True,
                scale=3
            )
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

        # Client-side state for column filtering and zero-query row navigation
        full_table_data_state = gr.State([])
        full_table_cols_state = gr.State([])
        current_row_idx_state = gr.State(0)

        # View Mode & Column Visibility Controls
        with gr.Row():
            view_mode_radio = gr.Radio(
                choices=["📊 Table Grid", "📄 Single Document"],
                value="📊 Table Grid",
                label="Display Mode",
                show_label=False,
                interactive=True,
                scale=2
            )
            limit_slider = gr.Slider(minimum=5, maximum=100, value=25, step=5, label="Max Rows to Fetch", scale=2)
            with gr.Row(scale=1):
                select_all_cols_btn = gr.Button("✓ Select All", size="sm", variant="secondary")
                deselect_all_cols_btn = gr.Button("✕ Deselect All", size="sm", variant="secondary")

        column_selector = gr.CheckboxGroup(
            choices=[],
            value=[],
            label="Visible Columns",
            show_label=False,
            elem_classes=["compact-pill-bar"],
            interactive=True
        )

        # 1. Multi-Row Table Grid View
        with gr.Column(visible=True) as table_grid_container:
            data_view_table = gr.Dataframe(
                headers=["Column 1", "Column 2", "Column 3"],
                datatype=["str", "str", "str"],
                value=[],
                interactive=False,
                wrap=True
            )

        # 2. Single Document Reader View (Option 1)
        with gr.Column(visible=False, elem_classes=["status-panel"]) as doc_view_container:
            with gr.Row():
                doc_prev_btn = gr.Button("◀ Previous Record", size="sm", scale=2)
                doc_counter_text = gr.Markdown("### Record 0 of 0", scale=4)
                doc_next_btn = gr.Button("Next Record ▶", size="sm", scale=2)

            with gr.Row():
                doc_image = gr.Image(label="🖼️ Media Image", visible=False, scale=2, interactive=False)
                doc_audio = gr.Audio(label="🎵 Media Audio", visible=False, scale=2, interactive=False)
                doc_video = gr.Video(label="🎬 Media Video", visible=False, scale=2, interactive=False)

            doc_title = gr.Markdown("### 📄 Document Title")
            doc_highlighted = gr.HighlightedText(
                label="🏷️ Extracted Intelligence & Highlighted Entities",
                visible=False,
                combine_adjacent=True,
                show_legend=True
            )
            doc_content = gr.Textbox(label="📄 Uncut Document Text", lines=8, visible=False, interactive=False)
            doc_attributes = gr.Markdown("#### Active Columns & Attributes\n*(Select columns above to inspect)*")

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
                    inspector_highlighted = gr.HighlightedText(
                        label="🏷️ Extracted Intelligence & Highlighted Entities",
                        visible=False,
                        combine_adjacent=True,
                        show_legend=True
                    )
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
                    preset_newspaper_btn = gr.Button("📰 Newspaper Story & Photo", size="sm", variant="secondary")
                    preset_entity_btn = gr.Button("🏷️ Entity & Keyword Intelligence", size="sm")
                    preset_visual_btn = gr.Button("🎨 Visual & Scene Breakdown", size="sm")
                with gr.Row():
                    preset_summary_btn = gr.Button("📋 Thematic Summary & Executive Brief", size="sm")
                    preset_catalog_btn = gr.Button("📁 Structured Media Catalog Dossier", size="sm")

            with gr.Row():
                export_strategy_radio = gr.Radio(
                    choices=["📄 Single Document Synthesis", "🗂️ Per-Row Sidecars (_meta.md)"],
                    value="📄 Single Document Synthesis",
                    label="Export Strategy & Scope",
                    scale=3
                )
                export_rows_slider = gr.Slider(
                    minimum=1,
                    maximum=200,
                    value=25,
                    step=1,
                    label="Max Records to Process",
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
                    label="Custom Output Filename (Optional - Single Document Mode Only)",
                    placeholder="e.g. entities_summary_2026",
                    scale=3
                )
                generate_export_btn = gr.Button("⚡ Generate & Export AI Markdown", variant="primary", scale=2)

            export_status_box = gr.Markdown("#### Export Status: *Ready to export.*")

            with gr.Row():
                with gr.Column(scale=3):
                    export_preview_markdown = gr.Markdown(
                        "*(Exported Markdown report preview will appear here upon completion)*",
                        elem_classes=["status-panel"]
                    )
                with gr.Column(scale=1):
                    download_file_component = gr.File(label="📥 Download Exported Markdown File", interactive=False)

    # Helper: Render Document View from in-memory row data
    def render_doc_view(row_idx, all_data, all_cols, active_cols):
        """Render single document view fields from in-memory row data without re-querying database."""
        if not all_data or not all_cols:
            return (
                "### 📄 No Record Available",
                "### Record 0 of 0",
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                "*No data loaded.*"
            )
        safe_idx = max(0, min(len(all_data) - 1, int(row_idx or 0)))
        row_values = all_data[safe_idx]
        row_dict = dict(zip(all_cols, row_values))

        doc = TablesController.format_document_view(
            row_dict=row_dict,
            active_columns=active_cols if active_cols else all_cols,
            row_index=safe_idx,
            total_rows=len(all_data)
        )

        has_img = doc["modality"] == "images" and bool(doc["media_path"])
        has_audio = doc["modality"] == "audio" and bool(doc["media_path"])
        has_video = doc["modality"] == "video" and bool(doc["media_path"])
        has_hl = bool(doc["highlighted_spans"])
        raw_content = str(row_dict.get("content") or "")

        return (
            f"### 📄 {doc['title_text']}",
            f"### {doc['counter_text']}",
            gr.update(value=doc["media_path"], visible=has_img),
            gr.update(value=doc["media_path"], visible=has_audio),
            gr.update(value=doc["media_path"], visible=has_video),
            gr.update(value=doc["highlighted_spans"], visible=has_hl),
            gr.update(value=raw_content, visible=not has_hl and bool(raw_content)),
            doc["attributes_md"]
        )

    # Event handlers
    def on_load_table(domain, table_name, limit, is_lightweight=True):
        res = TablesController.handle_load_table(domain, table_name, limit=limit, is_lightweight=is_lightweight)
        data = res.get("data", [])
        cols = res.get("columns", [])
        doc_renders = render_doc_view(0, data, cols, cols)

        return (
            res["stats_text"],
            gr.update(headers=cols, datatype=res["datatypes"], value=data),
            res["placeholders_text"],
            gr.update(choices=cols, value=cols),
            data,
            cols,
            0,
            *doc_renders
        )

    def on_view_mode_change(mode, row_idx, data, cols, active_cols):
        is_table = (mode == "📊 Table Grid")
        doc_renders = render_doc_view(row_idx, data, cols, active_cols)
        return (
            gr.update(visible=is_table),
            gr.update(visible=not is_table),
            *doc_renders
        )

    def on_column_selector_change(selected_cols, data, cols, row_idx):
        filtered_data, filtered_cols = TablesController.filter_dataframe_columns(data, cols, selected_cols)
        doc_renders = render_doc_view(row_idx, data, cols, selected_cols)
        return (
            gr.update(headers=filtered_cols, value=filtered_data),
            doc_renders[-1]
        )

    def on_nav_doc(delta, current_idx, data, cols, active_cols):
        total = len(data) if data else 0
        new_idx = TablesController.navigate_row(int(current_idx or 0), delta, total)
        doc_renders = render_doc_view(new_idx, data, cols, active_cols)
        return (new_idx, *doc_renders)

    def on_domain_change(domain):
        """Update table dropdown choices when domain selection changes."""
        res = TablesController.handle_domain_change(domain)
        return gr.update(choices=res["choices"], value=res["value"])

    def on_provider_change(selected_provider):
        res = TablesController.handle_provider_change(selected_provider)
        return gr.update(choices=res["choices"], value=res["value"])

    def load_preset(preset_key):
        preset = MarkdownExporter.PRESETS.get(preset_key)
        if not preset:
            return gr.update(), gr.update(), gr.update()
        strat = "🗂️ Per-Row Sidecars (_meta.md)" if preset.get("mode") == "sidecar" else "📄 Single Document Synthesis"
        return preset["system_prompt"], preset["prompt_template"], strat

    def on_select_table_row(evt: gr.SelectData, current_df, domain, table_name, all_data, all_cols, active_cols):
        """Populate Inspector drawer and sync active row index for Document View."""
        if not evt or evt.index is None:
            return (
                gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(),
                0,
                "### 📄 No Record Selected",
                "### Record 0 of 0",
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                "*No data loaded.*"
            )

        row_idx = evt.index[0] if isinstance(evt.index, (list, tuple)) else 0
        insp = TablesController.handle_row_inspection(row_idx, current_df, domain, table_name)
        show_hl = insp.get("has_highlighted", False)
        inspector_updates = (
            gr.update(visible=True),
            gr.update(value=insp["image_path"], visible=insp["has_image"]),
            gr.update(value=insp["audio_path"], visible=insp["has_audio"]),
            gr.update(value=insp["video_path"], visible=insp["has_video"]),
            insp["details_markdown"],
            gr.update(value=insp["content_text"], visible=insp["has_content"] and not show_hl),
            gr.update(value=insp.get("highlighted_spans", []), visible=show_hl)
        )

        doc_renders = render_doc_view(row_idx, all_data, all_cols, active_cols)
        return (*inspector_updates, row_idx, *doc_renders)

    def on_generate_export(
        domain, table_name, provider, model,
        max_rows, system_prompt, prompt_template, export_strategy, custom_filename,
        progress=gr.Progress(track_tqdm=False)
    ):
        if not domain or not table_name:
            gr.Warning("Please select a domain and table first.")
            yield "### ⚠️ Missing Target Table\nPlease select a Domain and Table above.", "", None
            return

        if not prompt_template or not prompt_template.strip():
            gr.Warning("Please enter a prompt template.")
            yield "### ⚠️ Missing Prompt Template\nPlease enter a synthesis prompt template.", "", None
            return

        is_sidecar = ("sidecar" in export_strategy.lower() or "per-row" in export_strategy.lower())

        if is_sidecar:
            last_file = None
            last_md = ""
            total_saved = 0
            for update in MarkdownExporter.generate_sidecar_exports(
                domain=domain,
                table_name=table_name,
                prompt_template=prompt_template,
                system_prompt=system_prompt,
                provider=provider,
                model=model,
                max_rows=int(max_rows),
                progress_callback=lambda cur, tot, msg: progress(cur, desc=msg)
            ):
                if update.get("status") == "error":
                    gr.Error(update.get("message", "Export error"))
                    yield f"### ❌ Export Error\n{update.get('message')}", "", None
                    return

                cur_idx = update.get("current_index", 0)
                tot_rows = update.get("total_rows", 1)
                cur_file = update.get("current_file", "")
                last_file = update.get("file_path")
                last_md = update.get("markdown_content", "")
                total_saved = len(update.get("saved_files", []))

                status_msg = (
                    f"### ⏳ Generating Sidecars... [{cur_idx}/{tot_rows}]\n"
                    f"- **Current Record:** `{cur_file}`\n"
                    f"- **Saved Sidecar:** `{update.get('sidecar_name')}`\n"
                    f"- **Total Sidecars Written:** `{total_saved}` in `exports/`"
                )
                yield status_msg, last_md, last_file

            final_msg = (
                f"### ✅ All Per-Row Sidecars Generated Successfully!\n"
                f"- **Strategy:** Per-Row Sidecars (`_meta.md`)\n"
                f"- **Total Sidecar Files Created:** `{total_saved}` in `exports/`\n"
                f"- **AI Engine / Model:** `{provider}` ({model})\n"
                f"- **Latest Saved File:** `{last_file}`"
            )
            gr.Info(f"Successfully exported {total_saved} sidecar files!")
            yield final_msg, last_md, last_file

        else:
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
                mode="single",
                custom_filename=custom_filename,
                progress_callback=cb
            )

            if res["status"] == "success":
                gr.Info(f"AI report exported successfully: {res.get('file_name')}")
                yield res["message"], res["content"], res["file_path"]
            else:
                gr.Error("Export failed")
                yield res["message"], "", None

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

    table_load_outputs = [
        table_stats_markdown, data_view_table, available_columns_info,
        column_selector, full_table_data_state, full_table_cols_state, current_row_idx_state,
        doc_title, doc_counter_text, doc_image, doc_audio, doc_video,
        doc_highlighted, doc_content, doc_attributes
    ]

    # Rule 2: Child dropdown (table_dropdown) sequentially loads the table data once.
    table_dropdown.change(
        fn=on_load_table,
        inputs=[domain_dropdown, table_dropdown, limit_slider, lightweight_toggle],
        outputs=table_load_outputs
    )

    # Rule 3: Parameter controls (limit slider & lightweight toggle) refresh the view on change.
    limit_slider.change(
        fn=on_load_table,
        inputs=[domain_dropdown, table_dropdown, limit_slider, lightweight_toggle],
        outputs=table_load_outputs
    )

    lightweight_toggle.change(
        fn=on_load_table,
        inputs=[domain_dropdown, table_dropdown, limit_slider, lightweight_toggle],
        outputs=table_load_outputs
    )

    # Rule 4: View Mode Toggle (Table Grid vs. Single Document)
    view_mode_radio.change(
        fn=on_view_mode_change,
        inputs=[view_mode_radio, current_row_idx_state, full_table_data_state, full_table_cols_state, column_selector],
        outputs=[
            table_grid_container, doc_view_container,
            doc_title, doc_counter_text, doc_image, doc_audio, doc_video,
            doc_highlighted, doc_content, doc_attributes
        ]
    )

    # Rule 5: Column Visibility Pill Bar Filtering
    column_selector.change(
        fn=on_column_selector_change,
        inputs=[column_selector, full_table_data_state, full_table_cols_state, current_row_idx_state],
        outputs=[data_view_table, doc_attributes]
    )

    select_all_cols_btn.click(
        fn=lambda cols: gr.update(value=cols),
        inputs=[full_table_cols_state],
        outputs=[column_selector]
    )

    deselect_all_cols_btn.click(
        fn=lambda: gr.update(value=[]),
        outputs=[column_selector]
    )

    # Rule 6: Single Document Navigation (◀ Previous / Next ▶)
    doc_prev_btn.click(
        fn=lambda c, d, cols, a: on_nav_doc(-1, c, d, cols, a),
        inputs=[current_row_idx_state, full_table_data_state, full_table_cols_state, column_selector],
        outputs=[
            current_row_idx_state,
            doc_title, doc_counter_text, doc_image, doc_audio, doc_video,
            doc_highlighted, doc_content, doc_attributes
        ]
    )

    doc_next_btn.click(
        fn=lambda c, d, cols, a: on_nav_doc(1, c, d, cols, a),
        inputs=[current_row_idx_state, full_table_data_state, full_table_cols_state, column_selector],
        outputs=[
            current_row_idx_state,
            doc_title, doc_counter_text, doc_image, doc_audio, doc_video,
            doc_highlighted, doc_content, doc_attributes
        ]
    )

    # Rule 7: Zero-query row inspection. Passing data_view_table directly allows extracting
    # the selected row in 0ms from client memory with zero database queries.
    data_view_table.select(
        fn=on_select_table_row,
        inputs=[data_view_table, domain_dropdown, table_dropdown, full_table_data_state, full_table_cols_state, column_selector],
        outputs=[
            media_inspector_group,
            inspector_image,
            inspector_audio,
            inspector_video,
            inspector_details,
            inspector_content,
            inspector_highlighted,
            current_row_idx_state,
            doc_title, doc_counter_text, doc_image, doc_audio, doc_video,
            doc_highlighted, doc_content, doc_attributes
        ]
    )

    close_inspector_btn.click(
        fn=lambda: gr.update(visible=False),
        outputs=[media_inspector_group]
    )

    provider_dropdown.change(
        fn=on_provider_change,
        inputs=[provider_dropdown],
        outputs=[model_dropdown]
    )

    preset_newspaper_btn.click(
        fn=lambda: load_preset("Newspaper Story & Embedded Photo"),
        inputs=[],
        outputs=[system_prompt_input, export_prompt_input, export_strategy_radio]
    )

    preset_entity_btn.click(
        fn=lambda: load_preset("Entity & Keyword Intelligence"),
        inputs=[],
        outputs=[system_prompt_input, export_prompt_input, export_strategy_radio]
    )

    preset_visual_btn.click(
        fn=lambda: load_preset("Visual & Multimodal Scene Analysis"),
        inputs=[],
        outputs=[system_prompt_input, export_prompt_input, export_strategy_radio]
    )

    preset_summary_btn.click(
        fn=lambda: load_preset("Thematic Summary & Executive Brief"),
        inputs=[],
        outputs=[system_prompt_input, export_prompt_input, export_strategy_radio]
    )

    preset_catalog_btn.click(
        fn=lambda: load_preset("Structured Media Catalog Dossier"),
        inputs=[],
        outputs=[system_prompt_input, export_prompt_input, export_strategy_radio]
    )

    generate_export_btn.click(
        fn=on_generate_export,
        inputs=[
            domain_dropdown,
            table_dropdown,
            provider_dropdown,
            model_dropdown,
            export_rows_slider,
            system_prompt_input,
            export_prompt_input,
            export_strategy_radio,
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
        def on_tab_select(current_domain, current_table, current_provider, current_model):
            latest_domains = DBManager.list_dirs() or ["default"]
            curr_settings = get_settings()
            dom = curr_settings.last_domain if curr_settings.last_domain in latest_domains else (
                current_domain if current_domain in latest_domains else latest_domains[0]
            )
            
            latest_tables = DBManager.list_tables(dom) or ["raw_assets"]
            tbl = curr_settings.last_table if curr_settings.last_table in latest_tables else (
                current_table if current_table in latest_tables else latest_tables[0]
            )

            prov = curr_settings.last_provider or current_provider or "Ollama"
            models = LLMService.list_models_for_provider(prov)
            mod = curr_settings.last_model if curr_settings.last_model in models else (
                current_model if current_model in models else (models[0] if models else "llama3.2")
            )
            
            return (
                gr.update(choices=latest_domains, value=dom),
                gr.update(choices=latest_tables, value=tbl),
                gr.update(value=prov),
                gr.update(choices=models, value=mod)
            )

        tab.select(
            fn=on_tab_select,
            inputs=[domain_dropdown, table_dropdown, provider_dropdown, model_dropdown],
            outputs=[domain_dropdown, table_dropdown, provider_dropdown, model_dropdown]
        )
