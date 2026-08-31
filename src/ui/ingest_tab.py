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

def render_ingest_tab(tab=None):
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

        domains = DBManager.list_dirs()
        if not domains:
            domains = ["default"]
        initial_domain = settings.last_domain if settings.last_domain in domains else domains[0]

        tables = DBManager.list_tables(initial_domain)
        if not tables:
            tables = ["raw_assets"]
        initial_table = settings.last_table if settings.last_table in tables else tables[0]

        gr.Markdown("---")
        gr.Markdown("### 📥 Pixeltable Ingestion Target")
        with gr.Row():
            domain_dropdown = gr.Dropdown(
                label="Pixeltable Domain / Directory (Select or type new)",
                choices=domains,
                value=initial_domain,
                allow_custom_value=True,
                scale=2
            )
            table_dropdown = gr.Dropdown(
                label="Table Name (Select or type new)",
                choices=tables,
                value=initial_table,
                allow_custom_value=True,
                scale=2
            )
            overwrite_check = gr.Checkbox(
                label="Overwrite if Exists (Preserves Lineage History)",
                value=False,
                scale=2
            )

        with gr.Row():
            ingest_btn = gr.Button("⚡ Ingest Scanned Files into Pixeltable", variant="primary", scale=1)

        with gr.Group(elem_classes=["status-panel"]):
            ingest_status_box = gr.Markdown("#### Ingestion Status: *Ready*")

    def on_dir_change(selected_path):
        """Update choices dynamically when user selects or types a path."""
        if not selected_path:
            return gr.update()
        new_choices = get_directory_choices(selected_path)
        return gr.update(choices=new_choices)

    def on_ingest_domain_change(selected_domain):
        if not selected_domain:
            return gr.update(choices=["raw_assets"], value="raw_assets")
        clean_dir = selected_domain.strip()
        tables_list = DBManager.list_tables(clean_dir)
        if not tables_list:
            tables_list = ["raw_assets"]
        curr_settings = get_settings()
        selected_tbl = curr_settings.last_table if curr_settings.last_table in tables_list else tables_list[0]
        return gr.update(choices=tables_list, value=selected_tbl)

    def on_scan(path_str, modalities, recursive, progress=gr.Progress(track_tqdm=True)):
        if not path_str or not path_str.strip():
            gr.Warning("Please provide a valid directory path.")
            return "⚠️ **Please provide a valid directory path.**", [], [], gr.update()
        
        p = Path(path_str.strip())
        if not p.exists():
            gr.Error(f"Path does not exist: {path_str}")
            return f"### ❌ Path Not Found\n> Path `{path_str}` does not exist.", [], [], gr.update()
        if not p.is_dir():
            gr.Error(f"Path is not a directory: {path_str}")
            return f"### ❌ Not a Directory\n> Path `{path_str}` is a file, not a directory.", [], [], gr.update()

        progress(0.2, desc=f"Scanning directory: {p.name}...")
        # Save last scanned directory
        update_last_entry(default_ingest_dir=str(p))
        updated_choices = get_directory_choices(str(p))

        files = scan_directory(str(p), recursive=recursive, modalities=modalities)
        progress(1.0, desc=f"Found {len(files)} files.")

        if not files:
            gr.Info(f"No matching files found in {path_str}")
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

    def on_ingest(files_data, domain, table_name, overwrite, progress=gr.Progress(track_tqdm=True)):
        if not files_data:
            gr.Warning("No scanned files to ingest. Scan a directory first.")
            yield "### ⚠️ No Files to Ingest\n> Please scan a directory containing documents/media first."
            return

        if not domain or not domain.strip():
            gr.Warning("Please enter a valid Domain/Directory name.")
            yield "### ⚠️ Missing Domain\n> Please enter a Pixeltable domain name (e.g. `default`, `project_alpha`)."
            return

        if not table_name or not table_name.strip():
            gr.Warning("Please enter a valid Table name.")
            yield "### ⚠️ Missing Table Name\n> Please enter a target table name (e.g. `raw_assets`)."
            return

        clean_dir = domain.strip()
        clean_tbl = table_name.strip()
        update_last_entry(last_domain=clean_dir, last_table=clean_tbl)

        total_files = len(files_data)
        mode_str = "Overwriting (Archiving previous version)" if overwrite else "Appending to table"
        yield f"⏳ **[1/3] Ingestion Started...** Target: `{clean_dir}.{clean_tbl}` ({mode_str}) for {total_files} files..."

        def cb(cur, total, detail):
            pct = (cur / total) if total else 0.5
            progress(pct, desc=detail)

        try:
            yield f"⏳ **[2/3] Extracting Content & Metadata...** Processing {total_files} files into `{clean_dir}.{clean_tbl}`..."
            res = DBManager.ingest_files(clean_dir, clean_tbl, files_data, overwrite=overwrite, progress_callback=cb)
            
            if res.get("status") == "success":
                overwritten_msg = "\n> ℹ️ *Previous version archived in Pixeltable lineage history.*" if res.get("overwritten") else ""
                gr.Info(f"Successfully ingested {res.get('inserted_count', total_files)} files!")
                yield (
                    f"### ✅ Ingestion Complete!\n"
                    f"> **Target Table:** `{clean_dir}.{clean_tbl}`\n"
                    f"> **Rows Ingested:** {res.get('inserted_count', total_files)}\n"
                    f"> **Total Rows in Table:** {res.get('total_count', 'N/A')}{overwritten_msg}\n\n"
                    f"*You can now inspect the ingested data in the **Lineage & DataTables** tab or run prompts in **Prompt Playground**.*"
                )
            else:
                err_msg = res.get("message", "Unknown error")
                gr.Error(f"Ingestion failed: {err_msg}")
                yield (
                    f"### ❌ Ingestion Failed\n"
                    f"> **Error Message:**\n"
                    f"> ```\n> {err_msg}\n> ```\n\n"
                    f"💡 *Hint: Ensure domain and table identifiers do not contain hyphens `-` or start with numbers.*"
                )
        except Exception as e:
            gr.Error(f"Unexpected error: {str(e)}")
            yield f"### ❌ Unexpected Ingestion Exception\n```\n{type(e).__name__}: {str(e)}\n```"

    dir_input.change(
        fn=on_dir_change,
        inputs=[dir_input],
        outputs=[dir_input]
    )

    domain_dropdown.change(
        fn=on_ingest_domain_change,
        inputs=[domain_dropdown],
        outputs=[table_dropdown]
    )

    scan_btn.click(
        fn=on_scan,
        inputs=[dir_input, modality_filters, recursive_check],
        outputs=[summary_markdown, files_table, scanned_state, dir_input]
    )

    ingest_btn.click(
        fn=on_ingest,
        inputs=[scanned_state, domain_dropdown, table_dropdown, overwrite_check],
        outputs=[ingest_status_box]
    )

    if tab is not None:
        def on_tab_select(current_domain, current_table):
            latest_domains = DBManager.list_dirs()
            if not latest_domains:
                latest_domains = ["default"]
            curr_settings = get_settings()
            dom = curr_settings.last_domain if curr_settings.last_domain in latest_domains else (
                current_domain if current_domain in latest_domains else latest_domains[0]
            )
            latest_tables = DBManager.list_tables(dom)
            if not latest_tables:
                latest_tables = ["raw_assets"]
            tbl = curr_settings.last_table if curr_settings.last_table in latest_tables else (
                current_table if current_table in latest_tables else latest_tables[0]
            )
            return (
                gr.update(choices=latest_domains, value=dom),
                gr.update(choices=latest_tables, value=tbl)
            )

        tab.select(
            fn=on_tab_select,
            inputs=[domain_dropdown, table_dropdown],
            outputs=[domain_dropdown, table_dropdown]
        )
