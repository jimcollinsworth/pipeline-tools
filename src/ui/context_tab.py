"""
Context View Tab
================
Interactive UI for inspecting accumulated ingestion knowledge, managing domain-level
system prompts, and exporting canonical knowledge registers with YAML/JSON-LD metadata.
"""

import gradio as gr
from src.controllers.context_controller import ContextController
from src.core.config import get_settings
from src.db.manager import DBManager


def render_context_tab(tab=None):
    """Render the Context View tab inside Gradio Blocks."""
    curr_settings = get_settings()
    available_domains = DBManager.list_dirs() or ["default"]
    default_dom = curr_settings.last_domain if curr_settings.last_domain in available_domains else available_domains[0]
    initial_tables = DBManager.list_tables(default_dom) or ["raw_assets"]
    default_tbl = curr_settings.last_table if curr_settings.last_table in initial_tables else initial_tables[0]

    gr.Markdown(
        """
        ### 🧠 Context & Knowledge Register
        Inspect and govern accumulated cross-row entities, canonical aliases, and domain knowledge.
        Manage the domain system prompt and export structured Markdown registers.
        """
    )

    with gr.Row():
        domain_dropdown = gr.Dropdown(
            choices=available_domains,
            value=default_dom,
            label="Domain / Directory",
            interactive=True,
            scale=2
        )
        table_dropdown = gr.Dropdown(
            choices=initial_tables,
            value=default_tbl,
            label="Table Name",
            interactive=True,
            scale=2
        )
        refresh_context_btn = gr.Button("🔄 Refresh Context", variant="secondary", scale=1)

    # 1. Domain System Prompt Editor
    with gr.Group():
        gr.Markdown("#### 🎯 Domain System Prompt (LLM Governance)")
        gr.Markdown(
            "*This prompt guides model behavior and entity extraction across all row enhancements in this domain.*"
        )
        initial_prompt = ContextController.get_domain_system_prompt(default_dom)
        system_prompt_input = gr.Textbox(
            value=initial_prompt,
            label="Active Domain System Prompt",
            lines=4,
            placeholder="Enter governance rules, extraction instructions, or /slash commands for this domain..."
        )
        with gr.Row():
            save_system_prompt_btn = gr.Button("💾 Save System Prompt", variant="primary", scale=1)
            prompt_status_box = gr.Markdown("#### Status: *Ready.*", scale=3)

    # 2. Accumulated Entity Knowledge State
    with gr.Group():
        gr.Markdown("#### 🏷️ Canonical Entity Register")
        context_status_badge = gr.Markdown("Loading context summary...")
        entity_dataframe = gr.Dataframe(
            headers=["Canonical Entity", "Category", "Occurrences", "Referencing Documents"],
            datatype=["str", "str", "number", "str"],
            value=[],
            label="Discovered & Normalized Entities",
            interactive=False,
            wrap=True
        )

    # 3. Full Markdown Knowledge Register View
    with gr.Accordion("📄 Full Ingestion Knowledge Register (YAML + JSON-LD)", open=False):
        register_preview = gr.Markdown("No register loaded.")

    # 4. Export Knowledge Register
    with gr.Group():
        with gr.Row():
            export_context_btn = gr.Button("⚡ Export Context Markdown", variant="primary", scale=2)
            export_file_download = gr.File(label="📥 Download Exported Register", interactive=False, scale=2)
        export_status_box = gr.Markdown("#### Export Status: *Ready to export.*")

    def on_load_context(domain, table_name):
        state = ContextController.load_context_state(domain, table_name)
        activity_badge = ContextController.get_minimal_activity_summary(domain, table_name)
        return (
            state.get("system_prompt", ""),
            activity_badge,
            state.get("entity_rows", []),
            state.get("markdown_register", "*No register content.*")
        )

    def on_save_system_prompt(domain, prompt):
        res = ContextController.save_domain_system_prompt(domain, prompt)
        prefix = "✅" if res.get("status") == "success" else "❌"
        return f"#### Status: {prefix} {res.get('message', 'Saved.')}"

    def on_export_context(domain, table_name):
        res = ContextController.export_context_markdown(domain, table_name)
        if res.get("status") == "success":
            return (
                res.get("file_path"),
                f"### ✅ Export Successful\nSaved to `{res.get('file_path')}`"
            )
        return (
            None,
            f"### ❌ Export Failed\n```\n{res.get('message', 'Error')}\n```"
        )

    def on_domain_change(domain):
        tables = DBManager.list_tables(domain) or ["raw_assets"]
        sel_tbl = tables[0]
        prompt, badge, entities, reg = on_load_context(domain, sel_tbl)
        return (
            gr.update(choices=tables, value=sel_tbl),
            prompt,
            badge,
            entities,
            reg
        )

    # Event Wiring
    domain_dropdown.change(
        fn=on_domain_change,
        inputs=[domain_dropdown],
        outputs=[table_dropdown, system_prompt_input, context_status_badge, entity_dataframe, register_preview]
    )

    table_dropdown.change(
        fn=on_load_context,
        inputs=[domain_dropdown, table_dropdown],
        outputs=[system_prompt_input, context_status_badge, entity_dataframe, register_preview]
    )

    refresh_context_btn.click(
        fn=on_load_context,
        inputs=[domain_dropdown, table_dropdown],
        outputs=[system_prompt_input, context_status_badge, entity_dataframe, register_preview]
    )

    save_system_prompt_btn.click(
        fn=on_save_system_prompt,
        inputs=[domain_dropdown, system_prompt_input],
        outputs=[prompt_status_box]
    )

    export_context_btn.click(
        fn=on_export_context,
        inputs=[domain_dropdown, table_dropdown],
        outputs=[export_file_download, export_status_box]
    )

    if tab is not None:
        def on_tab_select(curr_dom, curr_tbl):
            dirs = DBManager.list_dirs() or ["default"]
            dom = curr_dom if curr_dom in dirs else dirs[0]
            tbls = DBManager.list_tables(dom) or ["raw_assets"]
            tbl = curr_tbl if curr_tbl in tbls else tbls[0]
            prompt, badge, entities, reg = on_load_context(dom, tbl)
            return (
                gr.update(choices=dirs, value=dom),
                gr.update(choices=tbls, value=tbl),
                prompt,
                badge,
                entities,
                reg
            )

        tab.select(
            fn=on_tab_select,
            inputs=[domain_dropdown, table_dropdown],
            outputs=[domain_dropdown, table_dropdown, system_prompt_input, context_status_badge, entity_dataframe, register_preview]
        )
