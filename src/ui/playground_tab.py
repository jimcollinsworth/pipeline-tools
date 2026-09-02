"""
Data Enhancement Tab (Prompt Workbench & Batch Execution Engine)
================================================================
This module renders the Data Enhancement workbench for testing and applying LLM prompts
across Pixeltable datasets.

Key Architectural Principles & Workflow:
----------------------------------------
1. Interactive Single-Row Preview (Fast Iteration):
   - Allows users to select a sample row, customize prompt templates with dynamic `{column}`
     placeholders, and test prompt generation instantly against Ollama or Gemini.
2. Auto-Split JSON Column Generation:
   - When enabled, the LLM is instructed to return structured JSON.
   - Keys are parsed, scalar/nested types are inferred (`pxt.String`, `pxt.Int`, `pxt.Float`,
     `pxt.Json`, `pxt.Bool`), and separate columns are dynamically created on the Pixeltable table.
3. 1-Click Rollback / Undo:
   - Each batch execution records the added columns into `DBManager._operation_history`.
   - The user can cleanly undo the last batch run with 1 click, dropping the newly created columns.
4. Decoupled WebSocket Event Listeners:
   - `domain_dropdown.change` only updates `table_dropdown`.
   - `table_dropdown.change` loads the table data once, preventing Svelte re-render loops.
"""

import os
import gradio as gr
import pandas as pd
from pathlib import Path
from src.core.config import get_settings, update_last_entry
from src.core.llm_service import LLMService
from src.db.manager import DBManager
from src.prompts.executor import PromptExecutor
from src.controllers.playground_controller import PlaygroundController
from src.controllers.tables_controller import TablesController

