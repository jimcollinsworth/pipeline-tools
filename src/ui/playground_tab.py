import gradio as gr
import pandas as pd
from src.core.config import get_settings, update_last_entry
from src.core.ollama_client import OllamaClient
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

    with gr.Column():
        gr.Markdown("### 🧪 Prompt Playground & Batch Model Execution")
        
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("#### 1. Target Data & Model")
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
                
                model_dropdown = gr.Dropdown(
                    label="Ollama Model",
                    choices=[settings.default_ollama_model],
                    value=settings.default_ollama_model,
                    allow_custom_value=True
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
                table_info_markdown = gr.Markdown("#### 📊 Selected Table Preview: *Loading...*")
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

                batch_status_markdown = gr.Markdown("#### Batch Status: *Idle*")

    # Helper to load table preview
    def load_table_preview(domain, table_name):
        if not domain or not table_name:
            return "⚠️ Select a valid Domain and Table.", gr.update(headers=["Notice"], value=[["No table selected"]])
        
        res = DBManager.get_table_data(domain, table_name, limit=10)
        if res.get("error"):
            return f"⚠️ **Table `{domain}.{table_name}` not found or empty.**", gr.update(headers=["Status"], value=[[res.get("error")]])
        
        cols = res.get("columns", [])
        data = res.get("data", [])
        total = res.get("total_rows", len(data))
        
        info_text = f"✅ **Table `{res.get('domain', domain)}.{res.get('table', table_name)}`** — Total Rows: **{total}** (showing first {len(data)})"
        return info_text, gr.update(headers=cols, datatype=["str"] * len(cols), value=data)

    # Auto-refresh and event handlers
    def on_domain_change(selected_domain):
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
        
        info_text, df_update = load_table_preview(domain_str, selected_tbl)
        return gr.update(choices=discovered_tables, value=selected_tbl), info_text, df_update

    def on_table_change(selected_table, current_domain):
        """Persist last table selection and refresh table preview."""
        if selected_table and selected_table.strip():
            tbl_str = selected_table.strip()
            update_last_entry(last_table=tbl_str)
            return load_table_preview(current_domain or "default", tbl_str)
        return "⚠️ Select a table name.", gr.update(headers=[], value=[])

    def on_test_sample(domain, table_name, model, system_prompt, prompt_template, sample_count):
        curr_settings = get_settings()
        if not domain or not table_name:
            return [["Error", "Domain and Table selection required.", "", "", ""]]
        if not model:
            return [["Error", "Ollama model selection required.", "", "", ""]]

        # Persist prompt inputs
        update_last_entry(
            last_domain=domain.strip(),
            last_table=table_name.strip(),
            default_ollama_model=model.strip(),
            last_system_prompt=system_prompt,
            last_user_prompt=prompt_template
        )

        try:
            results = PromptExecutor.run_sample_test(
                host=curr_settings.ollama_host,
                model=model,
                prompt_template=prompt_template,
                system_prompt=system_prompt,
                table_dir=domain.strip(),
                table_name=table_name.strip(),
                sample_count=int(sample_count)
            )
            rows = [
                [r["row_id"], r["file_name"], r["source_content"], r["prompt_rendered"], r["model_output"]]
                for r in results
            ]
            return rows
        except Exception as e:
            return [["Error", f"{type(e).__name__}: {str(e)}", "", "", ""]]

    def on_commit_batch(domain, table_name, model, system_prompt, prompt_template, target_col, mode, limit_num):
        curr_settings = get_settings()
        limit_val = int(limit_num) if limit_num and int(limit_num) > 0 else None
        
        update_last_entry(
            last_domain=domain.strip() if domain else "default",
            last_table=table_name.strip() if table_name else "raw_assets",
            default_ollama_model=model.strip() if model else curr_settings.default_ollama_model,
            last_system_prompt=system_prompt,
            last_user_prompt=prompt_template
        )

        try:
            res = PromptExecutor.apply_prompt_to_table(
                host=curr_settings.ollama_host,
                model=model,
                prompt_template=prompt_template,
                system_prompt=system_prompt,
                table_dir=domain.strip(),
                table_name=table_name.strip(),
                target_column=target_col.strip(),
                mode=mode,
                limit=limit_val
            )
            if res.get("status") == "success":
                info_text, df_update = load_table_preview(domain, table_name)
                return f"✅ **{res.get('message')}**", info_text, df_update
            else:
                return f"❌ **Error:**\n```\n{res.get('message')}\n```", gr.update(), gr.update()
        except Exception as e:
            return f"❌ **Execution Failed:**\n```\n{type(e).__name__}: {str(e)}\n```", gr.update(), gr.update()

    domain_dropdown.change(
        fn=on_domain_change,
        inputs=[domain_dropdown],
        outputs=[table_dropdown, table_info_markdown, current_table_preview]
    )

    table_dropdown.change(
        fn=on_table_change,
        inputs=[table_dropdown, domain_dropdown],
        outputs=[table_info_markdown, current_table_preview]
    )
    
    test_sample_btn.click(
        fn=on_test_sample,
        inputs=[domain_dropdown, table_dropdown, model_dropdown, system_prompt_input, prompt_template_input, sample_count_slider],
        outputs=[test_results_table]
    )

    commit_batch_btn.click(
        fn=on_commit_batch,
        inputs=[domain_dropdown, table_dropdown, model_dropdown, system_prompt_input, prompt_template_input, target_column_input, write_mode_radio, limit_rows_input],
        outputs=[batch_status_markdown, table_info_markdown, current_table_preview]
    )


