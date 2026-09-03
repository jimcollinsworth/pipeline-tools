"""
Ingest Controller
=================
Decoupled controller for directory scanning, path suggestions, and Pixeltable ingestion.
Separates pure business logic, input validation, and database operations from the Gradio UI layer.
"""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from src.core.config import get_settings, update_last_entry, sanitize_identifier
from src.ingest.scanner import scan_directory
from src.db.manager import DBManager

class IngestController:
    """Pure controller handling directory scanning and file ingestion workflows."""

    @staticmethod
    def get_directory_suggestions(current_path: Optional[str] = None) -> List[str]:
        """Generate intelligent path suggestions for directory type-ahead inputs."""
        choices = set()
        cwd = Path.cwd()
        home = Path.home()

        choices.add(str(cwd))
        choices.add(str(home))

        curr = get_settings().default_ingest_dir
        if curr and Path(curr).exists():
            choices.add(str(Path(curr)))

        # Immediate subdirectories of CWD & Home
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

    @staticmethod
    def scan_directory_flow(
        path_str: str,
        modalities: Optional[List[str]] = None,
        recursive: bool = True,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Dict[str, Any]:
        """Validate directory, execute scanner, and return formatted summary & table records."""
        if not path_str or not path_str.strip():
            return {
                "status": "error",
                "summary": "⚠️ **Please provide a valid directory path.**",
                "files_table": [],
                "scanned_files": [],
                "directory_choices": IngestController.get_directory_suggestions()
            }

        p = Path(path_str.strip())
        if not p.exists():
            return {
                "status": "error",
                "summary": f"### ❌ Path Not Found\n> Path `{path_str}` does not exist.",
                "files_table": [],
                "scanned_files": [],
                "directory_choices": IngestController.get_directory_suggestions()
            }

        if not p.is_dir():
            return {
                "status": "error",
                "summary": f"### ❌ Not a Directory\n> Path `{path_str}` is a file, not a directory.",
                "files_table": [],
                "scanned_files": [],
                "directory_choices": IngestController.get_directory_suggestions()
            }

        if progress_callback:
            progress_callback(0.2, f"Scanning directory: {p.name}...")

        # Persist last scanned path
        update_last_entry(default_ingest_dir=str(p))
        updated_choices = IngestController.get_directory_suggestions(str(p))

        if modalities is None:
            modalities = ["docs", "images", "audio", "video", "csv"]

        files = scan_directory(str(p), recursive=recursive, modalities=modalities)
        if not files:
            return {
                "status": "empty",
                "summary": f"### 📂 Directory Scanned: `{p.resolve()}`\n> **0 files found** matching selected modalities.",
                "files_table": [],
                "scanned_files": [],
                "directory_choices": updated_choices
            }

        # Calculate modality counts
        modality_counts = {}
        for f in files:
            m = f.get("modality", "other")
            modality_counts[m] = modality_counts.get(m, 0) + 1

        counts_str = " | ".join([f"**{k.capitalize()}**: {v}" for k, v in sorted(modality_counts.items())])
        summary_md = f"### 📂 Scanned `{p.resolve()}`\n**Total Files Discovered:** {len(files)} ({counts_str})"

        table_rows = [
            [f["name"], f["modality"], f["extension"], f["size"], f["rel_path"], f["abs_path"]]
            for f in files
        ]

        return {
            "status": "success",
            "summary": summary_md,
            "files_table": table_rows,
            "scanned_files": files,
            "directory_choices": updated_choices
        }

    @staticmethod
    def ingest_files_flow(
        domain: str,
        table_name: str,
        scanned_files: List[Dict[str, Any]],
        overwrite: bool = False,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[str, Any]:
        """Validate input parameters and execute Pixeltable ingestion with sanitized identifiers."""
        if not scanned_files:
            return {
                "status": "error",
                "message": "⚠️ **No files scanned yet.** Please scan a directory first.",
                "domain_choices": DBManager.list_dirs() or ["default"],
                "table_choices": DBManager.list_tables(domain) or ["raw_assets"]
            }

        clean_dir = domain.strip() if domain and domain.strip() else "default"
        clean_tbl = table_name.strip() if table_name and table_name.strip() else "raw_assets"

        # Sanitize identifiers
        _, safe_dir, dir_sanitized = sanitize_identifier(clean_dir)
        _, safe_tbl, tbl_sanitized = sanitize_identifier(clean_tbl)

        update_last_entry(last_domain=safe_dir, last_table=safe_tbl)

        # Check for CSV files in scanned_files
        csv_files = [f for f in scanned_files if f.get("modality") == "csv" or f.get("extension", "").lower() == ".csv"]
        if csv_files:
            if len(csv_files) > 1:
                return {
                    "status": "error",
                    "message": (
                        f"### ⚠️ Single CSV Ingestion Rule\n"
                        f"> In Pipeline Tools, **only one CSV can be ingested at a time** because each row in the CSV becomes an individual record in the table.\n\n"
                        f"Found **{len(csv_files)} CSV files** in the scan list. Please isolate the specific CSV file you wish to ingest, or deselect other modalities."
                    ),
                    "domain_choices": DBManager.list_dirs() or [safe_dir],
                    "table_choices": DBManager.list_tables(safe_dir) or [safe_tbl]
                }
            if len(scanned_files) > 1:
                return {
                    "status": "error",
                    "message": (
                        f"### ⚠️ Mixed Ingestion Not Permitted\n"
                        f"> Found 1 CSV file (`{csv_files[0]['name']}`) alongside other media/document files.\n\n"
                        f"CSV files are ingested into tabular rows, whereas documents/media are ingested as individual file asset rows. "
                        f"Please uncheck 'csv' to ingest media files, or scan only the folder/file containing your CSV."
                    ),
                    "domain_choices": DBManager.list_dirs() or [safe_dir],
                    "table_choices": DBManager.list_tables(safe_dir) or [safe_tbl]
                }

            # Exactly 1 CSV file: route to DBManager.ingest_csv
            csv_path = csv_files[0].get("abs_path", "")
            res = DBManager.ingest_csv(
                dir_name=safe_dir,
                table_name=safe_tbl,
                csv_path=csv_path,
                overwrite=overwrite,
                progress_callback=progress_callback
            )
        else:
            res = DBManager.ingest_files(
                dir_name=safe_dir,
                table_name=safe_tbl,
                files_info=scanned_files,
                overwrite=overwrite,
                progress_callback=progress_callback
            )

        all_domains = DBManager.list_dirs()
        if not all_domains:
            all_domains = [safe_dir]
        elif safe_dir not in all_domains:
            all_domains.append(safe_dir)

        all_tables = DBManager.list_tables(safe_dir)
        if not all_tables:
            all_tables = [safe_tbl]
        elif safe_tbl not in all_tables:
            all_tables.append(safe_tbl)

        if res.get("status") == "success":
            sanitization_note = ""
            if dir_sanitized or tbl_sanitized:
                sanitization_note = f"\n> *Note: Target identifier was sanitized for SQL compatibility: `{clean_dir}.{clean_tbl}` → `{safe_dir}.{safe_tbl}`*"

            cols_line = f"\n- **Columns:** {res.get('columns_count')} ({', '.join(res.get('columns', [])[:8])}{'...' if len(res.get('columns', [])) > 8 else ''})" if "columns_count" in res else ""
            status_msg = (
                f"### ✅ Pixeltable Ingestion Complete!\n"
                f"- **Target Table:** `{safe_dir}.{safe_tbl}`\n"
                f"- **Rows Inserted:** {res.get('rows_inserted', len(scanned_files))}"
                f"{cols_line}\n"
                f"- **Status:** Successfully written to persistent storage.{sanitization_note}"
            )
            return {
                "status": "success",
                "message": status_msg,
                "safe_domain": safe_dir,
                "safe_table": safe_tbl,
                "domain_choices": all_domains,
                "table_choices": all_tables
            }
        else:
            return {
                "status": "error",
                "message": f"### ❌ Ingestion Failed\n```\n{res.get('message', 'Unknown database error')}\n```",
                "safe_domain": safe_dir,
                "safe_table": safe_tbl,
                "domain_choices": all_domains,
                "table_choices": all_tables
            }
