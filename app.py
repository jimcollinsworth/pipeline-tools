import sys
import gradio as gr
from src.ui.settings_tab import render_settings_tab
from src.ui.ingest_tab import render_ingest_tab
from src.ui.playground_tab import render_playground_tab
from src.ui.tables_tab import render_tables_tab

def create_app():
    custom_css = """
    .gradio-container { max-width: 95% !important; width: 95% !important; margin: auto; }
    .tabitem { width: 100% !important; min-width: 100% !important; }
    """
    
    with gr.Blocks(title="Pipeline Tools - Multimodal Workbench") as demo:
        gr.Markdown(
            """
            # 🚀 Multimodal Pipeline Tools & Prompt Workbench
            *Declarative Ingestion (Pixeltable), LLM Prompt Iteration, and Metadata Export Engine*
            """
        )
        
        with gr.Tabs():
            with gr.Tab("📂 Ingestion & Scanner"):
                render_ingest_tab()
                
            with gr.Tab("🧪 Prompt Playground"):
                render_playground_tab()
                
            with gr.Tab("📊 Lineage & DataTables"):
                render_tables_tab()
                
            with gr.Tab("⚙️ Settings & Models"):
                render_settings_tab()

    return demo

if __name__ == "__main__":
    app = create_app()
    port = 7860
    try:
        app.launch(
            server_name="127.0.0.1",
            server_port=port,
            show_error=True,
            theme=gr.themes.Soft(),
            css=".gradio-container { max-width: 95% !important; margin: auto; }"
        )
    except OSError as e:
        if "7860" in str(e) or "port" in str(e).lower():
            print(f"\n❌ ERROR: Port {port} is already in use!")
            print(f"ℹ️ An instance of Pipeline Tools is already running on http://127.0.0.1:{port}")
            print(f"💡 Open http://127.0.0.1:{port} in your browser, or stop the existing process to launch a new one.\n")
            sys.exit(1)
        else:
            raise e
