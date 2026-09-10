"""
Data Enhancement Tab (Prompt Workbench & Unified Output Engine)
================================================================
This module renders the Data Enhancement workbench for testing and applying LLM prompts
across Pixeltable datasets with maximum visibility for tabular data and prompts.

Key Architectural Principles & Workflow:
----------------------------------------
1. Centralized Domain System Prompt:
   - Inherits system instructions directly from the domain configuration in Settings & Models.
   - Eliminates per-screen system prompt overrides for clean domain consistency.
2. Unified Two-Table Workbench:
   - Input Table: Displays source data records and visually highlights rows targeted for sample testing.
     Clicking any record opens the Media Inspector for zero-latency rich media inspection.
   - Output Table: Single consolidated table for all generated data. Run-through outputs
     (sample tests) and committed batch columns are rendered in this unified view with explicit status indicators.
3. Maximized Layout:
   - Compact top control row for Dataset, Model, and Batch execution parameters.
   - Spacious, full-width User Prompt Studio with instant preset buttons and column placeholder pills.
   - Balanced, generous tabular inspection area.
"""

import os
import gradio as gr
import pandas as pd
from pathlib import Path
from src.core.config import get_settings, update_last_entry, get_domain_system_prompt
from src.core.llm_service import LLMService
from src.db.manager import DBManager
from src.prompts.executor import PromptExecutor
from src.controllers.playground_controller import PlaygroundController
from src.controllers.tables_controller import TablesController


