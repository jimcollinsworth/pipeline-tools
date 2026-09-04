import gradio as gr
import pandas as pd
from src.core.config import get_settings, save_settings, Settings
from src.core.ollama_client import OllamaClient
from src.core.gemini_client import GeminiClient

def render_settings_tab(tab=None):
    settings = get_settings()

    with gr.Column():
        gr.Markdown("### ⚙️ Engine Settings & Multi-Provider LLM Configuration")
        
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("#### 🦙 Local Ollama Settings")
                ollama_host_input = gr.Textbox(
                    label="Ollama Server URL",
                    value=settings.ollama_host,
                    placeholder="http://localhost:11434"
                )
                ollama_status_box = gr.Textbox(
                    label="Ollama Status",
                    value="Not checked",
                    interactive=False
                )
                test_ollama_btn = gr.Button("🔄 Test Ollama Connection", variant="secondary")

                gr.Markdown("---")
                gr.Markdown("#### ✨ Google Gemini Settings")
                gemini_key_input = gr.Textbox(
                    label="Gemini API Key",
                    value=settings.gemini_api_key or "",
                    type="password",
                    placeholder="Enter your Gemini API key (AIzaSy...)"
                )
                gemini_status_box = gr.Textbox(
                    label="Gemini Status",
                    value="Ready to test" if settings.gemini_api_key else "Key not set",
                    interactive=False
                )
                with gr.Row():
                    test_gemini_btn = gr.Button("✨ Test Gemini Connection", variant="secondary")

                gr.Markdown("---")
                gr.Markdown("#### 🎯 Active Default Provider")
                default_provider_radio = gr.Radio(
                    choices=["Ollama", "Gemini"],
                    value=settings.default_provider or "Ollama",
                    label="Default Provider for Playground"
                )

                gr.Markdown("---")
                gr.Markdown("#### 📁 Storage Directories")
                pixeltable_dir_input = gr.Textbox(
                    label="Pixeltable Data Directory",
                    value=settings.pixeltable_dir
                )
                export_dir_input = gr.Textbox(
                    label="Default Export Output Directory",
                    value=settings.export_dir
                )

                save_all_btn = gr.Button("💾 Save All Settings", variant="primary")
                save_status_box = gr.Markdown("")

            with gr.Column(scale=2):
                gr.Markdown("#### 🦙 Installed Ollama Models")
                ollama_models_table = gr.Dataframe(
                    headers=["Name", "Size", "Family", "Parameters", "Quantization", "Modified"],
                    datatype=["str", "str", "str", "str", "str", "str"],
                    value=[],
                    interactive=False,
                    wrap=True,
                    max_height=200
                )
                default_ollama_dropdown = gr.Dropdown(
                    label="Default Ollama Model",
                    choices=[settings.default_ollama_model],
                    value=settings.default_ollama_model,
                    allow_custom_value=True
                )

                gr.Markdown("---")
                gr.Markdown("#### ✨ Available Google Gemini Models")
                gemini_client = GeminiClient(api_key=settings.gemini_api_key)
                models_list = gemini_client.list_models()
                gemini_models_data = [
                    [
                        m.get("name", ""),
                        m.get("modalities", "Text, Vision"),
                        m.get("input_window", "1,048,576"),
                        m.get("output_limit", "8,192"),
                        m.get("cost_tier", "Standard"),
                        m.get("description", "")
                    ]
                    for m in models_list
                ]
                gemini_models_table = gr.Dataframe(
                    headers=["Model Identifier", "Modalities", "Context Window (t)", "Max Output (t)", "Cost Tier", "Capabilities & Description"],
                    datatype=["str", "str", "str", "str", "str", "str"],
                    value=gemini_models_data,
                    interactive=False,
                    wrap=True,
                    max_height=240
                )
                default_gemini_dropdown = gr.Dropdown(
                    label="Default Gemini Model",
                    choices=[m["name"] for m in models_list],
                    value=settings.default_gemini_model or "gemini-3.6-flash",
                    allow_custom_value=True
                )

    # Event handlers
    def test_and_fetch_ollama(host):
        client = OllamaClient(host=host)
        ok, msg = client.check_connection()
        if not ok:
            gr.Error(msg)
            return msg, [], gr.update(choices=[])
        
        models = client.list_models()
        if not models:
            gr.Warning(f"{msg} (No models found)")
            return f"{msg} (No models found)", [], gr.update(choices=[])
        
        rows = [
            [m["name"], m["size"], m["family"], m["parameter_size"], m["quantization"], m["modified_at"]]
            for m in models
        ]
        names = [m["name"] for m in models]
        curr_settings = get_settings()
        selected = curr_settings.default_ollama_model if curr_settings.default_ollama_model in names else (names[0] if names else "")
        gr.Info("Connected to Ollama successfully!")
        return msg, rows, gr.update(choices=names, value=selected)

    def test_gemini_key(api_key):
        client = GeminiClient(api_key=api_key)
        ok, msg = client.check_connection(api_key=api_key)
        if ok:
            models = client.list_models(api_key=api_key)
            rows = [
                [
                    m.get("name", ""),
                    m.get("modalities", "Text, Vision"),
                    m.get("input_window", "1,048,576"),
                    m.get("output_limit", "8,192"),
                    m.get("cost_tier", "Standard"),
                    m.get("description", "")
                ]
                for m in models
            ]
            names = [m["name"] for m in models]
            curr_settings = get_settings()
            selected = curr_settings.default_gemini_model if curr_settings.default_gemini_model in names else (names[0] if names else "gemini-3.6-flash")
            gr.Info(f"Connected to Google Gemini! Discovered {len(models)} models.")
            return msg, rows, gr.update(choices=names, value=selected)
        else:
            gr.Error(msg)
            return msg, gr.update(), gr.update()


    def on_save_settings(host, def_ollama, gemini_key, def_gemini, def_provider, pt_dir, exp_dir):
        curr = get_settings()
        updated = Settings(
            ollama_host=host.strip(),
            default_ollama_model=def_ollama.strip() if def_ollama else "llama3.2",
            gemini_api_key=gemini_key.strip() if gemini_key else None,
            default_gemini_model=def_gemini.strip() if def_gemini else "gemini-3.6-flash",
            default_provider=def_provider,
            pixeltable_dir=pt_dir.strip(),
            export_dir=exp_dir.strip(),
            last_provider=def_provider,
            last_domain=curr.last_domain,
            last_table=curr.last_table,
            last_system_prompt=curr.last_system_prompt,
            last_user_prompt=curr.last_user_prompt
        )
        save_settings(updated)
        gr.Info("Settings saved successfully!")
        return "✅ **All settings saved successfully!**"

    test_ollama_btn.click(
        fn=test_and_fetch_ollama,
        inputs=[ollama_host_input],
        outputs=[ollama_status_box, ollama_models_table, default_ollama_dropdown]
    )

    test_gemini_btn.click(
        fn=test_gemini_key,
        inputs=[gemini_key_input],
        outputs=[gemini_status_box, gemini_models_table, default_gemini_dropdown]
    )

    save_all_btn.click(
        fn=on_save_settings,
        inputs=[
            ollama_host_input,
            default_ollama_dropdown,
            gemini_key_input,
            default_gemini_dropdown,
            default_provider_radio,
            pixeltable_dir_input,
            export_dir_input
        ],
        outputs=[save_status_box]
    )
