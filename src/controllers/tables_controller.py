"""
Tables Controller
=================
Decoupled controller for the View & Export tab.
Handles table queries, zero-query row inspection formatting, AI report generation,
and safe 2-step table & domain deletion workflows.
"""

import os
from typing import List, Dict, Any, Optional, Callable, Tuple
from src.core.config import get_settings, update_last_entry
from src.core.llm_service import LLMService
from src.db.manager import DBManager
from src.export.exporter import MarkdownExporter

class TablesController:
    """Pure controller handling table data viewing, row media inspection, export, and deletion."""

    @staticmethod
    def handle_load_table(domain: str, table_name: str, limit: int = 50, is_lightweight: bool = True) -> Dict[str, Any]:
        """Fetch table rows, format stats summary, datatypes, and column placeholder tags."""
        if not domain or not table_name:
            return {
                "status": "error",
                "stats_text": "⚠️ Please provide both Domain and Table name.",
                "columns": [],
                "datatypes": [],
                "data": [],
                "placeholders_text": "💡 **Available Column Placeholders:** *None*"
            }

        clean_dir = domain.strip()
        clean_tbl = table_name.strip()
        update_last_entry(last_domain=clean_dir, last_table=clean_tbl)

        res = DBManager.get_table_data(clean_dir, clean_tbl, limit=int(limit), lightweight=is_lightweight)
        if res.get("error"):
            return {
                "status": "error",
                "stats_text": f"❌ **Error loading table `{clean_dir}.{clean_tbl}`:**\n```\n{res.get('error')}\n```",
                "columns": ["Error"],
                "datatypes": ["str"],
                "data": [[res.get("error")]],
                "placeholders_text": "💡 **Available Column Placeholders:** *Error loading table.*"
            }

        cols = res.get("columns", [])
        datatypes = res.get("datatypes", ["str"] * len(cols))
        data = res.get("data", [])
        total = res.get("total_rows", len(data))
        mode_label = "⚡ Lightweight" if is_lightweight else "🔍 Full Media"

        stats_text = (
            f"✅ **Table `{res.get('domain', clean_dir)}.{res.get('table', clean_tbl)}`** ({mode_label}) — "
            f"Displaying {len(data)} of {total} total rows.\nColumns: `{', '.join(cols)}`"
        )
        cols_pills = ", ".join([f"`{{{c}}}`" for c in cols if c != "media_preview"]) if cols else "*None*"
        cols_text = f"💡 **Available Column Placeholders:** {cols_pills} | Standard: `{{domain}}`, `{{table}}`, `{{total_rows}}`, `{{table_context}}`"

        return {
            "status": "success",
            "stats_text": stats_text,
            "columns": cols,
            "datatypes": datatypes,
            "data": data,
            "placeholders_text": cols_text,
            "total_rows": total
        }

    @staticmethod
    def handle_domain_change(domain: str) -> Dict[str, Any]:
        """Update table dropdown choices when domain selection changes."""
        if not domain:
            return {"choices": [], "value": ""}
        clean_dir = domain.strip()
        update_last_entry(last_domain=clean_dir)
        tables_list = DBManager.list_tables(clean_dir)
        if not tables_list:
            tables_list = ["raw_assets"]

        curr_settings = get_settings()
        selected_tbl = curr_settings.last_table if curr_settings.last_table in tables_list else tables_list[0]
        return {
            "choices": tables_list,
            "value": selected_tbl
        }

    @staticmethod
    def handle_row_inspection(row_idx: int, current_df: Any, domain: str, table_name: str) -> Dict[str, Any]:
        """Format row details, media file paths, and extracted text for the Media Inspector drawer."""
        row_dict = {}
        if hasattr(current_df, "iloc") and 0 <= row_idx < len(current_df):
            row_dict = current_df.iloc[row_idx].to_dict()
        elif isinstance(current_df, list) and 0 <= row_idx < len(current_df):
            val = current_df[row_idx]
            if isinstance(val, dict):
                row_dict = val
        elif isinstance(current_df, dict) and "data" in current_df:
            headers = current_df.get("headers", [])
            data_rows = current_df.get("data", [])
            if 0 <= row_idx < len(data_rows):
                row_dict = dict(zip(headers, data_rows[row_idx]))

        if not row_dict:
            clean_dir = domain.strip() if domain else "default"
            clean_tbl = table_name.strip() if table_name else "raw_assets"
            res = DBManager.get_table_data(clean_dir, clean_tbl, limit=50, lightweight=False)
            cols = res.get("columns", [])
            data = res.get("data", [])
            if 0 <= row_idx < len(data):
                row_dict = dict(zip(cols, data[row_idx]))

        file_path = str(row_dict.get("file_path", ""))
        file_name = str(row_dict.get("file_name", "Unknown File"))
        modality = str(row_dict.get("modality", "")).lower()
        file_type = str(row_dict.get("file_type", "")).lower()
        content = str(row_dict.get("content", ""))
        size = row_dict.get("file_size", "")

        summary_lines = [
            f"### 📄 **{file_name}**",
            f"- **Modality:** `{modality}` | **Format:** `{file_type}` | **Size:** {size} bytes",
            f"- **File Path:** `{file_path}`"
        ]
        for k, v in row_dict.items():
            if k not in ["id", "file_name", "file_path", "rel_path", "modality", "file_type", "file_size", "content", "media_preview", "doc", "image", "audio", "video", "metadata", "created_at"] and v:
                summary_lines.append(f"- **{k}:** {v}")

        details_md = "\n".join(summary_lines)
        file_exists = os.path.exists(file_path) if file_path else False

        img_val = file_path if (modality == "images" or file_type in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"]) and file_exists else None
        audio_val = file_path if (modality == "audio" or file_type in [".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"]) and file_exists else None
        video_val = file_path if (modality == "video" or file_type in [".mp4", ".webm", ".mov", ".avi", ".mkv"]) and file_exists else None
        has_content = bool(content and content.strip())

        return {
            "image_path": img_val,
            "has_image": bool(img_val),
            "audio_path": audio_val,
            "has_audio": bool(audio_val),
            "video_path": video_val,
            "has_video": bool(video_val),
            "details_markdown": details_md,
            "content_text": content if has_content else "",
            "has_content": has_content
        }

    @staticmethod
    def handle_delete_table(domain: str, table_name: str) -> Dict[str, Any]:
        """Execute safe table deletion and return updated dropdown states."""
        clean_dir = domain.strip() if domain else "default"
        clean_tbl = table_name.strip() if table_name else ""
        if not clean_tbl:
            return {
                "status": "error",
                "message": "⚠️ Please select a valid Table to delete."
            }

        res = DBManager.delete_table_with_details(clean_dir, clean_tbl)
        remaining_tables = DBManager.list_tables(clean_dir)
        new_val = remaining_tables[0] if remaining_tables else ""

        if res.get("status") == "success":
            status_msg = (
                f"### 🗑️ Table Deleted Successfully\n"
                f"- **Deleted Table:** `{res.get('table_path')}`\n"
                f"- **Rows Removed:** {res.get('rows_deleted', 0)}\n"
                f"- **Remaining Tables in `{clean_dir}`:** `{', '.join(remaining_tables) if remaining_tables else 'None'}`"
            )
            return {
                "status": "success",
                "message": status_msg,
                "table_choices": remaining_tables,
                "table_value": new_val
            }
        else:
            return {
                "status": "error",
                "message": f"### ❌ Table Deletion Failed\n{res.get('message', 'Unknown error')}",
                "table_choices": remaining_tables,
                "table_value": new_val
            }

    @staticmethod
    def handle_delete_domain(domain: str) -> Dict[str, Any]:
        """Execute safe domain deletion and return updated domain dropdown states."""
        clean_dir = domain.strip() if domain else ""
        if not clean_dir:
            return {
                "status": "error",
                "message": "⚠️ Please select a valid Domain to delete."
            }

        res = DBManager.delete_domain_with_details(clean_dir)
        remaining_domains = DBManager.list_dirs()
        new_domain_val = remaining_domains[0] if remaining_domains else "default"
        new_tables = DBManager.list_tables(new_domain_val)
        new_table_val = new_tables[0] if new_tables else "raw_assets"

        if res.get("status") == "success":
            status_msg = (
                f"### ⚠️ Domain & Connected Tables Deleted Successfully\n"
                f"- **Deleted Domain:** `{res.get('domain')}`\n"
                f"- **Tables Dropped:** `{', '.join(res.get('tables_deleted', [])) if res.get('tables_deleted') else 'None'}`\n"
                f"- **Total Rows Purged:** {res.get('total_rows_purged', 0)}\n"
                f"- **Active Domains Remaining:** `{', '.join(remaining_domains) if remaining_domains else 'None'}`"
            )
            return {
                "status": "success",
                "message": status_msg,
                "domain_choices": remaining_domains,
                "domain_value": new_domain_val,
                "table_choices": new_tables,
                "table_value": new_table_val
            }
        else:
            return {
                "status": "error",
                "message": f"### ❌ Domain Deletion Failed\n{res.get('message', 'Unknown error')}",
                "domain_choices": remaining_domains,
                "domain_value": new_domain_val,
                "table_choices": new_tables,
                "table_value": new_table_val
            }

    @staticmethod
    def handle_export_report(
        domain: str,
        table_name: str,
        provider: str,
        model: str,
        max_rows: int,
        system_prompt: str,
        prompt_template: str,
        mode: str = "single",
        custom_filename: str = "",
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[str, Any]:
        """Execute AI report synthesis or per-row sidecars and write to exports/ directory."""
        if not domain or not table_name:
            return {
                "status": "error",
                "message": "### ⚠️ Missing Target Table\nPlease select a Domain and Table above."
            }

        if not prompt_template or not prompt_template.strip():
            return {
                "status": "error",
                "message": "### ⚠️ Missing Prompt Template\nPlease enter a synthesis prompt template."
            }

        is_sidecar = ("sidecar" in mode.lower() or "per-row" in mode.lower())
        res = MarkdownExporter.generate_report(
            domain=domain,
            table_name=table_name,
            prompt_template=prompt_template,
            system_prompt=system_prompt,
            provider=provider,
            model=model,
            mode="sidecar" if is_sidecar else "single",
            max_rows=int(max_rows),
            custom_filename=custom_filename,
            progress_callback=progress_callback
        )

        if res.get("status") == "success":
            file_path = res.get("file_path")
            file_name = res.get("file_name")
            content = res.get("markdown_content", "")
            total_rows = res.get("row_count", 0)

            mode_label = "Per-Row Sidecars (`_meta.md`)" if is_sidecar else "Single Unified Synthesis"
            status_msg = (
                f"### ✅ Export Completed Successfully!\n"
                f"- **Strategy:** {mode_label}\n"
                f"- **Records Processed:** {total_rows}\n"
                f"- **Primary File / Output:** `{file_path}`\n"
                f"- **AI Engine / Model:** `{provider}` ({model})\n"
            )
            return {
                "status": "success",
                "message": status_msg,
                "file_path": file_path,
                "file_name": file_name,
                "content": content,
                "total_rows": total_rows,
                "saved_files": res.get("saved_files", [file_path])
            }
        else:
            err_msg = res.get("message", "Unknown error during export")
            return {
                "status": "error",
                "message": f"### ❌ Export Failed\n```\n{err_msg}\n```"
            }