def render_playground_tab(tab=None):
    """Render the Data Enhancement prompt workbench and batch execution tab."""
    settings = get_settings()

    # Discover initial domains and tables
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
    initial_model = settings.last_model if settings.last_model in initial_models else (initial_models[0] if initial_models else "gemini-3.6-flash")

    # Discover initial table columns for placeholder hints
    initial_table_res = DBManager.get_table_data(initial_domain, initial_table, limit=1, lightweight=True)
    initial_cols = initial_table_res.get("columns", [])
    initial_pills = ", ".join([f"`{{{c}}}`" for c in initial_cols if c != "media_preview"]) if initial_cols else "*None*"
    initial_cols_text = f"💡 **Available Column Placeholders:** {initial_pills} | Standard: `{{file_name}}`, `{{content}}`, `{{rel_path}}`, `{{modality}}`, `{{file_size}}`"

    with gr.Column():
        gr.Markdown("### 🧪 Data Enhancement (Prompt Workbench & Batch Execution)")
        
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("#### 1. Target Data & LLM Engine")
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
                
                with gr.Row():
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

                gr.Markdown("#### 2. System & Prompt Configuration")
                
                with gr.Accordion("💡 Prompt Guide & Example Presets (Click to Apply)", open=False):
                    gr.Markdown(
                        """
                        **How Prompts Work with Pixeltable**:
                        * **System Prompt**: Defines the AI persona, tone, and behavioral constraints across all rows.
                        * **User Prompt**: Supplies row variables (`{file_name}`, `{content}`, `{rel_path}`, `{modality}`).
                        * **⚡ Auto-Split Mode**: Any top-level keys in the JSON response automatically become individual table columns!
                        """
                    )
                    with gr.Row():
                        preset_cv_btn = gr.Button("🖼️ Image Summary + CSV Objects", size="sm")
                        preset_meta_btn = gr.Button("🔍 Precision Metadata", size="sm")
                    with gr.Row():
                        preset_art_btn = gr.Button("🎨 Creative Curator", size="sm")
                        preset_doc_btn = gr.Button("📄 Document Intelligence", size="sm")

                system_prompt_input = gr.Textbox(
                    label="System Prompt",
                    value=settings.last_system_prompt,
                    lines=2
                )
                
                prompt_template_input = gr.Textbox(
                    label="User Prompt Template",
                    value=settings.last_user_prompt,
                    lines=6
                )
                
                available_columns_info = gr.Markdown(initial_cols_text)

                gr.Markdown("#### 3. Test on Sample Rows")
                sample_count_slider = gr.Slider(minimum=1, maximum=10, value=2, step=1, label="Number of Test Rows")
                test_sample_btn = gr.Button("🚀 Run Test on Sample Rows", variant="primary")

            with gr.Column(scale=2):
                # Section 4: Live Table Data Preview
                with gr.Row():
                    table_info_markdown = gr.Markdown("#### 📊 Selected Table Preview: *Select a table to inspect*", scale=3)
                    preview_mode_toggle = gr.Checkbox(label="⚡ Lightweight Preview", value=True, scale=1)

                current_table_preview = gr.Dataframe(
                    headers=["file_name", "modality", "content", "file_size"],
                    datatype=["str", "str", "str", "str"],
                    value=[],
                    interactive=False,
                    wrap=True,
                    max_height=260
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

                gr.Markdown("---")
                gr.Markdown("#### 🧪 Sample Test Results Preview")
                test_results_table = gr.Dataframe(
                    headers=["Row ID", "File Name", "Source Snippet", "Rendered Prompt", "Model Output"],
                    datatype=["str", "str", "str", "str", "str"],
                    value=[],
                    interactive=False,
                    wrap=True
                )

                gr.Markdown("---")
                gr.Markdown("#### 5. Apply & Save to Table Columns")
                with gr.Row():
                    output_mode_radio = gr.Radio(
                        choices=["⚡ Auto-Split JSON Keys into Columns", "📄 Single Target Column"],
                        value="⚡ Auto-Split JSON Keys into Columns",
                        label="Output Mode",
                        scale=3
                    )
                
                with gr.Row(visible=False) as single_col_row:
                    target_column_input = gr.Textbox(
                        label="Target Column Name",
                        value="llm_summary",
                        placeholder="e.g. llm_summary, entities, tags",
                        scale=2
                    )
                    write_mode_radio = gr.Radio(
                        choices=["replace", "append"],
                        value="replace",
                        label="Write Mode",
                        scale=1
                    )

                with gr.Row():
                    limit_rows_input = gr.Number(
                        label="Max Rows (0 = all)",
                        value=0,
                        precision=0,
                        scale=1
                    )
                    commit_batch_btn = gr.Button("💾 Execute on Table & Save Columns", variant="primary", scale=2)
                    undo_batch_btn = gr.Button("↩️ Undo Last Operation", variant="secondary", scale=1)

                with gr.Group(elem_classes=["status-panel"]):
                    batch_status_markdown = gr.Markdown("#### Batch Status: *Idle*")

    # Helper to load table preview and available columns
    def load_table_preview(domain, table_name, lightweight=True):
        res = PlaygroundController.load_table_preview(domain, table_name, lightweight=lightweight)
        return res["stats_text"], gr.update(headers=res["columns"], datatype=res["datatypes"], value=res["data"]), res["placeholders_text"]

    def on_output_mode_change(selected_mode):
        is_single = (selected_mode == "📄 Single Target Column")
        return gr.update(visible=is_single)

    output_mode_radio.change(
        fn=on_output_mode_change,
        inputs=[output_mode_radio],
        outputs=[single_col_row]
    )

    # Auto-refresh and event handlers
    def on_provider_change(selected_provider):
        res = PlaygroundController.handle_provider_change(selected_provider)
        return gr.update(choices=res["choices"], value=res["value"])

    def on_domain_change(selected_domain):
        """Auto-populate tables when domain selection changes."""
        res = PlaygroundController.handle_domain_change(selected_domain)
        return gr.update(choices=res["choices"], value=res["value"])

    def on_table_change(selected_table, current_domain, is_lightweight):
        """Persist last table selection and refresh table preview."""
        if selected_table and selected_table.strip():
            tbl_str = selected_table.strip()
            update_last_entry(last_table=tbl_str)
            return load_table_preview(current_domain or "default", tbl_str, lightweight=is_lightweight)
        return "⚠️ Select a table name.", gr.update(headers=[], value=[]), "💡 **Available Column Placeholders:** *None*"

    def on_select_preview_row(evt: gr.SelectData, current_df, domain, table_name):
        """Populate Media Inspector in Data Enhancement tab when a table row is clicked without re-querying the database."""
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

    def on_test_sample(domain, table_name, provider, model, system_prompt, prompt_template, sample_count, output_mode,
                       progress=gr.Progress(track_tqdm=True)):
        if not domain or not table_name:
            gr.Warning("Domain and Table selection required.")
            return gr.update(headers=["Error"], value=[["Domain and Table selection required."]])
        if not model:
            gr.Warning("Model selection required.")
            return gr.update(headers=["Error"], value=[[f"{provider} model selection required."]])

        # Persist prompt inputs
        update_last_entry(
            last_domain=domain.strip(),
            last_table=table_name.strip(),
            last_provider=provider,
            last_model=model.strip(),
            last_system_prompt=system_prompt,
            last_user_prompt=prompt_template
        )

        def cb(cur, total, detail):
            pct = (cur / total) if total else 0.5
            progress(pct, desc=detail)

        is_auto_split = (output_mode == "⚡ Auto-Split JSON Keys into Columns")

        try:
            progress(0.1, desc=f"Evaluating prompt on {sample_count} sample rows with [{provider}] {model}...")
            results = PromptExecutor.run_sample_test(
                provider=provider,
                model=model,
                prompt_template=prompt_template,
                system_prompt=system_prompt,
                table_dir=domain.strip(),
                table_name=table_name.strip(),
                sample_count=int(sample_count),
                auto_split=is_auto_split,
                progress_callback=cb
            )

            if is_auto_split:
                # Discover all extracted JSON keys across sample rows
                all_keys = []
                for r in results:
                    for k in r.get("extracted_columns", []):
                        if k not in all_keys:
                            all_keys.append(k)

                if all_keys:
                    headers = ["Row ID", "File Name"] + all_keys
                    rows = []
                    for r in results:
                        parsed = r.get("parsed_json", {})
                        row_vals = [r["row_id"], r["file_name"]] + [str(parsed.get(k, "")) for k in all_keys]
                        rows.append(row_vals)
                    gr.Info(f"Evaluated {len(results)} rows: Extracted {len(all_keys)} dynamic columns ({', '.join(all_keys)})!")
                    return gr.update(headers=headers, datatype=["str"] * len(headers), value=rows)

            # Fallback to standard single output table
            headers = ["Row ID", "File Name", "Source Snippet", "Rendered Prompt", "Model Output"]
            rows = [
                [r["row_id"], r["file_name"], r["source_content"], r["prompt_rendered"], r["model_output"]]
                for r in results
            ]
            gr.Info(f"Evaluated {len(results)} sample rows with [{provider}] {model} successfully!")
            return gr.update(headers=headers, datatype=["str"] * len(headers), value=rows)
        except Exception as e:
            err_msg = f"{type(e).__name__}: {str(e)}"
            gr.Error(f"Sample test failed: {err_msg}")
            return gr.update(headers=["Error"], value=[[err_msg]])

    def on_commit_batch(domain, table_name, provider, model, system_prompt, prompt_template,
                        output_mode, target_col, mode, limit_num, is_lightweight,
                        progress=gr.Progress(track_tqdm=True)):
        if not domain or not table_name:
            gr.Warning("Select a valid Domain and Table first.")
            yield "### ⚠️ Missing Target\n> Select a valid Domain and Table before running batch execution.", gr.update(), gr.update(), gr.update()
            return
        if not model:
            gr.Warning("Select a valid model first.")
            yield f"### ⚠️ Missing Model\n> Select a valid {provider} model before running batch execution.", gr.update(), gr.update(), gr.update()
            return

        limit_val = int(limit_num) if limit_num and int(limit_num) > 0 else None
        clean_dir = domain.strip()
        clean_tbl = table_name.strip()
        is_auto_split = (output_mode == "⚡ Auto-Split JSON Keys into Columns")
        clean_col = target_col.strip() if target_col else "llm_summary"

        update_last_entry(
            last_domain=clean_dir,
            last_table=clean_tbl,
            last_provider=provider,
            last_model=model.strip(),
            last_system_prompt=system_prompt,
            last_user_prompt=prompt_template
        )

        limit_desc = f" (Limit: {limit_val} rows)" if limit_val else " (All rows)"
        mode_desc = "Auto-Splitting JSON Keys" if is_auto_split else f"Single Column `{clean_col}`"
        yield f"⏳ **[1/2] Initializing Batch Execution ({mode_desc})...** Running [{provider}] `{model}` on `{clean_dir}.{clean_tbl}`{limit_desc}...", gr.update(), gr.update(), gr.update()

        def cb(cur, total, detail):
            pct = (cur / total) if total else 0.5
            progress(pct, desc=detail)

        try:
            res = PromptExecutor.apply_prompt_to_table(
                provider=provider,
                model=model.strip(),
                prompt_template=prompt_template,
                system_prompt=system_prompt,
                table_dir=clean_dir,
                table_name=clean_tbl,
                target_column=clean_col,
                mode=mode,
                limit=limit_val,
                auto_split=is_auto_split,
                progress_callback=cb
            )

            if res.get("status") == "success":
                cols_created = res.get("columns", [clean_col])
                cols_msg = f"Columns Created / Updated: `{', '.join(cols_created)}`"
                status_msg = (
                    f"### ✅ Batch Execution Completed Successfully!\n"
                    f"- **Table:** `{clean_dir}.{clean_tbl}`\n"
                    f"- **Rows Processed:** {res.get('rows_processed', 0)}\n"
                    f"- **Engine:** [{provider}] `{model}`\n"
                    f"- **{cols_msg}**\n"
                    f"- **Operation:** `{mode.upper()}` mode\n"
                )
                gr.Info(f"Batch completed: {res.get('rows_processed', 0)} rows updated!")
                # Refresh table view and available columns
                info_text, df_update, cols_text = load_table_preview(clean_dir, clean_tbl, lightweight=is_lightweight)
                yield status_msg, info_text, df_update, cols_text
            else:
                err_msg = res.get("message", "Unknown error during batch execution")
                gr.Error(f"Batch execution failed: {err_msg}")
                yield f"### ❌ Batch Execution Failed\n```\n{err_msg}\n```", gr.update(), gr.update(), gr.update()

        except Exception as e:
            err_msg = f"{type(e).__name__}: {str(e)}"
            gr.Error(f"Batch execution exception: {err_msg}")
            yield f"### ❌ Batch Execution Error\n```\n{err_msg}\n```", gr.update(), gr.update(), gr.update()

    # Wire event listeners
    provider_dropdown.change(
        fn=on_provider_change,
        inputs=[provider_dropdown],
        outputs=[model_dropdown]
    )

    domain_dropdown.change(
        fn=on_domain_change,
        inputs=[domain_dropdown],
        outputs=[table_dropdown]
    )

    table_dropdown.change(
        fn=on_table_change,
        inputs=[table_dropdown, domain_dropdown, preview_mode_toggle],
        outputs=[table_info_markdown, current_table_preview, available_columns_info]
    )

    preview_mode_toggle.change(
        fn=load_table_preview,
        inputs=[domain_dropdown, table_dropdown, preview_mode_toggle],
        outputs=[table_info_markdown, current_table_preview, available_columns_info]
    )

    current_table_preview.select(
        fn=on_select_preview_row,
        inputs=[current_table_preview, domain_dropdown, table_dropdown],
        outputs=[pg_media_inspector_group, pg_inspector_image, pg_inspector_audio, pg_inspector_video, pg_inspector_details, pg_inspector_content]
    )

    pg_close_inspector_btn.click(
        fn=lambda: gr.update(visible=False),
        outputs=[pg_media_inspector_group]
    )
    
    test_sample_btn.click(
        fn=on_test_sample,
        inputs=[domain_dropdown, table_dropdown, provider_dropdown, model_dropdown, system_prompt_input, prompt_template_input, sample_count_slider, output_mode_radio],
        outputs=[test_results_table]
    )

    def on_apply_preset_cv():
        sys_p = "Process media records and extract visual scene descriptions, comma-separated object detection tags, and scene classifications. Always output a strict, parseable JSON object matching the requested schema."
        usr_p = "Analyze this image: {file_name}\n\nReturn a JSON object with exactly these keys:\n1. \"image_summary\": A concise 2-sentence description of the visual scene.\n2. \"detected_objects\": A comma-separated string (CSV) of all distinct objects visible in the image (e.g. \"car, person, tree, dog\").\n3. \"photo_type\": One of [\"landscape\", \"portrait\", \"document\", \"indoor\", \"macro\"]."
        return sys_p, usr_p, "⚡ Auto-Split JSON Keys into Columns"

    def on_apply_preset_meta():
        sys_p = "Extract precise multimodal metadata, visual summaries, categorical entity tags, and dominant color taxonomies. Always return a strict JSON payload matching the requested keys."
        usr_p = "Analyze the item: {file_name}\n\nExtract and return a JSON object with:\n- \"visual_summary\": 2-sentence factual overview.\n- \"object_tags\": Comma-separated list of key entities/objects.\n- \"dominant_colors\": Primary 3 colors as a CSV list.\n- \"confidence_score\": Estimated confidence level between 0.0 and 1.0."
        return sys_p, usr_p, "⚡ Auto-Split JSON Keys into Columns"

    def on_apply_preset_art():
        sys_p = "Analyze visual and aesthetic attributes including lighting direction, color temperature, atmospheric composition, and sensory descriptors. Return structured JSON matching the requested keys."
        usr_p = "Examine this image: {file_name}\n\nProvide a JSON response with:\n- \"curator_critique\": An evocative, sensory description of the scene and lighting.\n- \"poetic_haiku\": A 3-line evocative haiku capturing the atmosphere.\n- \"mood_palette\": Comma-separated list of emotional tones and vibes."
        return sys_p, usr_p, "⚡ Auto-Split JSON Keys into Columns"

    def on_apply_preset_doc():
        sys_p = "Extract factual document intelligence including key entities (organizations, individuals, locations), executive summaries, and action items. Maintain zero hallucination and return valid JSON."
        usr_p = "Analyze the document: {file_name}\n\nContent:\n{content}\n\nExtract JSON containing:\n- \"doc_summary\": 2-3 sentence executive summary.\n- \"key_entities\": Comma-separated list of organizations, people, and locations.\n- \"action_items\": Comma-separated list of key requirements or dates."
        return sys_p, usr_p, "⚡ Auto-Split JSON Keys into Columns"

    preset_cv_btn.click(
        fn=on_apply_preset_cv,
        outputs=[system_prompt_input, prompt_template_input, output_mode_radio]
    )
    preset_meta_btn.click(
        fn=on_apply_preset_meta,
        outputs=[system_prompt_input, prompt_template_input, output_mode_radio]
    )
    preset_art_btn.click(
        fn=on_apply_preset_art,
        outputs=[system_prompt_input, prompt_template_input, output_mode_radio]
    )
    preset_doc_btn.click(
        fn=on_apply_preset_doc,
        outputs=[system_prompt_input, prompt_template_input, output_mode_radio]
    )

    commit_batch_btn.click(
        fn=on_commit_batch,
        inputs=[domain_dropdown, table_dropdown, provider_dropdown, model_dropdown, system_prompt_input, prompt_template_input, output_mode_radio, target_column_input, write_mode_radio, limit_rows_input, preview_mode_toggle],
        outputs=[batch_status_markdown, table_info_markdown, current_table_preview, available_columns_info]
    )

    def on_undo_batch(domain, table_name, is_lightweight):
        clean_dir = domain.strip() if domain else "default"
        clean_tbl = table_name.strip() if table_name else "raw_assets"
        res = DBManager.undo_last_operation(clean_dir, clean_tbl)
        status_msg = res.get("message", "Undo completed.")
        prefix = "✅" if res.get("status") == "success" else ("ℹ️" if res.get("status") == "info" else "❌")
        batch_msg = f"#### Batch Status: {prefix} {status_msg}"
        info_text, df_update, cols_text = load_table_preview(clean_dir, clean_tbl, lightweight=is_lightweight)
        return batch_msg, info_text, df_update, cols_text

    undo_batch_btn.click(
        fn=on_undo_batch,
        inputs=[domain_dropdown, table_dropdown, preview_mode_toggle],
        outputs=[batch_status_markdown, table_info_markdown, current_table_preview, available_columns_info]
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
