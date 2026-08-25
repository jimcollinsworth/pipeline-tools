import gradio as gr
import pandas as pd
from src.db.manager import DBManager

def render_tables_tab():
    with gr.Column():
        gr.Markdown("### 📊 Pixeltable DataTables & Inspector")
        
        with gr.Row():
            domain_input = gr.Textbox(label="Domain / Directory", value="default", scale=2)
            table_input = gr.Textbox(label="Table Name", value="raw_assets", scale=2)
            limit_slider = gr.Slider(minimum=5, maximum=200, value=50, step=5, label="Max Rows to Fetch", scale=2)
            load_table_btn = gr.Button("🔍 Load / Refresh Table", variant="primary", scale=1)

        table_stats_markdown = gr.Markdown("#### Table Stats: *Click 'Load / Refresh Table' to view data.*")

        data_view_table = gr.Dataframe(
            headers=["Column 1", "Column 2", "Column 3"],
            value=[],
            interactive=False,
            wrap=True
        )


    def on_load_table(domain, table_name, limit):
        if not domain or not table_name:
            return "⚠️ Please provide both Domain and Table name.", gr.update(headers=[], value=[])

        res = DBManager.get_table_data(domain.strip(), table_name.strip(), limit=int(limit))
        if res.get("error"):
            return f"❌ Error loading table `{domain}.{table_name}`: {res.get('error')}", gr.update(headers=[], value=[])

        cols = res.get("columns", [])
        data = res.get("data", [])
        total = res.get("total_rows", len(data))

        stats_text = f"✅ **Table `{domain}.{table_name}`** — Displaying {len(data)} of {total} total rows. Columns: `{', '.join(cols)}`"
        return stats_text, gr.update(headers=cols, datatype=["str"] * len(cols), value=data)

    load_table_btn.click(
        fn=on_load_table,
        inputs=[domain_input, table_input, limit_slider],
        outputs=[table_stats_markdown, data_view_table]
    )
