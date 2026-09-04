"""
Context & Memory Tab (Table-Level Knowledge Base & Governance)
=============================================================
This module renders the Context & Memory workbench tab.
Allows inspecting, editing, saving, and exporting {domain}_{table}_context.md memory files.
"""

import gradio as gr
from pathlib import Path
from src.core.config import get_settings
from src.core.context_manager import CONTEXT_PRESETS
from src.controllers.context_controller import ContextController

def render_context_tab(tab=None):
    """Render the Context & Memory workbench tab."""
    settings = get_settings()
    initial_domains = ContextController.get_domains()
    selected_domain = settings.last_domain if settings.last_domain in initial_domains else (initial_domains[0] if initial_domains else "default")
    initial_tables = ContextController.get_tables(selected_domain)
    selected_table = settings.last_table if settings.last_table in initial_tables else (initial_tables[0] if initial_tables else "")

    preset_names = list(CONTEXT_PRESETS.keys())
    default_preset = preset_names[0] if preset_names else "General Document Knowledge Synthesis"

    gr.Markdown(
        """
        ### 🧠 Context & Memory (Table-Level Compounding Knowledge Base)
        Maintain and inspect the evolving Markdown memory file (`{domain}_{table}_context.md`) for the selected table.
        The context file holds table system prompts, rules, active skills, canonical entity registers, and lessons learned.
        """
    )

    with gr.Row():
        with gr.Column(scale=3):
            domain_dropdown = gr.Dropdown(
                choices=initial_domains,
                value=selected_domain,
                label="Domain / Directory",
                info="Select the domain housing the target table.",
                allow_custom_value=True,
                filterable=True
            )
        with gr.Column(scale=4):
            table_dropdown = gr.Dropdown(
                choices=initial_tables,
                value=selected_table,
                label="Table Name",
                info="Select the table whose knowledge memory you wish to inspect or edit.",
                allow_custom_value=True,
                filterable=True
            )
        with gr.Column(scale=2):
            refresh_btn = gr.Button("🔄 Refresh Tables", variant="secondary", size="sm")

    with gr.Row():
        with gr.Column(scale=7):
            preset_dropdown = gr.Dropdown(
                choices=preset_names,
                value=default_preset,
                label="Context Strategy Preset",
                info="Predefined governance prompts outlining how context, entities, and citations are handled."
            )
        with gr.Column(scale=3):
            apply_preset_btn = gr.Button("⚡ Apply Preset to Context", variant="secondary")

    with gr.Row():
        file_info_md = gr.Markdown("*Loading context file info...*")

    # Full-width Markdown code editor
    context_editor = gr.Code(
        value="",
        language="markdown",
        lines=26,
        label="Context & Memory File Content",
        interactive=True
    )

    with gr.Row():
        with gr.Column(scale=3):
            save_btn = gr.Button("💾 Save Context to File", variant="primary")
        with gr.Column(scale=3):
            reload_btn = gr.Button("🔄 Reload from Disk", variant="secondary")
        with gr.Column(scale=4):
            export_index_btn = gr.Button("📑 Export Clean Index (index.md)", variant="secondary")

    status_md = gr.Markdown("💡 *Ready. Edit markdown directly above and click Save to persist to disk.*")
    download_file = gr.File(label="Exported Index File", visible=False)

    # --- Event Wiring ---

    def on_domain_change(domain):
        tables = ContextController.get_tables(domain)
        new_val = tables[0] if tables else ""
        return gr.update(choices=tables, value=new_val)

    def on_table_change(domain, table):
        if not table:
            return "", "⚠️ Select a table to view context.", "*No table selected*"
        return ContextController.handle_load_context(domain, table)

    def on_refresh_tables(current_domain):
        domains = ContextController.get_domains()
        c_dom = current_domain if current_domain in domains else (domains[0] if domains else "default")
        tables = ContextController.get_tables(c_dom)
        c_tbl = tables[0] if tables else ""
        return gr.update(choices=domains, value=c_dom), gr.update(choices=tables, value=c_tbl)

    def on_save_click(domain, table, content):
        return ContextController.handle_save_context(domain, table, content)

    def on_reload_click(domain, table):
        return ContextController.handle_load_context(domain, table)

    def on_apply_preset_click(preset_name, current_content):
        return ContextController.handle_apply_preset(preset_name, current_content)

    def on_export_index_click(domain, table, content):
        status, path_str = ContextController.handle_export_index(domain, table, content)
        if path_str:
            return status, gr.update(value=path_str, visible=True)
        return status, gr.update(visible=False)

    domain_dropdown.change(
        fn=on_domain_change,
        inputs=[domain_dropdown],
        outputs=[table_dropdown]
    )

    table_dropdown.change(
        fn=on_table_change,
        inputs=[domain_dropdown, table_dropdown],
        outputs=[context_editor, status_md, file_info_md]
    )

    refresh_btn.click(
        fn=on_refresh_tables,
        inputs=[domain_dropdown],
        outputs=[domain_dropdown, table_dropdown]
    )

    save_btn.click(
        fn=on_save_click,
        inputs=[domain_dropdown, table_dropdown, context_editor],
        outputs=[status_md, file_info_md]
    )

    reload_btn.click(
        fn=on_reload_click,
        inputs=[domain_dropdown, table_dropdown],
        outputs=[context_editor, status_md, file_info_md]
    )

    apply_preset_btn.click(
        fn=on_apply_preset_click,
        inputs=[preset_dropdown, context_editor],
        outputs=[context_editor, status_md]
    )

    export_index_btn.click(
        fn=on_export_index_click,
        inputs=[domain_dropdown, table_dropdown, context_editor],
        outputs=[status_md, download_file]
    )

    # Initial load if table is pre-selected
    if selected_domain and selected_table:
        init_content, init_status, init_file_info = ContextController.handle_load_context(selected_domain, selected_table)
        context_editor.value = init_content
        status_md.value = init_status
        file_info_md.value = init_file_info

    # If tab is passed, sync tables and load context on tab select
    if tab:
        def on_tab_select(current_domain, current_table):
            domains = ContextController.get_domains()
            curr_settings = get_settings()
            c_dom = curr_settings.last_domain if curr_settings.last_domain in domains else (
                current_domain if current_domain in domains else (domains[0] if domains else "default")
            )
            tables = ContextController.get_tables(c_dom)
            c_tbl = curr_settings.last_table if curr_settings.last_table in tables else (
                current_table if current_table in tables else (tables[0] if tables else "")
            )
            if c_dom and c_tbl:
                content, status, file_info = ContextController.handle_load_context(c_dom, c_tbl)
            else:
                content = ""
                status = f"ℹ️ Domain '{c_dom}' selected. No tables found." if c_dom else "⚠️ Please select a Domain and Table."
                file_info = "*No table selected*"

            return (
                gr.update(choices=domains, value=c_dom),
                gr.update(choices=tables, value=c_tbl),
                content,
                status,
                file_info
            )

        tab.select(
            fn=on_tab_select,
            inputs=[domain_dropdown, table_dropdown],
            outputs=[domain_dropdown, table_dropdown, context_editor, status_md, file_info_md]
        )
