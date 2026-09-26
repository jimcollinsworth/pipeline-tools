import gradio as gr
import pandas as pd
from src.core.config import get_settings, save_settings, Settings, get_domain_system_prompt, set_domain_system_prompt
from src.core.ollama_client import OllamaClient
from src.core.gemini_client import GeminiClient
from src.db.manager import DBManager

def render_settings_tab(tab=None):
    settings = get_settings()
    domains = DBManager.list_dirs() or ["default"]
    if "default" not in domains:
        domains.insert(0, "default")
    initial_domain = settings.last_domain if settings.last_domain in domains else domains[0]

    # Pre-flight check Ollama on initial render
    ollama_client = OllamaClient(host=settings.ollama_host)
    ollama_ok, ollama_msg = ollama_client.check_connection()
    if ollama_ok:
        raw_ollama_models = ollama_client.list_models()
        ollama_models_data = [
            [m["name"], m["size"], m["family"], m["parameter_size"], m["quantization"], m["modified_at"]]
            for m in raw_ollama_models
        ]
        ollama_model_names = [m["name"] for m in raw_ollama_models]
        def_ollama = settings.default_ollama_model if settings.default_ollama_model in ollama_model_names else (ollama_model_names[0] if ollama_model_names else "")
        initial_ollama_status = ollama_msg
    else:
        ollama_models_data = []
        ollama_model_names = []
        def_ollama = ""
        initial_ollama_status = f"❌ {ollama_msg}"

    with gr.Column():
        gr.Markdown("### ⚙️ Engine Settings & Multi-Provider LLM Configuration")
        gr.Markdown("Manage local Ollama instance, Google Gemini API keys, default models, and storage directories.")

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
                    value=initial_ollama_status,
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
                    value=ollama_models_data,
                    interactive=False,
                    wrap=True,
                    max_height=200
                )
                default_ollama_dropdown = gr.Dropdown(
                    label="Default Ollama Model",
                    choices=ollama_model_names,
                    value=def_ollama,
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
                        m.get("input_window", "1M tokens"),
                        m.get("output_limit", "8K tokens"),
                        m.get("cost_tier", "Standard"),
                        m.get("description", "")
                    ]
                    for m in models_list
                ]
                gemini_models_table = gr.Dataframe(
                    headers=["Model Identifier", "Modalities", "Context Window", "Max Output", "Cost Tier", "Capabilities & Description"],
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
        from src.core.config import normalize_ollama_host, update_last_entry
        clean_host = normalize_ollama_host(host)
        client = OllamaClient(host=clean_host)
        ok, msg = client.check_connection()
        if not ok:
            gr.Error(msg)
            return clean_host, msg, [], gr.update(choices=[], value="")
        
        models = client.list_models()
        if not models:
            gr.Warning(f"{msg} (No models found)")
            return clean_host, f"{msg} (No models found)", [], gr.update(choices=[], value="")
        
        rows = [
            [m["name"], m["size"], m["family"], m["parameter_size"], m["quantization"], m["modified_at"]]
            for m in models
        ]
        names = [m["name"] for m in models]
        curr_settings = get_settings()
        selected = curr_settings.default_ollama_model if curr_settings.default_ollama_model in names else (names[0] if names else "")
        update_last_entry(ollama_host=clean_host)
        gr.Info(f"Connected to Ollama! Saved host: {clean_host}")
        return clean_host, msg, rows, gr.update(choices=names, value=selected)

    def test_gemini_key(api_key):
        client = GeminiClient(api_key=api_key)
        ok, msg = client.check_connection(api_key=api_key)
        if ok:
            models = client.list_models(api_key=api_key)
            rows = [
                [
                    m.get("name", ""),
                    m.get("modalities", "Text, Vision"),
                    m.get("input_window", "1M tokens"),
                    m.get("output_limit", "8K tokens"),
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
        from src.core.config import normalize_ollama_host
        curr = get_settings()
        clean_host = normalize_ollama_host(host)
        updated = Settings(
            ollama_host=clean_host,
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
            last_user_prompt=curr.last_user_prompt,
            domain_system_prompts=curr.domain_system_prompts
        )
        save_settings(updated)
        gr.Info("Settings saved successfully!")
        return "✅ **All settings saved successfully!**"

    test_ollama_btn.click(
        fn=test_and_fetch_ollama,
        inputs=[ollama_host_input],
        outputs=[ollama_host_input, ollama_status_box, ollama_models_table, default_ollama_dropdown]
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

    if tab is not None:
        def on_settings_tab_select():
            curr = get_settings()
            client = OllamaClient(host=curr.ollama_host)
            ok, msg = client.check_connection()
            if ok:
                models = client.list_models()
                rows = [
                    [m["name"], m["size"], m["family"], m["parameter_size"], m["quantization"], m["modified_at"]]
                    for m in models
                ]
                names = [m["name"] for m in models]
                val = curr.default_ollama_model if curr.default_ollama_model in names else (names[0] if names else "")
                return curr.ollama_host, msg, rows, gr.update(choices=names, value=val)
            else:
                return curr.ollama_host, f"❌ {msg}", [], gr.update(choices=[], value="")

        tab.select(
            fn=on_settings_tab_select,
            inputs=[],
            outputs=[ollama_host_input, ollama_status_box, ollama_models_table, default_ollama_dropdown]
        )

