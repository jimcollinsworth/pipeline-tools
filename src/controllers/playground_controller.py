"""
Playground Controller
=====================
Decoupled business logic controller for prompt testing, batch execution,
column auto-splitting, and 1-click lineage undo in the Data Enhancement tab.
"""

import os
from typing import List, Dict, Any, Optional, Callable, Tuple
from src.core.config import get_settings, update_last_entry
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
    def load_table_preview(domain: str, table_name: str, lightweight: bool = True, limit: int = 10) -> Dict[str, Any]:
        """Fetch table preview, format stats markdown, and generate column placeholders."""
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

        cols = res.get("columns", [])
        datatypes = res.get("datatypes", ["str"] * len(cols))
        data = res.get("data", [])
        total = res.get("total_rows", len(data))
        mode_label = "⚡ Lightweight" if lightweight else "🔍 Full Media"

        info_text = f"✅ **Table `{res.get('domain', clean_dir)}.{res.get('table', clean_tbl)}`** ({mode_label}) — Total Rows: **{total}** (showing first {len(data)})"
        cols_pills = ", ".join([f"`{{{c}}}`" for c in cols if c != "media_preview"]) if cols else "*None*"
        cols_text = f"💡 **Available Column Placeholders:** {cols_pills} | Standard: `{{file_name}}`, `{{content}}`, `{{rel_path}}`, `{{modality}}`, `{{file_size}}`"

        return {
            "status": "success",
            "stats_text": info_text,
            "columns": cols,
            "datatypes": datatypes,
            "data": data,
            "placeholders_text": cols_text,
            "total_rows": total
        }

    @staticmethod
    def test_sample_flow(
        domain: str,
        table_name: str,
        provider: str,
        model: str,
        system_prompt: str,
        prompt_template: str,
        sample_count: int = 1,
        output_mode: str = "⚡ Auto-Split JSON Keys into Columns",
        enable_vision: bool = False,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Dict[str, Any]:
        """Execute prompt dry-run against 1–N sample rows with side-by-side inspection and telemetry."""
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
        update_last_entry(
            last_domain=clean_dir,
            last_table=clean_tbl,
            last_provider=provider,
            last_model=model,
            last_system_prompt=system_prompt,
            last_prompt_template=prompt_template
        )

        res = PromptExecutor.test_sample_prompt(
            dir_name=clean_dir,
            table_name=clean_tbl,
            prompt_template=prompt_template,
            system_prompt=system_prompt,
            provider=provider,
            model=model,
            limit=int(sample_count),
            enable_vision=enable_vision,
            progress_callback=progress_callback
        )

        if res.get("status") == "success":
            results = res.get("results", [])
            headers = ["Row ID", "File Name", "Telemetry & Speed", "Source Snippet", "Rendered Prompt", "Model Output"]
            rows = []
            for r in results:
                rows.append([
                    str(r.get("row_id", "")),
                    str(r.get("file_name", "")),
                    str(r.get("telemetry", "⚡ Fast (<1s)")),
                    str(r.get("source_snippet", "")),
                    str(r.get("rendered_prompt", "")),
                    str(r.get("llm_output", ""))
                ])
            return {
                "status": "success",
                "headers": headers,
                "data": rows,
                "count": len(rows)
            }
        else:
            return {
                "status": "error",
                "message": res.get("message", "Error running prompt test"),
                "headers": ["Error"],
                "data": [[res.get("message", "Error running prompt test")]]
            }

    @staticmethod
    def cancel_execution() -> None:
        """Signal prompt executor to halt running batch operations."""
        PromptExecutor.cancel_execution()

    @staticmethod
    def commit_batch_flow(
        domain: str,
        table_name: str,
        provider: str,
        model: str,
        system_prompt: str,
        prompt_template: str,
        output_mode: str,
        target_column: str,
        write_mode: str = "replace",
        limit_rows: int = 0,
        enable_vision: bool = False,
        is_lightweight: bool = True,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Dict[str, Any]:
        """Apply tested prompt across table rows using native Pixeltable computed columns."""
        if not domain or not table_name:
            return {
                "status": "error",
                "message": "⚠️ Please select a valid Domain and Table."
            }

        clean_dir = domain.strip()
        clean_tbl = table_name.strip()
        is_auto_split = (output_mode == "⚡ Auto-Split JSON Keys into Columns")

        if not is_auto_split and not target_column.strip():
            return {
                "status": "error",
                "message": "⚠️ Please specify a Target Column Name."
            }

        update_last_entry(
            last_domain=clean_dir,
            last_table=clean_tbl,
            last_provider=provider,
            last_model=model,
            last_system_prompt=system_prompt,
            last_prompt_template=prompt_template
        )

        res = PromptExecutor.apply_prompt_to_table(
            dir_name=clean_dir,
            table_name=clean_tbl,
            prompt_template=prompt_template,
            system_prompt=system_prompt,
            target_column=target_column.strip() if not is_auto_split else "json_extract",
            provider=provider,
            model=model,
            write_mode=write_mode,
            limit=int(limit_rows),
            auto_split_json=is_auto_split,
            enable_vision=enable_vision,
            progress_callback=progress_callback
        )

        if res.get("status") == "success":
            cols = res.get("columns", [target_column])
            status_msg = (
                f"### ✅ Batch Execution Successful!\n"
                f"- **Table:** `{clean_dir}.{clean_tbl}`\n"
                f"- **Rows Enriched:** {res.get('rows_processed', 0)}\n"
                f"- **Columns Created / Updated:** `{', '.join(cols)}`\n"
                f"- **Model / Provider:** `{provider}` ({model})"
            )
            # Fetch fresh preview
            preview = PlaygroundController.load_table_preview(clean_dir, clean_tbl, lightweight=is_lightweight)
            return {
                "status": "success",
                "message": status_msg,
                "preview": preview
            }
        elif res.get("status") == "warning":
            cols = res.get("columns", [target_column])
            status_msg = (
                f"### ⚠️ Batch Execution Halted (Partial Results Saved)\n"
                f"- **Notice:** {res.get('message', '')}\n"
                f"- **Rows Enriched:** {res.get('rows_processed', 0)}\n"
                f"- **Columns:** `{', '.join(cols)}`"
            )
            preview = PlaygroundController.load_table_preview(clean_dir, clean_tbl, lightweight=is_lightweight)
            return {
                "status": "warning",
                "message": status_msg,
                "preview": preview
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
