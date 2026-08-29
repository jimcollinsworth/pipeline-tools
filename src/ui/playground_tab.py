import gradio as gr
import pandas as pd
from src.core.config import get_settings, update_last_entry
from src.core.llm_service import LLMService
from src.db.manager import DBManager
from src.prompts.executor import PromptExecutor

def render_playground_tab():
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

    with gr.Column():
        gr.Markdown("### 🧪 Prompt Playground & Batch Model Execution")
        
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
                gr.Markdown("*Tip: Use `{file_name}`, `{content}`, `{rel_path}`, `{modality}` placeholders to inject row values.*")

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
                    value=[],
                    interactive=False,
                    wrap=True,
                    max_height=260
                )

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
                gr.Markdown("#### 5. Apply & Save to Table Column")
                with gr.Row():
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
                        label="Row Limit (0 for all rows in table)",
                        value=0,
                        precision=0,
                        scale=1
                    )
                    commit_batch_btn = gr.Button("💾 Execute on Table & Save Column", variant="stop", scale=2)

                with gr.Group(elem_classes=["status-panel"]):
                    batch_status_markdown = gr.Markdown("#### Batch Status: *Idle*")

    # Helper to load table preview
    def load_table_preview(domain, table_name, lightweight=True):
        if not domain or not table_name:
            return "⚠️ Select a valid Domain and Table.", gr.update(headers=["Notice"], value=[["No table selected"]])
        
        res = DBManager.get_table_data(domain, table_name, limit=10, lightweight=lightweight)
        if res.get("error"):
            return f"⚠️ **Table `{domain}.{table_name}` not found or empty.**", gr.update(headers=["Status"], value=[[res.get("error")]])
        
        cols = res.get("columns", [])
        data = res.get("data", [])
        total = res.get("total_rows", len(data))
        mode_label = "⚡ Lightweight" if lightweight else "🔍 Full"
        
        info_text = f"✅ **Table `{res.get('domain', domain)}.{res.get('table', table_name)}`** ({mode_label}) — Total Rows: **{total}** (showing first {len(data)})"
        return info_text, gr.update(headers=cols, datatype=["str"] * len(cols), value=data)

    # Auto-refresh and event handlers
    def on_provider_change(selected_provider):
        models = LLMService.list_models_for_provider(selected_provider)
        curr = get_settings()
        if selected_provider == "Gemini":
            chosen = curr.default_gemini_model if curr.default_gemini_model in models else (models[0] if models else "gemini-3.6-flash")
        else:
            chosen = curr.default_ollama_model if curr.default_ollama_model in models else (models[0] if models else "llama3.2")
        update_last_entry(last_provider=selected_provider, last_model=chosen)
        return gr.update(choices=models, value=chosen)

    def on_domain_change(selected_domain, is_lightweight):
        """Auto-populate tables when domain selection changes and refresh table preview."""
        if not selected_domain:
            return gr.update(choices=[], value=""), "⚠️ Select a valid Domain.", gr.update(headers=[], value=[])
        domain_str = selected_domain.strip()
        update_last_entry(last_domain=domain_str)
        
        discovered_tables = DBManager.list_tables(domain_str)
        if not discovered_tables:
            discovered_tables = ["raw_assets"]
        
        curr_settings = get_settings()
        selected_tbl = curr_settings.last_table if curr_settings.last_table in discovered_tables else discovered_tables[0]
        
        info_text, df_update = load_table_preview(domain_str, selected_tbl, lightweight=is_lightweight)
        return gr.update(choices=discovered_tables, value=selected_tbl), info_text, df_update

    def on_table_change(selected_table, current_domain, is_lightweight):
        """Persist last table selection and refresh table preview."""
        if selected_table and selected_table.strip():
            tbl_str = selected_table.strip()
            update_last_entry(last_table=tbl_str)
            return load_table_preview(current_domain or "default", tbl_str, lightweight=is_lightweight)
        return "⚠️ Select a table name.", gr.update(headers=[], value=[])

    def on_test_sample(domain, table_name, provider, model, system_prompt, prompt_template, sample_count,
                       progress=gr.Progress(track_tqdm=True)):
        if not domain or not table_name:
            gr.Warning("Domain and Table selection required.")
            return [["Error", "Domain and Table selection required.", "", "", ""]]
        if not model:
            gr.Warning("Model selection required.")
            return [["Error", f"{provider} model selection required.", "", "", ""]]

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
                progress_callback=cb
            )
            rows = [
                [r["row_id"], r["file_name"], r["source_content"], r["prompt_rendered"], r["model_output"]]
                for r in results
            ]
            gr.Info(f"Evaluated {len(results)} sample rows with [{provider}] {model} successfully!")
            return rows
        except Exception as e:
            err_msg = f"{type(e).__name__}: {str(e)}"
            gr.Error(f"Sample test failed: {err_msg}")
            return [["Error", err_msg, "", "", ""]]

    def on_commit_batch(domain, table_name, provider, model, system_prompt, prompt_template, target_col, mode, limit_num, is_lightweight,
                        progress=gr.Progress(track_tqdm=True)):
        if not domain or not table_name:
            gr.Warning("Select a valid Domain and Table first.")
            yield "### ⚠️ Missing Target\n> Select a valid Domain and Table before running batch execution.", gr.update(), gr.update()
            return
        if not model:
            gr.Warning("Select a valid model first.")
            yield f"### ⚠️ Missing Model\n> Select a valid {provider} model before running batch execution.", gr.update(), gr.update()
            return

        limit_val = int(limit_num) if limit_num and int(limit_num) > 0 else None
        clean_dir = domain.strip()
        clean_tbl = table_name.strip()
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
        yield f"⏳ **[1/2] Initializing Batch Execution...** Running [{provider}] `{model}` on `{clean_dir}.{clean_tbl}`{limit_desc}...", gr.update(), gr.update()

        def cb(cur, total, detail):
            pct = (cur / total) if total else 0.5
            progress(pct, desc=detail)

        try:
            yield f"⏳ **[2/2] Generating [{provider}] LLM Outputs & Updating Column `{clean_col}`...**", gr.update(), gr.update()
            res = PromptExecutor.apply_prompt_to_table(
                provider=provider,
                model=model,
                prompt_template=prompt_template,
                system_prompt=system_prompt,
                table_dir=clean_dir,
                table_name=clean_tbl,
                target_column=clean_col,
                mode=mode,
                limit=limit_val,
                progress_callback=cb
            )
            if res.get("status") == "success":
                info_text, df_update = load_table_preview(clean_dir, clean_tbl, lightweight=is_lightweight)
                gr.Info(f"Batch completed: {res.get('count')} rows updated in column '{res.get('column')}'")
                yield (
                    f"### ✅ Batch Execution Complete!\n"
                    f"> **Table:** `{clean_dir}.{clean_tbl}`\n"
                    f"> **Provider & Model:** [{provider}] `{model}`\n"
                    f"> **Target Column:** `{res.get('column')}` ({mode} mode)\n"
                    f"> **Rows Processed:** {res.get('count')}\n\n"
                    f"*Column updated in Pixeltable. Check updated preview on the right.*",
                    info_text,
                    df_update
                )
            else:
                err_msg = res.get("message", "Unknown error")
                gr.Error(f"Batch execution failed: {err_msg}")
                yield f"### ❌ Batch Run Failed\n> **Error:**\n```\n{err_msg}\n```", gr.update(), gr.update()
        except Exception as e:
            err_msg = f"{type(e).__name__}: {str(e)}"
            gr.Error(f"Batch execution error: {err_msg}")
            yield f"### ❌ Execution Exception\n```\n{err_msg}\n```", gr.update(), gr.update()

    provider_dropdown.change(
        fn=on_provider_change,
        inputs=[provider_dropdown],
        outputs=[model_dropdown]
    )

    domain_dropdown.change(
        fn=on_domain_change,
        inputs=[domain_dropdown, preview_mode_toggle],
        outputs=[table_dropdown, table_info_markdown, current_table_preview]
    )

    table_dropdown.change(
        fn=on_table_change,
        inputs=[table_dropdown, domain_dropdown, preview_mode_toggle],
        outputs=[table_info_markdown, current_table_preview]
    )

    preview_mode_toggle.change(
        fn=load_table_preview,
        inputs=[domain_dropdown, table_dropdown, preview_mode_toggle],
        outputs=[table_info_markdown, current_table_preview]
    )
    
    test_sample_btn.click(
        fn=on_test_sample,
        inputs=[domain_dropdown, table_dropdown, provider_dropdown, model_dropdown, system_prompt_input, prompt_template_input, sample_count_slider],
        outputs=[test_results_table]
    )

    commit_batch_btn.click(
        fn=on_commit_batch,
        inputs=[domain_dropdown, table_dropdown, provider_dropdown, model_dropdown, system_prompt_input, prompt_template_input, target_column_input, write_mode_radio, limit_rows_input, preview_mode_toggle],
        outputs=[batch_status_markdown, table_info_markdown, current_table_preview]
    )


