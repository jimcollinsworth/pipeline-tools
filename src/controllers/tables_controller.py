"""
Tables Controller
=================
Decoupled controller for the View & Export tab.
Handles table queries, zero-query row inspection formatting, AI report generation,
and safe 2-step table & domain deletion workflows.
"""

import os
import re
import json
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
            f"Displaying {len(data)} of {total} total rows."
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
    def build_highlighted_spans(text: str, entities: List[Tuple[str, str]]) -> List[Tuple[str, Optional[str]]]:
        """
        Given raw text and a list of (entity_text, category_label) tuples,
        computes non-overlapping matches and returns Gradio HighlightedText spans:
        [(span_text, category_or_None), ...]
        """
        if not text:
            return []
        if not entities:
            return [(text, None)]

        valid_targets = []
        seen = set()
        for ent_text, label in entities:
            if not ent_text or not isinstance(ent_text, str):
                continue
            ent_clean = ent_text.strip()
            if len(ent_clean) < 2 or ent_clean.lower() in seen:
                continue
            seen.add(ent_clean.lower())
            valid_targets.append((ent_clean, label or "Entity"))

        if not valid_targets:
            return [(text, None)]

        valid_targets.sort(key=lambda x: len(x[0]), reverse=True)

        intervals = []  # (start, end, label)
        for ent_text, label in valid_targets:
            pattern = re.escape(ent_text)
            for match in re.finditer(pattern, text, re.IGNORECASE):
                s, e = match.start(), match.end()
                overlap = any(not (e <= existing_s or s >= existing_e) for existing_s, existing_e, _ in intervals)
                if not overlap:
                    intervals.append((s, e, label))

        if not intervals:
            return [(text, None)]

        intervals.sort(key=lambda x: x[0])

        spans: List[Tuple[str, Optional[str]]] = []
        curr_idx = 0
        for s, e, label in intervals:
            if s > curr_idx:
                spans.append((text[curr_idx:s], None))
            spans.append((text[s:e], label))
            curr_idx = e

        if curr_idx < len(text):
            spans.append((text[curr_idx:], None))

        return spans

    @staticmethod
    def extract_entities_from_row_dict(row_dict: Dict[str, Any]) -> List[Tuple[str, str]]:
        """
        Inspects row dictionary to discover extracted entity targets and their category labels.
        Supports lists, JSON strings, dicts, and comma-separated entity column values.
        """
        entities: List[Tuple[str, str]] = []

        LABEL_MAPPING = {
            "people": "Person",
            "person": "Person",
            "c_people": "Person",
            "c_person": "Person",
            "organizations": "Organization",
            "organization": "Organization",
            "c_organizations": "Organization",
            "c_organization": "Organization",
            "orgs": "Organization",
            "c_orgs": "Organization",
            "locations": "Location",
            "location": "Location",
            "c_locations": "Location",
            "c_location": "Location",
            "places": "Location",
            "c_places": "Location",
            "dates": "Date",
            "c_dates": "Date",
            "action_items": "Action Item",
            "c_action_items": "Action Item",
            "key_entities": "Entity",
            "c_key_entities": "Entity",
            "entities": "Entity",
            "c_entities": "Entity",
        }

        def _add_item(item: Any, default_label: str):
            if not item:
                return
            if isinstance(item, str):
                for part in item.split(","):
                    part_clean = part.strip().strip('"').strip("'")
                    if len(part_clean) >= 2:
                        entities.append((part_clean, default_label))
            elif isinstance(item, (list, tuple)):
                for sub in item:
                    _add_item(sub, default_label)
            elif isinstance(item, dict):
                name = item.get("name") or item.get("text") or item.get("entity")
                cat = item.get("type") or item.get("label") or item.get("category") or default_label
                if name and isinstance(name, str) and len(name.strip()) >= 2:
                    entities.append((name.strip(), str(cat)))

        core_cols = {"id", "file_name", "file_path", "rel_path", "modality", "file_type", "file_size", "content", "media_preview", "doc", "image", "audio", "video", "metadata", "created_at"}

        for col_name, val in row_dict.items():
            if col_name in core_cols or val is None:
                continue

            lower_col = col_name.lower().strip()
            default_label = LABEL_MAPPING.get(lower_col, lower_col.replace("c_", "").replace("_", " ").title())

            if isinstance(val, str) and (val.startswith("{") or val.startswith("[")):
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, dict):
                        for k, sub_val in parsed.items():
                            sub_lbl = LABEL_MAPPING.get(k.lower(), k.replace("_", " ").title())
                            _add_item(sub_val, sub_lbl)
                    elif isinstance(parsed, list):
                        _add_item(parsed, default_label)
                except Exception:
                    _add_item(val, default_label)
            else:
                _add_item(val, default_label)

        return entities

    @staticmethod
    def handle_row_inspection(row_idx: int, current_df: Any, domain: str, table_name: str) -> Dict[str, Any]:
        """Format row details, media file paths, extracted text, and highlighted entities for the Media Inspector drawer."""
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

        extracted_entities = TablesController.extract_entities_from_row_dict(row_dict)
        highlighted_spans = TablesController.build_highlighted_spans(content, extracted_entities) if (has_content and extracted_entities) else []
        has_highlighted = bool(highlighted_spans and any(lbl is not None for _, lbl in highlighted_spans))

        return {
            "image_path": img_val,
            "has_image": bool(img_val),
            "audio_path": audio_val,
            "has_audio": bool(audio_val),
            "video_path": video_val,
            "has_video": bool(video_val),
            "details_markdown": details_md,
            "content_text": content if has_content else "",
            "has_content": has_content,
            "highlighted_spans": highlighted_spans,
            "has_highlighted": has_highlighted
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

    @staticmethod
    def filter_dataframe_columns(data: list, columns: list, selected_columns: list) -> Tuple[list, list]:
        """Project a 2D dataset to only include columns specified in selected_columns."""
        if not selected_columns:
            return data, columns

        active_indices = [i for i, col in enumerate(columns) if col in selected_columns]
        if not active_indices:
            return data, columns

        filtered_columns = [columns[i] for i in active_indices]
        filtered_data = [
            [row[i] for i in active_indices if i < len(row)]
            for row in data
        ]
        return filtered_data, filtered_columns

    @staticmethod
    def navigate_row(current_index: int, delta: int, total_rows: int) -> int:
        """Clamp row navigation index between 0 and total_rows - 1."""
        if total_rows <= 0:
            return 0
        new_idx = current_index + delta
        return max(0, min(total_rows - 1, new_idx))

    @classmethod
    def format_document_view(cls, row_dict: Dict[str, Any], active_columns: Optional[list] = None, row_index: int = 0, total_rows: int = 1) -> Dict[str, Any]:
        """Format a single table row into a structured document view representation."""
        if not row_dict:
            return {
                "counter_text": "Record 0 of 0",
                "title_text": "No Record Selected",
                "modality": "unknown",
                "media_path": "",
                "highlighted_spans": [],
                "attributes_md": "*No attributes available.*"
            }

        safe_index = max(0, row_index)
        safe_total = max(1, total_rows)
        counter_text = f"Record {safe_index + 1} of {safe_total}"

        title_text = str(row_dict.get("file_name") or row_dict.get("id") or f"Record #{safe_index + 1}")
        modality = str(row_dict.get("modality") or "unknown").lower()
        media_path = str(row_dict.get("file_path") or row_dict.get("path") or "")

        content_text = str(row_dict.get("content") or "")
        entities_dict = cls.extract_entities_from_row_dict(row_dict)
        highlighted_spans = cls.build_highlighted_spans(content_text, entities_dict) if content_text else []

        cols_to_show = active_columns if active_columns else list(row_dict.keys())
        excluded_keys = {"content", "thumbnail"}

        attr_lines = []
        for k in cols_to_show:
            if k in row_dict and k not in excluded_keys:
                val = row_dict[k]
                if val is not None and str(val).strip():
                    attr_lines.append(f"- **{k}**: {val}")

        attributes_md = "\n".join(attr_lines) if attr_lines else "*No additional attributes selected.*"

        return {
            "counter_text": counter_text,
            "title_text": title_text,
            "modality": modality,
            "media_path": media_path,
            "highlighted_spans": highlighted_spans,
            "attributes_md": attributes_md
        }
