import gradio as gr
import pandas as pd
from src.core.config import get_settings, update_last_entry
from src.db.manager import DBManager

def render_tables_tab():
    settings = get_settings()

    domains = DBManager.list_dirs()
    if not domains:
        domains = ["default"]
    initial_domain = settings.last_domain if settings.last_domain in domains else domains[0]

    tables = DBManager.list_tables(initial_domain)
    if not tables:
        tables = ["raw_assets"]
    initial_table = settings.last_table if settings.last_table in tables else tables[0]

    with gr.Column():
        gr.Markdown("### 📊 Pixeltable DataTables & Inspector")
        
        with gr.Row():
            domain_dropdown = gr.Dropdown(
                label="Domain / Directory",
                choices=domains,
                value=initial_domain,
                allow_custom_value=True,
                scale=2
            )
            table_dropdown = gr.Dropdown(
                label="Table Name",
                choices=tables,
                value=initial_table,
                allow_custom_value=True,
                scale=2
            )
            limit_slider = gr.Slider(minimum=5, maximum=200, value=50, step=5, label="Max Rows to Fetch", scale=2)
            lightweight_toggle = gr.Checkbox(label="⚡ Lightweight Preview", value=True, scale=1)
            load_table_btn = gr.Button("🔍 Load / Refresh Table", variant="primary", scale=1)

        table_stats_markdown = gr.Markdown("#### Table Stats: *Click 'Load / Refresh Table' or select a table to view data.*")

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

    def on_domain_change(domain, limit, is_lightweight):
        if not domain:
            return gr.update(choices=[], value=""), "⚠️ Select a domain.", gr.update(headers=[], value=[])
        clean_dir = domain.strip()
        update_last_entry(last_domain=clean_dir)
        tables_list = DBManager.list_tables(clean_dir)
        if not tables_list:
            tables_list = ["raw_assets"]
        
        curr_settings = get_settings()
        selected_tbl = curr_settings.last_table if curr_settings.last_table in tables_list else tables_list[0]
        stats_text, df_update = on_load_table(clean_dir, selected_tbl, limit, is_lightweight)
        return gr.update(choices=tables_list, value=selected_tbl), stats_text, df_update

    domain_dropdown.change(
        fn=on_domain_change,
        inputs=[domain_dropdown, limit_slider, lightweight_toggle],
        outputs=[table_dropdown, table_stats_markdown, data_view_table]
    )

    table_dropdown.change(
        fn=on_load_table,
        inputs=[domain_dropdown, table_dropdown, limit_slider, lightweight_toggle],
        outputs=[table_stats_markdown, data_view_table]
    )

    load_table_btn.click(
        fn=on_load_table,
        inputs=[domain_dropdown, table_dropdown, limit_slider, lightweight_toggle],
        outputs=[table_stats_markdown, data_view_table]
    )

    lightweight_toggle.change(
        fn=on_load_table,
        inputs=[domain_dropdown, table_dropdown, limit_slider, lightweight_toggle],
        outputs=[table_stats_markdown, data_view_table]
    )


