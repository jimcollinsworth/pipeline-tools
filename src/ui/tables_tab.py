import gradio as gr
import pandas as pd
from src.core.config import get_settings, update_last_entry
from src.db.manager import DBManager

def render_tables_tab():
    settings = get_settings()

    with gr.Column():
        gr.Markdown("### 📊 Pixeltable DataTables & Inspector")
        
        with gr.Row():
            domain_input = gr.Textbox(label="Domain / Directory", value=settings.last_domain, scale=2)
            table_input = gr.Textbox(label="Table Name", value=settings.last_table, scale=2)
            limit_slider = gr.Slider(minimum=5, maximum=200, value=50, step=5, label="Max Rows to Fetch", scale=2)
            lightweight_toggle = gr.Checkbox(label="⚡ Lightweight Preview", value=True, scale=1)
            load_table_btn = gr.Button("🔍 Load / Refresh Table", variant="primary", scale=1)

        table_stats_markdown = gr.Markdown("#### Table Stats: *Click 'Load / Refresh Table' to view data.*")

        data_view_table = gr.Dataframe(
            headers=["Column 1", "Column 2", "Column 3"],
            value=[],
            interactive=False,
            wrap=True
        )

    def on_load_table(domain, table_name, limit, is_lightweight=True):
        if not domain or not table_name:
            return "⚠️ Please provide both Domain and Table name.", gr.update(headers=[], value=[])

        clean_dir = domain.strip() if domain else "default"
        clean_tbl = table_name.strip() if table_name else "raw_assets"
        update_last_entry(last_domain=clean_dir, last_table=clean_tbl)

        res = DBManager.get_table_data(clean_dir, clean_tbl, limit=int(limit), lightweight=is_lightweight)
        if res.get("error"):
            return f"❌ **Error loading table `{clean_dir}.{clean_tbl}`:**\n```\n{res.get('error')}\n```", gr.update(headers=["Error"], value=[[res.get('error')]])

        cols = res.get("columns", [])
        data = res.get("data", [])
        total = res.get("total_rows", len(data))
        mode_label = "⚡ Lightweight" if is_lightweight else "🔍 Full"

        stats_text = f"✅ **Table `{res.get('domain', clean_dir)}.{res.get('table', clean_tbl)}`** ({mode_label}) — Displaying {len(data)} of {total} total rows.\nColumns: `{', '.join(cols)}`"
        return stats_text, gr.update(headers=cols, datatype=["str"] * len(cols), value=data)

    load_table_btn.click(
        fn=on_load_table,
        inputs=[domain_input, table_input, limit_slider, lightweight_toggle],
        outputs=[table_stats_markdown, data_view_table]
    )

    lightweight_toggle.change(
        fn=on_load_table,
        inputs=[domain_input, table_input, limit_slider, lightweight_toggle],
        outputs=[table_stats_markdown, data_view_table]
    )

