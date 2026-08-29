import sys
import gradio as gr
from src.ui.settings_tab import render_settings_tab
from src.ui.ingest_tab import render_ingest_tab
from src.ui.playground_tab import render_playground_tab
from src.ui.tables_tab import render_tables_tab

def create_app():
    # Monochromatic Technical / Bauhaus Theme
    mono_theme = gr.themes.Monochrome(
        primary_hue=gr.themes.colors.neutral,
        secondary_hue=gr.themes.colors.neutral,
        neutral_hue=gr.themes.colors.neutral,
        text_size="sm",
        radius_size="none",
        font=[gr.themes.GoogleFont("JetBrains Mono"), "SF Mono", "Consolas", "monospace"],
        font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "Consolas", "monospace"]
    ).set(
        body_background_fill="#f3f0e8",
        body_background_fill_dark="#121212",
        block_background_fill="#faf8f5",
        block_background_fill_dark="#181818",
        block_border_width="1.5px",
        block_border_color="#1a1a1a",
        block_border_color_dark="#333333",
        button_primary_background_fill="#111111",
        button_primary_background_fill_hover="#333333",
        button_primary_text_color="#ffffff",
        button_primary_border_color="#111111",
        button_secondary_background_fill="#faf8f5",
        button_secondary_background_fill_hover="#eae7df",
        button_secondary_text_color="#111111",
        button_secondary_border_color="#1a1a1a",
        input_background_fill="#ffffff",
        input_border_color="#1a1a1a",
        input_border_width="1.5px",
        table_border_color="#1a1a1a",
        table_row_focus="#eae7df"
    )

    custom_css = """
    /* Full-Width Layout & Monochromatic Architecture */
    body, gradio-app, .gradio-container {
        max-width: 98% !important;
        width: 98% !important;
        margin: 8px auto !important;
        background-color: #f3f0e8 !important;
        font-family: 'JetBrains Mono', 'SF Mono', 'Consolas', monospace !important;
        color: #111111 !important;
    }
    
    .tabitem, .tabs, .tab-nav {
        width: 100% !important;
        min-width: 100% !important;
    }

    /* Minimalist Header */
    .app-header {
        border-bottom: 2px solid #111111;
        padding-bottom: 10px;
        margin-bottom: 16px;
    }
    .app-header h1 {
        font-size: 1.6rem !important;
        font-weight: 800 !important;
        letter-spacing: -0.5px !important;
        text-transform: uppercase !important;
        margin-bottom: 2px !important;
    }
    .app-header p {
        font-size: 0.85rem !important;
        color: #555555 !important;
        margin: 0 !important;
    }

    /* Architectural Monospace Tabs */
    .tab-nav {
        border-bottom: 1.5px solid #1a1a1a !important;
        gap: 6px !important;
        padding-bottom: 4px !important;
        margin-bottom: 16px !important;
    }
    .tab-nav button {
        font-family: 'JetBrains Mono', monospace !important;
        font-weight: 700 !important;
        font-size: 0.82rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.6px !important;
        border: 1.5px solid #1a1a1a !important;
        border-radius: 2px !important;
        background: #faf8f5 !important;
        color: #1a1a1a !important;
        padding: 6px 16px !important;
        transition: all 0.15s ease !important;
    }
    .tab-nav button.selected, .tab-nav button[aria-selected="true"] {
        background: #111111 !important;
        color: #ffffff !important;
        border: 1.5px solid #111111 !important;
    }
    .tab-nav button:hover:not(.selected) {
        background: #e8e4dc !important;
    }

    /* Monochromatic Card Containers & Status Panels */
    .status-panel, .card-box {
        margin-top: 16px !important;
        padding: 14px 18px !important;
        border-radius: 2px !important;
        border: 1.5px solid #1a1a1a !important;
        background: #faf8f5 !important;
        min-height: 80px !important;
        box-shadow: 2px 2px 0px #1a1a1a !important;
    }
    .progress-level {
        margin-bottom: 16px !important;
    }

    /* Buttons */
    button.primary, button[variant="primary"] {
        background: #111111 !important;
        color: #ffffff !important;
        border: 1.5px solid #111111 !important;
        border-radius: 2px !important;
        font-weight: 700 !important;
        font-family: 'JetBrains Mono', monospace !important;
        text-transform: uppercase !important;
        letter-spacing: 0.6px !important;
        box-shadow: 2px 2px 0px #333333 !important;
    }
    button.primary:hover {
        background: #2a2a2a !important;
        box-shadow: 1px 1px 0px #111111 !important;
    }
    button.secondary, button[variant="secondary"] {
        background: #faf8f5 !important;
        color: #111111 !important;
        border: 1.5px solid #1a1a1a !important;
        border-radius: 2px !important;
        font-weight: 700 !important;
        font-family: 'JetBrains Mono', monospace !important;
        text-transform: uppercase !important;
        letter-spacing: 0.6px !important;
    }
    button.secondary:hover {
        background: #eae6dd !important;
    }
    button.stop, button[variant="stop"] {
        background: #111111 !important;
        color: #ffffff !important;
        border: 1.5px solid #111111 !important;
        border-radius: 2px !important;
        font-weight: 700 !important;
        font-family: 'JetBrains Mono', monospace !important;
        text-transform: uppercase !important;
        letter-spacing: 0.6px !important;
        box-shadow: 2px 2px 0px #111111 !important;
    }

    /* Inputs, Dropdowns, Checkboxes */
    input, textarea, select, .gr-input, .gr-dropdown {
        border: 1.5px solid #1a1a1a !important;
        border-radius: 2px !important;
        background: #ffffff !important;
        color: #111111 !important;
        font-family: 'JetBrains Mono', monospace !important;
    }
    
    /* Clean High-Contrast Data Tables */
    .gr-dataframe, table {
        border: 1.5px solid #1a1a1a !important;
        border-radius: 2px !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.84rem !important;
        background: #ffffff !important;
    }
    th {
        background: #eae7df !important;
        border-bottom: 1.5px solid #1a1a1a !important;
        color: #111111 !important;
        font-weight: 700 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.4px !important;
        font-size: 0.8rem !important;
    }
    td {
        border-bottom: 1px solid #e5e1d7 !important;
        color: #111111 !important;
    }
    """
    
    with gr.Blocks(title="Pipeline Tools // Multimodal Workbench", theme=mono_theme, css=custom_css) as demo:
        gr.Markdown(
            """
            <div class="app-header">
                <h1>⬛ PIPELINE TOOLS // MULTIMODAL WORKBENCH</h1>
                <p>Declarative Pixeltable Ingestion • Multi-Provider Prompt Engineering (Ollama / Gemini) • Lineage Inspector</p>
            </div>
            """
        )
        
        with gr.Tabs():
            with gr.Tab("Ingestion & Scanner"):
                render_ingest_tab()
                
            with gr.Tab("Prompt Playground"):
                render_playground_tab()
                
            with gr.Tab("Lineage & DataTables"):
                render_tables_tab()
                
            with gr.Tab("Settings & Models"):
                render_settings_tab()

    return demo

demo = create_app()

if __name__ == "__main__":
    port = 7860
    try:
        demo.launch(
            server_name="127.0.0.1",
            server_port=port,
            show_error=True
        )
    except OSError as e:
        if "7860" in str(e) or "port" in str(e).lower():
            print(f"\n❌ ERROR: Port {port} is already in use!")
            print(f"ℹ️ An instance of Pipeline Tools is already running on http://127.0.0.1:{port}")
            print(f"💡 Open http://127.0.0.1:{port} in your browser, or stop the existing process to launch a new one.\n")
            sys.exit(1)
        else:
            raise e

