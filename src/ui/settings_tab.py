import gradio as gr
import pandas as pd
from src.core.config import get_settings, save_settings, Settings
from src.core.ollama_client import OllamaClient

def render_settings_tab():
    settings = get_settings()

    with gr.Column():
        gr.Markdown("### ⚙️ Engine Settings & LLM Configuration")
        
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("#### Local Ollama Settings")
                ollama_host_input = gr.Textbox(
                    label="Ollama Server URL",
                    value=settings.ollama_host,
                    placeholder="http://localhost:11434"
                )
                ollama_status_box = gr.Textbox(
                    label="Connection Status",
                    value="Not checked",
                    interactive=False
                )
                with gr.Row():
                    test_conn_btn = gr.Button("🔄 Test Connection & Fetch Models", variant="primary")
                    save_btn = gr.Button("💾 Save Settings", variant="secondary")

                gr.Markdown("#### Cloud Providers (Roadmap)")
                gemini_key_input = gr.Textbox(
                    label="Gemini API Key (Optional)",
                    value=settings.gemini_api_key or "",
                    type="password",
                    placeholder="AIzaSy..."
                )

                gr.Markdown("#### Storage Directories")
                pixeltable_dir_input = gr.Textbox(
                    label="Pixeltable Data Directory",
                    value=settings.pixeltable_dir
                )
                export_dir_input = gr.Textbox(
                    label="Default Export Output Directory",
                    value=settings.export_dir
                )

            with gr.Column(scale=2):
                gr.Markdown("#### 🦙 Installed Ollama Models")
                models_table = gr.Dataframe(
                    headers=["Name", "Size", "Family", "Parameters", "Quantization", "Modified"],
                    datatype=["str", "str", "str", "str", "str", "str"],
                    value=[],
                    interactive=False,
                    wrap=True
                )
                default_model_dropdown = gr.Dropdown(
                    label="Active / Default Model for Prompts",
                    choices=[settings.default_ollama_model],
                    value=settings.default_ollama_model,
                    allow_custom_value=True
                )

    # Event handlers
    def test_and_fetch_models(host):
        client = OllamaClient(host=host)
        ok, msg = client.check_connection()
        if not ok:
            return msg, [], gr.update(choices=[])
        
        models = client.list_models()
        if not models:
            return f"{msg} (No models found)", [], gr.update(choices=[])
        
        rows = [
            [m["name"], m["size"], m["family"], m["parameter_size"], m["quantization"], m["modified_at"]]
            for m in models
        ]
        names = [m["name"] for m in models]
        curr_settings = get_settings()
        selected = curr_settings.default_ollama_model if curr_settings.default_ollama_model in names else (names[0] if names else "")
        return msg, rows, gr.update(choices=names, value=selected)

    def on_save_settings(host, default_model, gemini_key, pt_dir, exp_dir):
        s = Settings(
            ollama_host=host.strip(),
            default_ollama_model=default_model.strip() if default_model else "llama3.2",
            gemini_api_key=gemini_key.strip() if gemini_key else None,
            pixeltable_dir=pt_dir.strip(),
            export_dir=exp_dir.strip()
        )
        save_settings(s)
        return "Settings saved successfully!"

    test_conn_btn.click(
        fn=test_and_fetch_models,
        inputs=[ollama_host_input],
        outputs=[ollama_status_box, models_table, default_model_dropdown]
    )

    save_btn.click(
        fn=on_save_settings,
        inputs=[ollama_host_input, default_model_dropdown, gemini_key_input, pixeltable_dir_input, export_dir_input],
        outputs=[ollama_status_box]
    )