def render_playground_tab(tab=None):
    """Render the Data Enhancement prompt workbench and batch execution tab."""
    settings = get_settings()

    # Discover initial domains and tables
    domains = DBManager.list_dirs() or ["default"]
    initial_domain = settings.last_domain if settings.last_domain in domains else domains[0]
    
    tables = DBManager.list_tables(initial_domain) or ["raw_assets"]
    initial_table = settings.last_table if settings.last_table in tables else tables[0]

    initial_provider = settings.last_provider or settings.default_provider or "Ollama"
    initial_models = LLMService.list_models_for_provider(initial_provider)
    initial_model = settings.last_model if settings.last_model in initial_models else (initial_models[0] if initial_models else "gemini-3.6-flash")

    # Discover initial table preview for instant data display and placeholder hints
    initial_preview = PlaygroundController.load_table_preview(
        initial_domain, initial_table, lightweight=True, target_sample_count=2
    )
    initial_cols_text = initial_preview.get(
        "placeholders_text",
        "💡 **Available Column Placeholders:** Standard: `{file_name}`, `{content}`, `{rel_path}`, `{modality}`, `{file_size}`"
    )
    initial_in_header = initial_preview.get("stats_text", "#### 📥 Input Table (Source Data)")
    initial_in_headers = initial_preview.get("columns", ["Target", "file_name", "modality", "content", "file_size"])
    initial_in_datatypes = initial_preview.get("datatypes", ["str"] * len(initial_in_headers))
    initial_in_data = initial_preview.get("data", [])

    def format_domain_prompt_banner(domain_name: str) -> str:
        prompt_text = get_domain_system_prompt(domain_name)
        snippet = (prompt_text[:120] + "...") if len(prompt_text) > 120 else prompt_text
        return f"💡 **Active System Prompt (Domain: `{domain_name}`):** *\"{snippet}\"* — *(Configure on Settings & Models tab)*"

    with gr.Column():
        gr.Markdown("### 🧪 Data Enhancement (Prompt Workbench & Unified Output Engine)")
        domain_prompt_banner = gr.Markdown(format_domain_prompt_banner(initial_domain))

        # -------------------------------------------------------------------------
        # Section 1: Compact Top Control Strip
        # -------------------------------------------------------------------------
        with gr.Group(elem_classes=["status-panel"]):
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
                provider_dropdown = gr.Dropdown(
                    label="LLM Provider",
                    choices=["Ollama", "Gemini"],
                    value=initial_provider,
                    scale=1
                )
                model_dropdown = gr.Dropdown(
                    label="Model",
                    choices=initial_models,
                    value=initial_model,
                    allow_custom_value=True,
                    scale=2
                )
                preview_mode_toggle = gr.Checkbox(
                    label="⚡ Lightweight",
                    value=True,
                    scale=1
                )

            with gr.Row():
                output_mode_radio = gr.Radio(
                    choices=["⚡ Auto-Split JSON Keys into Columns", "📄 Single Target Column"],
                    value="⚡ Auto-Split JSON Keys into Columns",
                    label="Output Mode",
                    scale=3
                )
                target_column_input = gr.Textbox(
                    label="Target Column Name",
                    value="llm_summary",
                    placeholder="e.g. llm_summary, entities",
                    visible=False,
                    scale=2
                )
                write_mode_radio = gr.Radio(
                    choices=["replace", "append"],
                    value="replace",
                    label="Write Mode",
                    visible=False,
                    scale=1
                )
                sample_count_slider = gr.Slider(
                    minimum=1,
                    maximum=10,
                    value=2,
                    step=1,
                    label="Sample Test Rows",
                    scale=1
                )
                limit_rows_input = gr.Number(
                    label="Max Batch Rows (0=all)",
                    value=0,
                    precision=0,
                    scale=1
                )

            with gr.Row():
                test_sample_btn = gr.Button("🚀 Run Test on Sample Rows", variant="primary", scale=2)
                commit_batch_btn = gr.Button("💾 Execute on Table & Save Columns", variant="primary", scale=2)
                undo_batch_btn = gr.Button("↩️ Undo Last Operation", variant="secondary", scale=1)

            batch_status_markdown = gr.Markdown("#### Status: *Ready. Select sample rows to test or execute batch on table.*")

        # -------------------------------------------------------------------------
        # Section 2: Full-Width User Prompt Studio
        # -------------------------------------------------------------------------
        with gr.Group():
            with gr.Accordion("💡 Prompt Guide & Example Presets (Click to Apply)", open=False):
                gr.Markdown(
                    """
                    **How Prompts Work with Pixeltable**:
                    * **System Instructions**: Centrally managed per-domain in *Settings & Models*.
                    * **User Prompt**: Supplies row variables (`{file_name}`, `{content}`, `{rel_path}`, `{modality}`).
                    * **⚡ Auto-Split Mode**: Top-level keys in the JSON response automatically become individual table columns!
                    """
                )
                with gr.Row():
                    preset_cv_btn = gr.Button("🖼️ Image Summary + CSV Objects", size="sm")
                    preset_meta_btn = gr.Button("🔍 Precision Metadata", size="sm")
                    preset_art_btn = gr.Button("🎨 Creative Curator", size="sm")
                    preset_doc_btn = gr.Button("📄 Document Intelligence", size="sm")

            available_columns_info = gr.Markdown(initial_cols_text)
            prompt_template_input = gr.Textbox(
                label="User Prompt Template",
                value=settings.last_user_prompt,
                lines=5,
                max_lines=10,
                placeholder="Enter prompt template. Use {file_name}, {content}, or any {column} placeholder..."
            )

        # -------------------------------------------------------------------------
        # Section 3: Consolidated Two-Table Workbench
        # -------------------------------------------------------------------------
        with gr.Row():
            # Table 1: Input Table (Source Data with Sample Target Highlight)
            with gr.Column(scale=1):
                input_table_header = gr.Markdown(initial_in_header)
                input_table = gr.Dataframe(
                    headers=initial_in_headers,
                    datatype=initial_in_datatypes,
                    value=initial_in_data,
                    interactive=False,
                    wrap=True,
                    min_width=400,
                    max_height=380
                )

                # Media Inspector Drawer for selected row
                with gr.Group(visible=False, elem_classes=["status-panel"]) as pg_media_inspector_group:
                    with gr.Row():
                        gr.Markdown("#### 🔬 Selected Record Media Inspector", scale=4)
                        pg_close_inspector_btn = gr.Button("✖️ Close", size="sm", scale=1)

                    with gr.Row():
                        pg_inspector_image = gr.Image(label="🖼️ Image Preview", visible=False, scale=2, interactive=False)
                        pg_inspector_audio = gr.Audio(label="🎵 Audio Playback", visible=False, scale=2, interactive=False)
                        pg_inspector_video = gr.Video(label="🎬 Video Player", visible=False, scale=2, interactive=False)

                        with gr.Column(scale=3):
                            pg_inspector_details = gr.Markdown("*(Select a row in the table above to inspect full media & metadata)*")
                            pg_inspector_content = gr.Textbox(label="📄 Extracted Content / Text", lines=6, visible=False, interactive=False)

            # Table 2: Output Table (Consolidated Test Preview & Enriched Batch Results)
            with gr.Column(scale=1):
                output_table_header = gr.Markdown("#### 📤 Output Table (Test Preview & Enriched Results)")
                output_table = gr.Dataframe(
                    headers=["Status", "Row ID", "File Name", "Model Output"],
                    datatype=["str", "str", "str", "str"],
                    value=[["Ready", "—", "—", f"Loaded table '{initial_domain}.{initial_table}'. Run sample test or commit batch to generate output."]],
                    interactive=False,
                    wrap=True,
                    min_width=400,
                    max_height=380
                )

    # -------------------------------------------------------------------------
    # Helper Functions & Event Handlers
    # -------------------------------------------------------------------------
    def load_input_table(domain, table_name, lightweight=True, sample_count=2):
        res = PlaygroundController.load_table_preview(
            domain, table_name, lightweight=lightweight, target_sample_count=int(sample_count)
        )
        return (
            res["stats_text"],
            gr.update(headers=res["columns"], datatype=res["datatypes"], value=res["data"]),
            res["placeholders_text"]
        )

    def on_output_mode_change(selected_mode):
        is_single = (selected_mode == "📄 Single Target Column")
        return gr.update(visible=is_single), gr.update(visible=is_single)

    output_mode_radio.change(
        fn=on_output_mode_change,
        inputs=[output_mode_radio],
        outputs=[target_column_input, write_mode_radio]
    )

    def on_provider_change(selected_provider):
        res = PlaygroundController.handle_provider_change(selected_provider)
        return gr.update(choices=res["choices"], value=res["value"])

    provider_dropdown.change(
        fn=on_provider_change,
        inputs=[provider_dropdown],
        outputs=[model_dropdown]
    )

    def on_domain_change(selected_domain, is_lightweight, sample_count):
        """Discover tables, refresh domain prompt banner, and load table preview when domain changes."""
        res = PlaygroundController.handle_domain_change(selected_domain)
        dom = selected_domain.strip() if selected_domain else "default"
        banner = format_domain_prompt_banner(dom)
        new_tbl = res["value"]

        info, df_update, pills = load_input_table(dom, new_tbl, lightweight=is_lightweight, sample_count=sample_count)
        reset_out_header = "#### 📤 Output Table (Ready for Test or Batch Execution)"
        reset_out_df = gr.update(
            headers=["Status", "Info"],
            datatype=["str", "str"],
            value=[["Ready", f"Loaded table '{dom}.{new_tbl}'. Run sample test or commit batch to generate output."]]
        )
        return gr.update(choices=res["choices"], value=new_tbl), banner, info, df_update, pills, reset_out_header, reset_out_df

    domain_dropdown.change(
        fn=on_domain_change,
        inputs=[domain_dropdown, preview_mode_toggle, sample_count_slider],
        outputs=[table_dropdown, domain_prompt_banner, input_table_header, input_table, available_columns_info, output_table_header, output_table]
    )

    def on_table_change(selected_table, current_domain, is_lightweight, sample_count):
        """Persist last table selection, refresh input preview, and reset output table."""
        if selected_table and selected_table.strip():
            tbl_str = selected_table.strip()
            update_last_entry(last_table=tbl_str)
            info, df_update, pills = load_input_table(current_domain, tbl_str, lightweight=is_lightweight, sample_count=sample_count)
            reset_out_header = "#### 📤 Output Table (Ready for Test or Batch Execution)"
            reset_out_df = gr.update(
                headers=["Status", "Info"],
                datatype=["str", "str"],
                value=[["Ready", f"Loaded table '{current_domain}.{tbl_str}'. Run sample test or commit batch to generate output."]]
            )
            return info, df_update, pills, reset_out_header, reset_out_df

        return (
            "⚠️ Select a table name.",
            gr.update(headers=[], value=[]),
            "💡 **Available Column Placeholders:** *None*",
            "#### 📤 Output Table: *No table selected*",
            gr.update(headers=[], value=[])
        )

    table_dropdown.change(
        fn=on_table_change,
        inputs=[table_dropdown, domain_dropdown, preview_mode_toggle, sample_count_slider],
        outputs=[input_table_header, input_table, available_columns_info, output_table_header, output_table]
    )

    preview_mode_toggle.change(
        fn=load_input_table,
        inputs=[domain_dropdown, table_dropdown, preview_mode_toggle, sample_count_slider],
        outputs=[input_table_header, input_table, available_columns_info]
    )

    sample_count_slider.change(
        fn=load_input_table,
        inputs=[domain_dropdown, table_dropdown, preview_mode_toggle, sample_count_slider],
        outputs=[input_table_header, input_table, available_columns_info]
    )

    def on_select_preview_row(evt: gr.SelectData, current_df, domain, table_name):
        """Populate Media Inspector in Data Enhancement tab when a table row is clicked."""
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

    input_table.select(
        fn=on_select_preview_row,
        inputs=[input_table, domain_dropdown, table_dropdown],
        outputs=[pg_media_inspector_group, pg_inspector_image, pg_inspector_audio, pg_inspector_video, pg_inspector_details, pg_inspector_content]
    )

    output_table.select(
        fn=on_select_preview_row,
        inputs=[output_table, domain_dropdown, table_dropdown],
        outputs=[pg_media_inspector_group, pg_inspector_image, pg_inspector_audio, pg_inspector_video, pg_inspector_details, pg_inspector_content]
    )

    pg_close_inspector_btn.click(
        fn=lambda: gr.update(visible=False),
        outputs=[pg_media_inspector_group]
    )

    # -------------------------------------------------------------------------
    # Test on Sample Rows -> Renders Directly into Output Table
    # -------------------------------------------------------------------------
    def on_test_sample(domain, table_name, provider, model, prompt_template, sample_count, output_mode,
                       progress=gr.Progress(track_tqdm=False)):
        if not domain or not table_name:
            gr.Warning("Domain and Table selection required.")
            return "#### Status: ⚠️ Domain and Table selection required.", "#### 📤 Output Table: ⚠️ Missing Selection", gr.update(headers=["Error"], value=[["Domain and Table selection required."]])
        if not model:
            gr.Warning("Model selection required.")
            return "#### Status: ⚠️ Model selection required.", "#### 📤 Output Table: ⚠️ Missing Model", gr.update(headers=["Error"], value=[[f"{provider} model selection required."]])

        sys_prompt = get_domain_system_prompt(domain)

        def cb(cur, total, detail):
            pct = (cur / total) if total else 0.5
            progress(pct, desc=detail)

        progress(0.1, desc=f"Evaluating prompt on {sample_count} sample rows with [{provider}] {model}...")
        res = PlaygroundController.test_sample_flow(
            domain=domain,
            table_name=table_name,
            provider=provider,
            model=model,
            system_prompt=sys_prompt,
            prompt_template=prompt_template,
            sample_count=sample_count,
            output_mode=output_mode,
            progress_callback=cb
        )

        if res["status"] == "success":
            count = res.get("count", 0)
            status_msg = f"#### Status: 🧪 Evaluated **{count}** sample rows with **[{provider}] {model}**"
            out_hdr = f"#### 📤 Output Table: 🧪 Sample Test Preview ({count} rows dry-run)"
            gr.Info(f"Evaluated {count} sample rows successfully!")
            return status_msg, out_hdr, gr.update(headers=res["headers"], datatype=["str"] * len(res["headers"]), value=res["data"])
        else:
            err_msg = res.get("message", "Test execution failed")
            gr.Error(err_msg)
            return f"#### Status: ❌ Test Failed: {err_msg}", "#### 📤 Output Table: ❌ Error", gr.update(headers=["Error"], value=[[err_msg]])

    test_sample_btn.click(
        fn=on_test_sample,
        inputs=[domain_dropdown, table_dropdown, provider_dropdown, model_dropdown, prompt_template_input, sample_count_slider, output_mode_radio],
        outputs=[batch_status_markdown, output_table_header, output_table]
    )

    # -------------------------------------------------------------------------
    # Batch Execution -> Commits and Renders directly into Output Table
    # -------------------------------------------------------------------------
    def on_commit_batch(domain, table_name, provider, model, prompt_template,
                        output_mode, target_col, mode, limit_num, is_lightweight, sample_count,
                        progress=gr.Progress(track_tqdm=False)):
        if not domain or not table_name:
            gr.Warning("Select a valid Domain and Table first.")
            return "### ⚠️ Missing Target\n> Select a valid Domain and Table first.", gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
        if not model:
            gr.Warning("Select a valid model first.")
            return f"### ⚠️ Missing Model\n> Select a valid {provider} model first.", gr.update(), gr.update(), gr.update(), gr.update(), gr.update()

        sys_prompt = get_domain_system_prompt(domain)

        def cb(cur, total, detail):
            pct = (cur / total) if total else 0.5
            progress(pct, desc=detail)

        res = PlaygroundController.commit_batch_flow(
            domain=domain,
            table_name=table_name,
            provider=provider,
            model=model,
            system_prompt=sys_prompt,
            prompt_template=prompt_template,
            output_mode=output_mode,
            target_column=target_col,
            write_mode=mode,
            limit_rows=limit_num,
            is_lightweight=is_lightweight,
            progress_callback=cb
        )

        if res["status"] == "success":
            rows_done = res.get("rows_processed", 0)
            cols_done = ", ".join(res.get("columns_created", []))
            gr.Info(f"Batch completed: {rows_done} rows enriched ({cols_done})!")
            
            # Refresh Input Table
            in_info, in_df, in_pills = load_input_table(domain, table_name, lightweight=is_lightweight, sample_count=sample_count)
            
            out_hdr = f"#### 📤 Output Table: 💾 Batch Execution Committed ({rows_done} rows saved to `{table_name}`)"
            out_df = gr.update(
                headers=res.get("output_headers", []),
                datatype=["str"] * len(res.get("output_headers", [])),
                value=res.get("output_data", [])
            )
            return res["message"], in_info, in_df, in_pills, out_hdr, out_df
        else:
            gr.Error(res.get("message", "Batch execution failed"))
            return res.get("message", "Error"), gr.update(), gr.update(), gr.update(), "#### 📤 Output Table: ❌ Execution Failed", gr.update()

    commit_batch_btn.click(
        fn=on_commit_batch,
        inputs=[
            domain_dropdown, table_dropdown, provider_dropdown, model_dropdown,
            prompt_template_input, output_mode_radio, target_column_input, write_mode_radio,
            limit_rows_input, preview_mode_toggle, sample_count_slider
        ],
        outputs=[batch_status_markdown, input_table_header, input_table, available_columns_info, output_table_header, output_table]
    )

    # -------------------------------------------------------------------------
    # Undo Last Operation -> Reverts and Refreshes Both Tables
    # -------------------------------------------------------------------------
    def on_undo_batch(domain, table_name, is_lightweight, sample_count):
        clean_dir = domain.strip() if domain else "default"
        clean_tbl = table_name.strip() if table_name else "raw_assets"
        res = DBManager.undo_last_operation(clean_dir, clean_tbl)
        status_msg = res.get("message", "Undo completed.")
        prefix = "✅" if res.get("status") == "success" else ("ℹ️" if res.get("status") == "info" else "❌")
        batch_msg = f"#### Status: {prefix} {status_msg}"

        # Refresh input and output tables
        in_info, in_df, in_pills = load_input_table(clean_dir, clean_tbl, lightweight=is_lightweight, sample_count=sample_count)
        out_hdr = f"#### 📤 Output Table: ↩️ Reverted Schema ({status_msg})"
        
        # Load fresh table data for output table
        raw_res = DBManager.get_table_data(clean_dir, clean_tbl, limit=25, lightweight=is_lightweight)
        raw_cols = raw_res.get("columns", [])
        raw_data = raw_res.get("data", [])
        out_headers = ["Status"] + raw_cols
        out_data = [["↩️ Reverted"] + list(r) for r in raw_data]
        out_df = gr.update(
            headers=out_headers,
            datatype=["str"] * len(out_headers),
            value=out_data
        )

        return batch_msg, in_info, in_df, in_pills, out_hdr, out_df

    undo_batch_btn.click(
        fn=on_undo_batch,
        inputs=[domain_dropdown, table_dropdown, preview_mode_toggle, sample_count_slider],
        outputs=[batch_status_markdown, input_table_header, input_table, available_columns_info, output_table_header, output_table]
    )

    # -------------------------------------------------------------------------
    # Presets Wireup
    # -------------------------------------------------------------------------
    def on_apply_preset_cv():
        usr_p = "Analyze this image: {file_name}\n\nReturn a JSON object with exactly these keys:\n1. \"image_summary\": A concise 2-sentence description of the visual scene.\n2. \"detected_objects\": A comma-separated string (CSV) of all distinct objects visible in the image (e.g. \"car, person, tree, dog\").\n3. \"photo_type\": One of [\"landscape\", \"portrait\", \"document\", \"indoor\", \"macro\"]."
        return usr_p, "⚡ Auto-Split JSON Keys into Columns"

    def on_apply_preset_meta():
        usr_p = "Analyze the item: {file_name}\n\nExtract and return a JSON object with:\n- \"visual_summary\": 2-sentence factual overview.\n- \"object_tags\": Comma-separated list of key entities/objects.\n- \"dominant_colors\": Primary 3 colors as a CSV list.\n- \"confidence_score\": Estimated confidence level between 0.0 and 1.0."
        return usr_p, "⚡ Auto-Split JSON Keys into Columns"

    def on_apply_preset_art():
        usr_p = "Examine this image: {file_name}\n\nProvide a JSON response with:\n- \"curator_critique\": An evocative, sensory description of the scene and lighting.\n- \"poetic_haiku\": A 3-line evocative haiku capturing the atmosphere.\n- \"mood_palette\": Comma-separated list of emotional tones and vibes."
        return usr_p, "⚡ Auto-Split JSON Keys into Columns"

    def on_apply_preset_doc():
        usr_p = "Analyze the document: {file_name}\n\nContent:\n{content}\n\nExtract JSON containing:\n- \"doc_summary\": 2-3 sentence executive summary.\n- \"key_entities\": Comma-separated list of organizations, people, and locations.\n- \"action_items\": Comma-separated list of key requirements or dates."
        return usr_p, "⚡ Auto-Split JSON Keys into Columns"

    preset_cv_btn.click(
        fn=on_apply_preset_cv,
        outputs=[prompt_template_input, output_mode_radio]
    )
    preset_meta_btn.click(
        fn=on_apply_preset_meta,
        outputs=[prompt_template_input, output_mode_radio]
    )
    preset_art_btn.click(
        fn=on_apply_preset_art,
        outputs=[prompt_template_input, output_mode_radio]
    )
    preset_doc_btn.click(
        fn=on_apply_preset_doc,
        outputs=[prompt_template_input, output_mode_radio]
    )

    # -------------------------------------------------------------------------
    # Tab Synchronization
    # -------------------------------------------------------------------------
    if tab is not None:
        def on_tab_select(current_domain, current_table, is_lightweight, sample_count):
            latest_domains = DBManager.list_dirs() or ["default"]
            curr_settings = get_settings()
            dom = curr_settings.last_domain if curr_settings.last_domain in latest_domains else (
                current_domain if current_domain in latest_domains else latest_domains[0]
            )
            
            latest_tables = DBManager.list_tables(dom) or ["raw_assets"]
            tbl = curr_settings.last_table if curr_settings.last_table in latest_tables else (
                current_table if current_table in latest_tables else latest_tables[0]
            )

            info, df_update, pills = load_input_table(dom, tbl, lightweight=is_lightweight, sample_count=sample_count)
            
            return (
                gr.update(choices=latest_domains, value=dom),
                gr.update(choices=latest_tables, value=tbl),
                format_domain_prompt_banner(dom),
                info,
                df_update,
                pills
            )

        tab.select(
            fn=on_tab_select,
            inputs=[domain_dropdown, table_dropdown, preview_mode_toggle, sample_count_slider],
            outputs=[domain_dropdown, table_dropdown, domain_prompt_banner, input_table_header, input_table, available_columns_info]
        )
