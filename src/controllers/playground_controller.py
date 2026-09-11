"""
Playground Controller
=====================
Decoupled business logic controller for prompt testing, batch execution,
column auto-splitting, and 1-click lineage undo in the Data Enhancement tab.
"""

import os
from typing import List, Dict, Any, Optional, Callable, Tuple
from src.core.config import get_settings, update_last_entry, get_domain_system_prompt
from src.core.llm_service import LLMService
from src.db.manager import DBManager
from src.prompts.executor import PromptExecutor

class PlaygroundController:
    """Pure controller handling interactive prompt iteration, column commits, and undo."""

    @staticmethod
    def handle_provider_change(selected_provider: str) -> Dict[str, Any]:
        """Discover models for provider and resolve last/default choice."""
        models = LLMService.list_models_for_provider(selected_provider)
        curr = get_settings()
        if selected_provider == "Gemini":
            chosen = curr.default_gemini_model if curr.default_gemini_model in models else (models[0] if models else "gemini-3.7-flash")
        else:
            chosen = curr.default_ollama_model if curr.default_ollama_model in models else (models[0] if models else "llama3.2")
        update_last_entry(last_provider=selected_provider, last_model=chosen)
        return {
            "choices": models,
            "value": chosen
        }

    @staticmethod
    def handle_domain_change(selected_domain: str) -> Dict[str, Any]:
        """Discover tables when domain selection changes."""
        if not selected_domain:
            return {"choices": [], "value": ""}
        domain_str = selected_domain.strip()
        update_last_entry(last_domain=domain_str)

        discovered_tables = DBManager.list_tables(domain_str)
        if not discovered_tables:
            discovered_tables = ["raw_assets"]

        curr_settings = get_settings()
        selected_tbl = curr_settings.last_table if curr_settings.last_table in discovered_tables else discovered_tables[0]
        return {
            "choices": discovered_tables,
            "value": selected_tbl
        }

    @staticmethod
    def load_table_preview(domain: str, table_name: str, lightweight: bool = True, limit: int = 10, target_sample_count: int = 2) -> Dict[str, Any]:
        """Fetch table preview, format stats markdown, and generate column placeholders with target row highlights."""
        if not domain or not table_name:
            return {
                "status": "error",
                "stats_text": "⚠️ Select a valid Domain and Table.",
                "columns": ["Notice"],
                "datatypes": ["str"],
                "data": [["No table selected"]],
                "placeholders_text": "💡 **Available Column Placeholders:** *No table selected.*"
            }

        clean_dir = domain.strip()
        clean_tbl = table_name.strip()
        res = DBManager.get_table_data(clean_dir, clean_tbl, limit=limit, lightweight=lightweight)

        if res.get("error"):
            return {
                "status": "error",
                "stats_text": f"⚠️ **Table `{clean_dir}.{clean_tbl}` not found or empty.**",
                "columns": ["Status"],
                "datatypes": ["str"],
                "data": [[res.get("error")]],
                "placeholders_text": "💡 **Available Column Placeholders:** *Error loading table.*"
            }

        raw_cols = res.get("columns", [])
        raw_data = res.get("data", [])
        datatypes = res.get("datatypes", ["str"] * len(raw_cols))
        total = res.get("total_rows", len(raw_data))
        mode_label = "⚡ Lightweight" if lightweight else "🔍 Full Media"

        # Add Row Target column to clearly show rows targeted for testing
        cols = ["Target"] + raw_cols
        enriched_datatypes = ["str"] + datatypes
        enriched_data = []
        for idx, row in enumerate(raw_data):
            target_badge = f"🎯 Test Row {idx + 1}" if idx < target_sample_count else "—"
            enriched_data.append([target_badge] + list(row))

        info_text = f"✅ **Table `{res.get('domain', clean_dir)}.{res.get('table', clean_tbl)}`** ({mode_label}) — Total Rows: **{total}** (showing first {len(raw_data)}, top {min(target_sample_count, len(raw_data))} targeted for sample testing)"

        # Discover additional metadata keys (such as ingested CSV columns)
        meta_keys = []
        if "metadata" in raw_cols and len(raw_data) > 0:
            meta_idx = raw_cols.index("metadata")
            first_meta = raw_data[0][meta_idx]
            if isinstance(first_meta, dict):
                meta_keys = list(first_meta.keys())
            elif isinstance(first_meta, str) and first_meta.startswith("{"):
                try:
                    import json
                    meta_keys = list(json.loads(first_meta).keys())
                except Exception:
                    pass

        visible_cols = [c for c in raw_cols if c not in ("media_preview", "metadata")]
        pills = [f"`{{{c}}}`" for c in visible_cols]
        if meta_keys:
            pills.extend([f"`{{{k}}}`" for k in meta_keys if k not in visible_cols])
        cols_pills = ", ".join(pills) if pills else "*None*"
        cols_text = f"💡 **Available Column Placeholders:** {cols_pills} | Standard: `{{file_name}}`, `{{content}}`, `{{rel_path}}`, `{{modality}}`, `{{file_size}}`"

        return {
            "status": "success",
            "stats_text": info_text,
            "columns": cols,
            "raw_columns": raw_cols,
            "datatypes": enriched_datatypes,
            "data": enriched_data,
            "placeholders_text": cols_text,
            "total_rows": total
        }

    @staticmethod
    def test_sample_flow(
        domain: str,
        table_name: str,
        provider: str,
        model: str,
        system_prompt: Optional[str] = None,
        prompt_template: str = "",
        sample_count: int = 1,
        output_mode: str = "⚡ Auto-Split JSON Keys into Columns",
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Dict[str, Any]:
        """Execute prompt dry-run against 1–N sample rows with side-by-side inspection."""
        if not domain or not table_name:
            return {
                "status": "error",
                "message": "Domain and Table selection required.",
                "headers": ["Error"],
                "data": [["Domain and Table selection required."]]
            }

        if not model:
            return {
                "status": "error",
                "message": f"{provider} model selection required.",
                "headers": ["Error"],
                "data": [[f"{provider} model selection required."]]
            }

        clean_dir = domain.strip()
        clean_tbl = table_name.strip()
        resolved_sys_prompt = system_prompt.strip() if system_prompt and system_prompt.strip() else get_domain_system_prompt(clean_dir)
        is_auto_split = (output_mode == "⚡ Auto-Split JSON Keys into Columns")

        update_last_entry(
            last_domain=clean_dir,
            last_table=clean_tbl,
            last_provider=provider,
            last_model=model,
            last_system_prompt=resolved_sys_prompt,
            last_user_prompt=prompt_template
        )

        try:
            results = PromptExecutor.run_sample_test(
                model=model,
                prompt_template=prompt_template,
                system_prompt=resolved_sys_prompt,
                table_dir=clean_dir,
                table_name=clean_tbl,
                provider=provider,
                sample_count=int(sample_count),
                auto_split=is_auto_split,
                progress_callback=progress_callback
            )

            if is_auto_split:
                all_keys = []
                for r in results:
                    for k in r.get("extracted_columns", []):
                        if k not in all_keys:
                            all_keys.append(k)

                if all_keys:
                    headers = ["Status", "Row ID", "File Name"] + all_keys
                    rows = []
                    for r in results:
                        parsed = r.get("parsed_json", {})
                        row_vals = ["🧪 Test Preview", str(r.get("row_id", "")), str(r.get("file_name", ""))] + [str(parsed.get(k, "")) for k in all_keys]
                        rows.append(row_vals)
                    return {
                        "status": "success",
                        "headers": headers,
                        "data": rows,
                        "count": len(rows),
                        "keys": all_keys
                    }

            headers = ["Status", "Row ID", "File Name", "Source Snippet", "Rendered Prompt", "Model Output"]
            rows = [
                ["🧪 Test Preview", str(r.get("row_id", "")), str(r.get("file_name", "")), str(r.get("source_content", "")), str(r.get("prompt_rendered", "")), str(r.get("llm_output", r.get("model_output", "")))]
                for r in results
            ]
            return {
                "status": "success",
                "headers": headers,
                "data": rows,
                "count": len(rows)
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "headers": ["Error"],
                "data": [[str(e)]]
            }

    @staticmethod
    def commit_batch_flow(
        domain: str,
        table_name: str,
        provider: str,
        model: str,
        system_prompt: Optional[str] = None,
        prompt_template: str = "",
        output_mode: str = "⚡ Auto-Split JSON Keys into Columns",
        target_column: str = "llm_summary",
        write_mode: str = "replace",
        limit_rows: int = 0,
        is_lightweight: bool = True,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Dict[str, Any]:
        """Apply tested prompt across table rows and save newly generated columns."""
        if not domain or not table_name:
            return {
                "status": "error",
                "message": "⚠️ Please select a valid Domain and Table."
            }

        clean_dir = domain.strip()
        clean_tbl = table_name.strip()
        is_auto_split = (output_mode == "⚡ Auto-Split JSON Keys into Columns")
        clean_col = target_column.strip() if target_column and target_column.strip() else "llm_summary"

        if not is_auto_split and not clean_col:
            return {
                "status": "error",
                "message": "⚠️ Please specify a Target Column Name."
            }

        resolved_sys_prompt = system_prompt.strip() if system_prompt and system_prompt.strip() else get_domain_system_prompt(clean_dir)

        update_last_entry(
            last_domain=clean_dir,
            last_table=clean_tbl,
            last_provider=provider,
            last_model=model,
            last_system_prompt=resolved_sys_prompt,
            last_user_prompt=prompt_template
        )

        limit_val = int(limit_rows) if limit_rows and int(limit_rows) > 0 else None

        res = PromptExecutor.apply_prompt_to_table(
            model=model.strip(),
            prompt_template=prompt_template,
            system_prompt=resolved_sys_prompt,
            table_dir=clean_dir,
            table_name=clean_tbl,
            target_column=clean_col,
            provider=provider,
            auto_split=is_auto_split,
            mode=write_mode,
            limit=limit_val,
            progress_callback=progress_callback
        )

        if res.get("status") == "success":
            cols_created = res.get("columns", [clean_col])
            rows_done = res.get("rows_processed", 0)
            status_msg = (
                f"### ✅ Batch Execution Successful!\n"
                f"- **Table:** `{clean_dir}.{clean_tbl}`\n"
                f"- **Rows Enriched:** {rows_done}\n"
                f"- **Columns Created / Updated:** `{', '.join(cols_created)}`\n"
                f"- **Model / Provider:** `{provider}` ({model})"
            )
            # Fetch updated table data with newly created columns highlighted
            raw_preview = DBManager.get_table_data(clean_dir, clean_tbl, limit=25, lightweight=is_lightweight)
            raw_cols = raw_preview.get("columns", [])
            raw_data = raw_preview.get("data", [])

            # Prioritize newly created columns so they appear immediately after row identifier columns
            lead_cols = [c for c in ["id", "file_name"] if c in raw_cols]
            created_in_raw = [c for c in cols_created if c in raw_cols and c not in lead_cols]
            other_cols = [c for c in raw_cols if c not in lead_cols and c not in created_in_raw]
            ordered_cols = lead_cols + created_in_raw + other_cols

            # Reorder row cells to match ordered_cols
            col_indices = [raw_cols.index(c) for c in ordered_cols]
            out_headers = ["Status"] + ordered_cols

            out_rows = []
            for idx, r in enumerate(raw_data):
                reordered_row = [r[i] for i in col_indices]
                status_tag = f"💾 Saved ({idx + 1})" if idx < rows_done else "— (Unchanged)"
                out_rows.append([status_tag] + reordered_row)

            return {
                "status": "success",
                "message": status_msg,
                "output_headers": out_headers,
                "output_data": out_rows,
                "columns_created": cols_created,
                "rows_processed": rows_done
            }
        else:
            return {
                "status": "error",
                "message": f"### ❌ Batch Execution Failed\n```\n{res.get('message', 'Unknown error')}\n```"
            }

    @staticmethod
    def undo_last_operation_flow(domain: str, table_name: str, is_lightweight: bool = True) -> Dict[str, Any]:
        """Execute 1-click lineage undo to drop newly added LLM columns and restore table schema."""
        if not domain or not table_name:
            return {
                "status": "error",
                "message": "⚠️ Please select a valid Domain and Table."
            }

        clean_dir = domain.strip()
        clean_tbl = table_name.strip()
        undo_res = DBManager.undo_last_operation(clean_dir, clean_tbl)

        if undo_res.get("status") == "success":
            status_msg = f"### ↩️ Operation Undone\n{undo_res.get('message', '')}"
            preview = PlaygroundController.load_table_preview(clean_dir, clean_tbl, lightweight=is_lightweight)
            return {
                "status": "success",
                "message": status_msg,
                "preview": preview
            }
        else:
            return {
                "status": "error",
                "message": f"### ⚠️ Undo Not Available\n{undo_res.get('message', 'No undo operations available.')}"
            }
