"""
Segmentation Tab (Declarative Multimodal Chunking & View Builder)
==================================================================
Renders the Segmentation & Chunking workbench for declaratively splitting documents,
text, audio, and video into granular sub-row views using native Pixeltable iterators.
"""

import gradio as gr
import pandas as pd
from typing import Optional
from src.core.config import get_settings
from src.db.manager import DBManager
from src.core.segmenter_registry import SegmenterRegistry
from src.controllers.segmentation_controller import SegmentationController


def create_segmentation_tab(settings=None, tab=None):
    """Render the Segmentation & Chunking workbench tab."""
    if tab is None and hasattr(settings, "select"):
        tab = settings
        settings = None
    if settings is None:
        settings = get_settings()

    # Discover initial domains and tables
    domains = DBManager.list_dirs() or ["default"]
    initial_domain = settings.last_domain if settings.last_domain in domains else domains[0]

    tables = DBManager.list_tables(initial_domain) or ["raw_assets"]
    initial_table = settings.last_table if settings.last_table in tables else tables[0]
    initial_suggested_view = SegmentationController.suggest_view_name(initial_table, "/split_paragraphs")

    with gr.Column():
        gr.Markdown(
            """
            ### ✂️ Segmentation & Chunking (Multimodal View Builder)
            Declaratively split documents, text, audio, and video into granular sub-row views using native Pixeltable iterators.
            Segmented views maintain automatic parent lineage, store zero duplicate media, and automatically chunk newly ingested rows.
            """
        )

        # -------------------------------------------------------------------------
        # Section 1: Source Table & Target View Configuration Strip
        # -------------------------------------------------------------------------
        with gr.Group(elem_classes=["status-panel"]):
            with gr.Row():
                domain_dropdown = gr.Dropdown(
                    label="Domain / Directory",
                    choices=domains,
                    value=initial_domain,
                    allow_custom_value=True,
                    scale=2
                )
                source_table_dropdown = gr.Dropdown(
                    label="Source Table",
                    choices=tables,
                    value=initial_table,
                    allow_custom_value=True,
                    scale=2
                )
                target_view_input = gr.Textbox(
                    label="Target View Name",
                    value=initial_suggested_view,
                    placeholder="e.g. raw_assets_paragraphs",
                    scale=2
                )
                sample_rows_slider = gr.Slider(
                    minimum=1,
                    maximum=10,
                    value=2,
                    step=1,
                    label="Sample Preview Rows",
                    scale=1
                )

        # -------------------------------------------------------------------------
        # Section 2: Presets & Prompt Command Studio
        # -------------------------------------------------------------------------
        with gr.Group(elem_classes=["status-panel"]):
            gr.Markdown("#### ⚡ Quick Presets")
            with gr.Row():
                preset_pages_btn = gr.Button("📄 Split Pages", variant="secondary")
                preset_paras_btn = gr.Button("📝 Split Paragraphs", variant="secondary")
                preset_sents_btn = gr.Button("🔤 Split Sentences", variant="secondary")
                preset_audio_btn = gr.Button("🎙️ Audio Segments (10s)", variant="secondary")
                preset_frames_btn = gr.Button("🎬 Video Frames (1 fps)", variant="secondary")

            with gr.Row():
                segment_prompt_input = gr.Textbox(
                    label="Segmentation Prompt / Slash Command",
                    value="/split_paragraphs",
                    placeholder="e.g. /split_paragraphs or /split_audio duration=15.0 or /extract_frames fps=0.5",
                    elem_classes=["prompt-slash-input"],
                    lines=1,
                    scale=5
                )
                preview_btn = gr.Button("🔬 Preview Segments", variant="secondary", scale=2)
                create_view_btn = gr.Button("✂️ Create Segmented View", variant="primary", scale=2)

            with gr.Accordion("📚 Segmentation Slash Commands & Documentation", open=False):
                gr.Markdown(SegmenterRegistry.generate_markdown_help())

        # -------------------------------------------------------------------------
        # Section 3: Segmented Output & Results Panel
        # -------------------------------------------------------------------------
        status_markdown = gr.Markdown(
            "💡 *Select a source table and click **🔬 Preview Segments** to inspect chunks or **✂️ Create Segmented View** to build a Pixeltable view.*"
        )
        preview_dataframe = gr.DataFrame(
            label="Segmented View / Preview",
            wrap=True,
            min_width=800,
            interactive=False
        )

    # -------------------------------------------------------------------------
    # Event Handlers & Dynamic Wiring
    # -------------------------------------------------------------------------
    def on_domain_change(dom, current_prompt):
        res = SegmentationController.handle_domain_change(dom, current_prompt)
        return (
            gr.update(choices=res["tables"], value=res["selected_table"]),
            res["suggested_view_name"]
        )

    domain_dropdown.change(
        fn=on_domain_change,
        inputs=[domain_dropdown, segment_prompt_input],
        outputs=[source_table_dropdown, target_view_input]
    )

    def on_table_change(dom, tbl, current_prompt):
        res = SegmentationController.handle_table_change(dom, tbl, current_prompt)
        return res["suggested_view_name"]

    source_table_dropdown.change(
        fn=on_table_change,
        inputs=[domain_dropdown, source_table_dropdown, segment_prompt_input],
        outputs=[target_view_input]
    )

    # Preset button click actions
    def set_preset_pages(src_tbl):
        cmd = "/split_pages"
        view = SegmentationController.suggest_view_name(src_tbl, cmd)
        return cmd, view

    preset_pages_btn.click(
        fn=set_preset_pages,
        inputs=[source_table_dropdown],
        outputs=[segment_prompt_input, target_view_input]
    )

    def set_preset_paras(src_tbl):
        cmd = "/split_paragraphs"
        view = SegmentationController.suggest_view_name(src_tbl, cmd)
        return cmd, view

    preset_paras_btn.click(
        fn=set_preset_paras,
        inputs=[source_table_dropdown],
        outputs=[segment_prompt_input, target_view_input]
    )

    def set_preset_sents(src_tbl):
        cmd = "/split_sentences"
        view = SegmentationController.suggest_view_name(src_tbl, cmd)
        return cmd, view

    preset_sents_btn.click(
        fn=set_preset_sents,
        inputs=[source_table_dropdown],
        outputs=[segment_prompt_input, target_view_input]
    )

    def set_preset_audio(src_tbl):
        cmd = "/split_audio duration=10.0"
        view = SegmentationController.suggest_view_name(src_tbl, cmd)
        return cmd, view

    preset_audio_btn.click(
        fn=set_preset_audio,
        inputs=[source_table_dropdown],
        outputs=[segment_prompt_input, target_view_input]
    )

    def set_preset_frames(src_tbl):
        cmd = "/extract_frames fps=1.0"
        view = SegmentationController.suggest_view_name(src_tbl, cmd)
        return cmd, view

    preset_frames_btn.click(
        fn=set_preset_frames,
        inputs=[source_table_dropdown],
        outputs=[segment_prompt_input, target_view_input]
    )

    # Preview Action
    def on_preview(dom, tbl, prompt, sample_count):
        res = SegmentationController.handle_preview_segmentation(
            domain=dom,
            table_name=tbl,
            prompt_or_preset=prompt,
            sample_rows=sample_count
        )
        headers = res.get("headers", ["Status"])
        data = res.get("data", [])
        df = pd.DataFrame(data, columns=headers) if data and headers else pd.DataFrame(columns=headers)
        return res.get("stats_text", ""), df

    preview_btn.click(
        fn=on_preview,
        inputs=[domain_dropdown, source_table_dropdown, segment_prompt_input, sample_rows_slider],
        outputs=[status_markdown, preview_dataframe]
    )

    # Create View Action
    def on_create_view(dom, tbl, view_name, prompt):
        res = SegmentationController.handle_create_view(
            domain=dom,
            source_table=tbl,
            view_name=view_name,
            prompt_or_preset=prompt
        )
        headers = res.get("headers", ["Status"])
        data = res.get("data", [])
        df = pd.DataFrame(data, columns=headers) if data and headers else pd.DataFrame(columns=headers)
        updated_tables = res.get("table_choices", DBManager.list_tables(dom))
        return (
            res.get("stats_text", ""),
            df,
            gr.update(choices=updated_tables, value=res.get("created_view", tbl))
        )

    create_view_btn.click(
        fn=on_create_view,
        inputs=[domain_dropdown, source_table_dropdown, target_view_input, segment_prompt_input],
        outputs=[status_markdown, preview_dataframe, source_table_dropdown]
    )

    # Tab selection synchronization
    if tab is not None:
        def on_tab_select(current_dom, current_tbl, current_prompt):
            latest_domains = DBManager.list_dirs() or ["default"]
            curr_settings = get_settings()
            dom = curr_settings.last_domain if curr_settings.last_domain in latest_domains else (
                current_dom if current_dom in latest_domains else latest_domains[0]
            )
            latest_tables = DBManager.list_tables(dom) or ["raw_assets"]
            tbl = curr_settings.last_table if curr_settings.last_table in latest_tables else (
                current_tbl if current_tbl in latest_tables else latest_tables[0]
            )
            suggested_view = SegmentationController.suggest_view_name(tbl, current_prompt)
            return (
                gr.update(choices=latest_domains, value=dom),
                gr.update(choices=latest_tables, value=tbl),
                suggested_view
            )

        tab.select(
            fn=on_tab_select,
            inputs=[domain_dropdown, source_table_dropdown, segment_prompt_input],
            outputs=[domain_dropdown, source_table_dropdown, target_view_input]
        )

    render_segmentation_tab = create_segmentation_tab

    return {
        "domain_dropdown": domain_dropdown,
        "source_table_dropdown": source_table_dropdown,
        "target_view_input": target_view_input,
        "sample_rows_slider": sample_rows_slider,
        "segment_prompt_input": segment_prompt_input,
        "preview_btn": preview_btn,
        "create_view_btn": create_view_btn,
        "status_markdown": status_markdown,
        "preview_dataframe": preview_dataframe,
    }


render_segmentation_tab = create_segmentation_tab
