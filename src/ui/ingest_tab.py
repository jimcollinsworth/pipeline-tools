import gradio as gr
import pandas as pd
from pathlib import Path
from src.core.config import get_settings, update_last_entry, sanitize_identifier
from src.ingest.scanner import scan_directory
from src.db.manager import DBManager

def get_directory_choices(current_path=None):
    """Generate intelligent path suggestions for type-ahead dropdown."""
    choices = set()
    cwd = Path.cwd()
    home = Path.home()
    
    choices.add(str(cwd))
    choices.add(str(home))
    
    curr = get_settings().default_ingest_dir
    if curr and Path(curr).exists():
        choices.add(str(Path(curr)))

    # Discover immediate subdirectories of CWD & Home
    for base in [cwd, home]:
        try:
            for child in base.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    choices.add(str(child))
        except Exception:
            pass

    # If current_path exists, include it and its subdirectories
    if current_path:
        try:
            p = Path(current_path.strip())
            if p.exists() and p.is_dir():
                choices.add(str(p))
                for child in p.iterdir():
                    if child.is_dir() and not child.name.startswith("."):
                        choices.add(str(child))
        except Exception:
            pass

    return sorted(list(choices))

def render_ingest_tab():
    settings = get_settings()
    default_path = settings.default_ingest_dir or str(Path.cwd())

    with gr.Column(scale=1):
        gr.Markdown("### 📂 Ingestion & Directory Scanner")
        
        with gr.Row():
            dir_input = gr.Dropdown(
                label="Source Directory Path (Type or select from tree)",
                choices=get_directory_choices(default_path),
                value=default_path,
                allow_custom_value=True,
                filterable=True,
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
            wrap=True,
            min_width=800
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

    def on_dir_change(selected_path):
        """Update choices dynamically when user selects or types a path."""
        if not selected_path:
            return gr.update()
        new_choices = get_directory_choices(selected_path)
        return gr.update(choices=new_choices)

    def on_scan(path_str, modalities, recursive):
        if not path_str or not path_str.strip():
            return "⚠️ Please provide a valid directory path.", [], [], gr.update()
        
        p = Path(path_str.strip())
        if not p.exists():
            return f"❌ Path does not exist: `{path_str}`", [], [], gr.update()
        if not p.is_dir():
            return f"❌ Path is not a directory: `{path_str}`", [], [], gr.update()

        # Save last scanned directory
        update_last_entry(default_ingest_dir=str(p))
        updated_choices = get_directory_choices(str(p))

        files = scan_directory(str(p), recursive=recursive, modalities=modalities)
        if not files:
            return f"ℹ️ Directory scanned successfully, but no matching files were found in `{path_str}`.", [], [], gr.update(choices=updated_choices)

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

        return summary_text, rows, files, gr.update(choices=updated_choices)

    def on_ingest(files_data, domain, table_name):
        if not files_data:
            return "⚠️ No scanned files to ingest. Please scan a directory first."
        if not domain or not domain.strip():
            return "⚠️ Please enter a valid Domain/Directory name."
        if not table_name or not table_name.strip():
            return "⚠️ Please enter a valid Table name."

        clean_dir = domain.strip()
        clean_tbl = table_name.strip()

        update_last_entry(last_domain=clean_dir, last_table=clean_tbl)

        res = DBManager.ingest_files(clean_dir, clean_tbl, files_data)
        if res.get("status") == "success":
            return f"✅ **{res.get('message')}**"
        else:
            return f"❌ **Error during ingestion:** {res.get('message')}"

    dir_input.change(
        fn=on_dir_change,
        inputs=[dir_input],
        outputs=[dir_input]
    )

    scan_btn.click(
        fn=on_scan,
        inputs=[dir_input, modality_filters, recursive_check],
        outputs=[summary_markdown, files_table, scanned_state, dir_input]
    )

    ingest_btn.click(
        fn=on_ingest,
        inputs=[scanned_state, domain_input, table_input],
        outputs=[ingest_status_box]
    )
