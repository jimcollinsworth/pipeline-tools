import gradio as gr
import pandas as pd
from pathlib import Path
from src.core.config import get_settings, update_last_entry, sanitize_identifier
from src.ingest.scanner import scan_directory
from src.db.manager import DBManager

def render_ingest_tab():
    settings = get_settings()

    with gr.Column():
        gr.Markdown("### 📂 Ingestion & Directory Scanner")
        
        with gr.Row():
            dir_input = gr.Textbox(
                label="Source Directory Path",
                value=settings.default_ingest_dir,
                placeholder="e.g. D:\\data\\my_documents or C:\\docs",
                scale=4
            )
            scan_btn = gr.Button("🔍 Scan Directory", variant="primary", scale=1)

        with gr.Row():
            modality_filters = gr.CheckboxGroup(
                label="Include Modalities",
                choices=["docs", "images", "audio", "video", "other"],
                value=["docs", "images", "audio", "video"],
                scale=3
            )
            recursive_check = gr.Checkbox(label="Recursive Subdirectories", value=True, scale=1)

        summary_markdown = gr.Markdown("#### Scan Summary: *No directory scanned yet.*")

        files_table = gr.Dataframe(
            headers=["Name", "Modality", "Type", "Size", "Relative Path", "Absolute Path"],
            datatype=["str", "str", "str", "str", "str", "str"],
            value=[],
            interactive=False,
            wrap=True
        )

        # State to store scanned files in memory for ingestion
        scanned_state = gr.State([])

        gr.Markdown("---")
        gr.Markdown("### 📥 Pixeltable Ingestion Target")
        with gr.Row():
            domain_input = gr.Textbox(
                label="Pixeltable Domain / Directory",
                value=settings.last_domain,
                placeholder="e.g. eba, project_alpha",
                scale=2
            )
            table_input = gr.Textbox(
                label="Table Name",
                value=settings.last_table,
                placeholder="e.g. raw_assets, documents",
                scale=2
            )
            ingest_btn = gr.Button("⚡ Ingest Scanned Files into Pixeltable", variant="primary", scale=2)

        ingest_status_box = gr.Markdown("#### Ingestion Status: *Ready*")

    def on_scan(path_str, modalities, recursive):
        if not path_str or not path_str.strip():
            return "⚠️ Please provide a valid directory path.", [], []
        
        p = Path(path_str.strip())
        if not p.exists():
            return f"❌ Path does not exist: `{path_str}`", [], []
        if not p.is_dir():
            return f"❌ Path is not a directory: `{path_str}`", [], []

        # Save last scanned directory
        update_last_entry(default_ingest_dir=str(p))

        files = scan_directory(str(p), recursive=recursive, modalities=modalities)
        if not files:
            return f"ℹ️ Directory scanned successfully, but no matching files were found in `{path_str}`.", [], []

        # Tally summary stats
        modality_counts = {}
        total_bytes = 0
        for f in files:
            m = f["modality"]
            modality_counts[m] = modality_counts.get(m, 0) + 1
            total_bytes += f["size_bytes"]

        total_mb = round(total_bytes / (1024 * 1024), 2)
        breakdown = ", ".join([f"**{m}**: {count}" for m, count in modality_counts.items()])
        summary_text = (
            f"✅ **Found {len(files)} files** ({total_mb} MB total)\n\n"
            f"Breakdown: {breakdown}"
        )

        rows = [
            [f["name"], f["modality"], f["extension"], f["size"], f["rel_path"], f["abs_path"]]
            for f in files
        ]

        return summary_text, rows, files

    def on_ingest(files_data, domain, table_name):
        if not files_data:
            return "⚠️ No scanned files to ingest. Please scan a directory first."
        
        clean_dir = domain.strip() if domain else "default"
        clean_tbl = table_name.strip() if table_name else "raw_assets"

        update_last_entry(last_domain=clean_dir, last_table=clean_tbl)

        res = DBManager.ingest_files(clean_dir, clean_tbl, files_data)
        if res.get("status") == "success":
            return f"✅ **{res.get('message')}**"
        else:
            return f"❌ **Error during ingestion:**\n```\n{res.get('message')}\n```"


    def on_scan(path_str, modalities, recursive):
        if not path_str or not path_str.strip():
            return "⚠️ Please provide a valid directory path.", [], []
        
        p = Path(path_str.strip())
        if not p.exists():
            return f"❌ Path does not exist: `{path_str}`", [], []
        if not p.is_dir():
            return f"❌ Path is not a directory: `{path_str}`", [], []

        files = scan_directory(str(p), recursive=recursive, modalities=modalities)
        if not files:
            return f"ℹ️ Directory scanned successfully, but no matching files were found in `{path_str}`.", [], []

        # Tally summary stats
        modality_counts = {}
        total_bytes = 0
        for f in files:
            m = f["modality"]
            modality_counts[m] = modality_counts.get(m, 0) + 1
            total_bytes += f["size_bytes"]

        total_mb = round(total_bytes / (1024 * 1024), 2)
        breakdown = ", ".join([f"**{m}**: {count}" for m, count in modality_counts.items()])
        summary_text = (
            f"✅ **Found {len(files)} files** ({total_mb} MB total)\n\n"
            f"Breakdown: {breakdown}"
        )

        rows = [
            [f["name"], f["modality"], f["extension"], f["size"], f["rel_path"], f["abs_path"]]
            for f in files
        ]

        return summary_text, rows, files

    def on_ingest(files_data, domain, table_name):
        if not files_data:
            return "⚠️ No scanned files to ingest. Please scan a directory first."
        if not domain or not domain.strip():
            return "⚠️ Please enter a valid Domain/Directory name."
        if not table_name or not table_name.strip():
            return "⚠️ Please enter a valid Table name."

        res = DBManager.ingest_files(domain.strip(), table_name.strip(), files_data)
        if res.get("status") == "success":
            return f"✅ **{res.get('message')}**"
        else:
            return f"❌ **Error during ingestion:** {res.get('message')}"

    scan_btn.click(
        fn=on_scan,
        inputs=[dir_input, modality_filters, recursive_check],
        outputs=[summary_markdown, files_table, scanned_state]
    )

    ingest_btn.click(
        fn=on_ingest,
        inputs=[scanned_state, domain_input, table_input],
        outputs=[ingest_status_box]
    )

