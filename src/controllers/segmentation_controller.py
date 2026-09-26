"""
Segmentation Controller
=======================
Decoupled controller for the Segmentation & Chunking tab.
Handles table discovery, automatic view name suggestion, dry-run segmentation preview,
and declarative Pixeltable view creation.
"""

from typing import Dict, Any, Optional, List
from src.core.config import sanitize_identifier, update_last_entry
from src.db.manager import DBManager
from src.core.segmenter_registry import SegmenterRegistry


class SegmentationController:
    """Pure controller handling table segmentation, dry-run preview, and view creation."""

    @staticmethod
    def suggest_view_name(source_table: str, prompt_or_preset: str = "") -> str:
        """Suggest a clean, descriptive view name based on source table and segmenter."""
        is_valid, clean_tbl, _ = sanitize_identifier(source_table) if source_table else (True, "data", "")
        if not is_valid or not clean_tbl:
            clean_tbl = "data"
        suffix = "segmented"
        if prompt_or_preset:
            match = SegmenterRegistry.match_prompt(prompt_or_preset)
            if match:
                suffix = match[0].name.replace("split_", "").replace("extract_", "")
            else:
                p_clean = prompt_or_preset.strip().lstrip("/").split()[0].lower()
                _, clean_p, _ = sanitize_identifier(p_clean)
                suffix = clean_p.replace("split_", "").replace("extract_", "") if clean_p else "segmented"
        return f"{clean_tbl}_{suffix}"

    @staticmethod
    def handle_domain_change(domain: str, prompt: str = "") -> Dict[str, Any]:
        """Handle domain dropdown change: discovers tables and suggests initial view name."""
        clean_dir = domain.strip() if domain else "default"
        update_last_entry(last_domain=clean_dir)
        tables = DBManager.list_tables(clean_dir) or ["raw_assets"]
        first_table = tables[0]
        suggested_view = SegmentationController.suggest_view_name(first_table, prompt)
        return {
            "tables": tables,
            "selected_table": first_table,
            "suggested_view_name": suggested_view
        }

    @staticmethod
    def handle_table_change(domain: str, table_name: str, prompt: str = "") -> Dict[str, Any]:
        """Handle source table change: suggests target view name."""
        clean_tbl = table_name.strip() if table_name else "raw_assets"
        update_last_entry(last_table=clean_tbl)
        suggested_view = SegmentationController.suggest_view_name(clean_tbl, prompt)
        return {
            "suggested_view_name": suggested_view
        }

    @staticmethod
    def handle_preview_segmentation(
        domain: str,
        table_name: str,
        prompt_or_preset: str,
        sample_rows: int = 2
    ) -> Dict[str, Any]:
        """Execute dry-run segmentation preview across sample rows."""
        if not domain or not table_name:
            return {
                "status": "error",
                "stats_text": "⚠️ Please select a Domain and Source Table to preview segmentation.",
                "headers": ["Status", "Message"],
                "datatypes": ["str", "str"],
                "data": [["Error", "Domain and Source Table required."]],
                "count": 0
            }

        if not prompt_or_preset or not prompt_or_preset.strip():
            return {
                "status": "error",
                "stats_text": "⚠️ Please enter a segmentation prompt or click a preset button.",
                "headers": ["Status", "Message"],
                "datatypes": ["str", "str"],
                "data": [["Error", "Segmentation prompt or preset required."]],
                "count": 0
            }

        clean_dir = domain.strip()
        clean_tbl = table_name.strip()
        clean_prompt = prompt_or_preset.strip()

        res = SegmenterRegistry.preview_segmentation(
            domain=clean_dir,
            table_name=clean_tbl,
            segmenter_name_or_prompt=clean_prompt,
            sample_count=int(sample_rows)
        )

        if res.get("status") == "error":
            return {
                "status": "error",
                "stats_text": f"❌ **Preview Failed:** {res.get('message', 'Unknown error')}",
                "headers": res.get("headers", ["Status", "Message"]),
                "datatypes": res.get("datatypes", ["str", "str"]),
                "data": res.get("data", [["Error", res.get("message", "Unknown error")]]),
                "count": 0
            }

        count = res.get("count", 0)
        stats_text = (
            f"🔬 **Dry-Run Preview Successful** — Generated **{count} sub-row chunk(s)** "
            f"from top {sample_rows} sample row(s) of `{clean_dir}.{clean_tbl}`.\n"
            f"*(No data written to database. Click **✂️ Create Segmented View** to commit.)*"
        )

        return {
            "status": "success",
            "stats_text": stats_text,
            "headers": res.get("headers", []),
            "datatypes": res.get("datatypes", []),
            "data": res.get("data", []),
            "count": count
        }

    @staticmethod
    def handle_create_view(
        domain: str,
        source_table: str,
        view_name: str,
        prompt_or_preset: str
    ) -> Dict[str, Any]:
        """Create a permanent native Pixeltable view from the selected table and segmenter."""
        if not domain or not source_table:
            return {
                "status": "error",
                "stats_text": "⚠️ Please select a Domain and Source Table.",
                "table_choices": [],
                "headers": ["Status", "Message"],
                "datatypes": ["str", "str"],
                "data": [["Error", "Domain and Source Table required."]],
                "count": 0
            }

        if not view_name or not view_name.strip():
            return {
                "status": "error",
                "stats_text": "⚠️ Please provide a Target View Name.",
                "table_choices": [],
                "headers": ["Status", "Message"],
                "datatypes": ["str", "str"],
                "data": [["Error", "Target View Name required."]],
                "count": 0
            }

        if not prompt_or_preset or not prompt_or_preset.strip():
            return {
                "status": "error",
                "stats_text": "⚠️ Please enter a segmentation prompt or select a preset.",
                "table_choices": [],
                "headers": ["Status", "Message"],
                "datatypes": ["str", "str"],
                "data": [["Error", "Segmentation prompt or preset required."]],
                "count": 0
            }

        clean_dir = domain.strip()
        clean_src = source_table.strip()
        is_valid_view, clean_view, err_msg = sanitize_identifier(view_name.strip())
        clean_prompt = prompt_or_preset.strip()

        if not is_valid_view or not clean_view:
            return {
                "status": "error",
                "stats_text": f"⚠️ Invalid target view name: {err_msg or 'Name contains no valid alphanumeric characters.'}",
                "table_choices": DBManager.list_tables(clean_dir),
                "headers": ["Status", "Message"],
                "datatypes": ["str", "str"],
                "data": [["Error", err_msg or "Invalid target view name."]],
                "count": 0
            }

        if clean_src == clean_view:
            return {
                "status": "error",
                "stats_text": "⚠️ Target View Name cannot be identical to Source Table name.",
                "table_choices": [],
                "headers": ["Status", "Message"],
                "datatypes": ["str", "str"],
                "data": [["Error", "View name must differ from source table name."]],
                "count": 0
            }

        res = SegmenterRegistry.create_segmented_view(
            domain=clean_dir,
            source_table=clean_src,
            view_name=clean_view,
            segmenter_name_or_prompt=clean_prompt
        )

        if res.get("status") == "error":
            return {
                "status": "error",
                "stats_text": f"❌ **Failed to Create View:** {res.get('message', 'Unknown error')}",
                "table_choices": DBManager.list_tables(clean_dir),
                "headers": ["Status", "Message"],
                "datatypes": ["str", "str"],
                "data": [["Error", res.get("message", "Unknown error")]],
                "count": 0
            }

        # Fetch preview data from newly created view
        view_data_res = DBManager.get_table_data(clean_dir, clean_view, limit=50, lightweight=False)
        headers = view_data_res.get("columns", res.get("columns", []))
        datatypes = view_data_res.get("datatypes", ["str"] * len(headers))
        data = view_data_res.get("data", [])
        total_rows = res.get("count", len(data))

        stats_text = (
            f"✅ **Segmented View Created Successfully!**\n"
            f"- **View Name:** `{clean_dir}.{clean_view}`\n"
            f"- **Source Table:** `{clean_dir}.{clean_src}`\n"
            f"- **Segmenter:** `{res.get('segmenter', 'native')}`\n"
            f"- **Total Rows:** **{total_rows}** segmented rows\n"
            f"- **Lineage:** Zero data copied; auto-propagates on new ingestions. "
            f"Ready for prompt enhancement on the **Data Enhancement** tab."
        )

        all_tables = DBManager.list_tables(clean_dir)
        update_last_entry(last_domain=clean_dir, last_table=clean_view)

        return {
            "status": "success",
            "stats_text": stats_text,
            "created_view": clean_view,
            "table_choices": all_tables,
            "headers": headers,
            "datatypes": datatypes,
            "data": data,
            "count": total_rows
        }
