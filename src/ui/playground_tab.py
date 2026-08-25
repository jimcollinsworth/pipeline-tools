import gradio as gr
import pandas as pd
from src.core.config import get_settings
from src.core.ollama_client import OllamaClient
from src.db.manager import DBManager
from src.prompts.executor import PromptExecutor

def render_playground_tab():
    settings = get_settings()

    with gr.Column():
        gr.Markdown("### 🧪 Prompt Playground & Batch Model Execution")
        
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("#### 1. Target Data & Model")
                domain_input = gr.Textbox(label="Domain / Directory", value="default")
                table_input = gr.Textbox(label="Table Name", value="raw_assets")
                
                model_dropdown = gr.Dropdown(
                    label="Ollama Model",
                    choices=[settings.default_ollama_model],
                    value=settings.default_ollama_model,
                    allow_custom_value=True
                )
                refresh_models_btn = gr.Button("🔄 Refresh Model List", size="sm")

                gr.Markdown("#### 2. System & Prompt Configuration")
                system_prompt_input = gr.Textbox(
                    label="System Prompt",
                    value="You are a helpful AI assistant extracting entities, summaries, and key metadata from documents.",
                    lines=2
                )
                
                prompt_template_input = gr.Textbox(
                    label="User Prompt Template",
                    value="Analyze the following document:\nFile: {file_name}\n\nContent:\n{content}\n\nProvide a 2-sentence summary and extract top 3 key entities as JSON.",
                    lines=6
                )
                gr.Markdown("*Tip: Use `{file_name}`, `{content}`, `{rel_path}`, `{modality}` placeholders to inject row values.*")

                gr.Markdown("#### 3. Test on Sample Rows")
                sample_count_slider = gr.Slider(minimum=1, maximum=10, value=2, step=1, label="Number of Test Rows")
                test_sample_btn = gr.Button("🚀 Run Test on Sample Rows", variant="primary")

            with gr.Column(scale=2):
                gr.Markdown("#### 4. Sample Test Results Preview")
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

    # Event handlers
    def refresh_models():
        curr_settings = get_settings()
        client = OllamaClient(host=curr_settings.ollama_host)
        models = client.list_models()
        names = [m["name"] for m in models] if models else [curr_settings.default_ollama_model]
        curr_val = curr_settings.default_ollama_model if curr_settings.default_ollama_model in names else (names[0] if names else "")
        return gr.update(choices=names, value=curr_val)

    def on_test_sample(domain, table_name, model, system_prompt, prompt_template, sample_count):
        curr_settings = get_settings()
        if not domain or not table_name:
            return [["Error", "Domain/Table required", "", "", ""]]
        if not model:
            return [["Error", "Model required", "", "", ""]]

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
            return [["Error", str(e), "", "", ""]]

    def on_commit_batch(domain, table_name, model, system_prompt, prompt_template, target_col, mode, limit_num):
        curr_settings = get_settings()
        limit_val = int(limit_num) if limit_num and int(limit_num) > 0 else None
        
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
                return f"✅ **{res.get('message')}**"
            else:
                return f"❌ **Error:** {res.get('message')}"
        except Exception as e:
            return f"❌ **Execution failed:** {str(e)}"

    refresh_models_btn.click(fn=refresh_models, outputs=[model_dropdown])
    
    test_sample_btn.click(
        fn=on_test_sample,
        inputs=[domain_input, table_input, model_dropdown, system_prompt_input, prompt_template_input, sample_count_slider],
        outputs=[test_results_table]
    )

    commit_batch_btn.click(
        fn=on_commit_batch,
        inputs=[domain_input, table_input, model_dropdown, system_prompt_input, prompt_template_input, target_column_input, write_mode_radio, limit_rows_input],
        outputs=[batch_status_markdown]
    )
