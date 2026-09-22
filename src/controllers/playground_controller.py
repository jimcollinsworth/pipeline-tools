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

        # Check if prompt triggers a registered declarative UDF (single, multiple, or hybrid with LLM)
        from src.core.udf_registry import UDFRegistry
        udf_matches = UDFRegistry.match_all_prompts(prompt_template)
        remaining_prompt = UDFRegistry.strip_udf_triggers(prompt_template) if udf_matches else prompt_template
        has_llm = bool(remaining_prompt.strip())

        udf_headers: List[str] = []
        udf_datatypes: List[str] = []
        udf_rows: List[List[Any]] = []

        if udf_matches:
            if len(udf_matches) == 1 and not has_llm:
                udf_def, udf_kwargs = udf_matches[0]
                if progress_callback:
                    progress_callback(0.5, f"Evaluating declarative UDF '{udf_def.name}' on {sample_count} sample rows...")
                return udf_def.sample_eval_fn(clean_dir, clean_tbl, sample_count=sample_count, **udf_kwargs)

            total_udfs = len(udf_matches)
            for u_idx, (udf_def, udf_kwargs) in enumerate(udf_matches):
                if progress_callback:
                    progress_callback(
                        u_idx / (total_udfs + (1 if has_llm else 0)),
                        f"Evaluating declarative UDF '{udf_def.name}' ({u_idx + 1}/{total_udfs}) on {sample_count} sample rows..."
                    )
                res = udf_def.sample_eval_fn(clean_dir, clean_tbl, sample_count=sample_count, **udf_kwargs)
                if res.get("status") != "success":
                    return res

                res_headers = res.get("headers", [])
                res_datatypes = res.get("datatypes", ["str"] * len(res_headers))
                res_data = res.get("data", [])

                if not udf_headers:
                    udf_headers = ["Status", "Row ID", "File Name"]
                    udf_datatypes = ["str", "str", "str"]

                extra_indices = []
                for i, h in enumerate(res_headers):
                    if h in ("Status", "Row ID", "File Name"):
                        continue
                    final_h = h
                    if final_h in udf_headers:
                        final_h = f"{udf_def.name}_{h}"
                    extra_indices.append(i)
                    udf_headers.append(final_h)
                    udf_datatypes.append(res_datatypes[i] if i < len(res_datatypes) else "str")

                if not udf_rows:
                    for row in res_data:
                        lead = [
                            row[0] if len(row) > 0 else "🧪 UDF Sample Test",
                            row[1] if len(row) > 1 else "",
                            row[2] if len(row) > 2 else ""
                        ]
                        udf_rows.append(lead)

                while len(udf_rows) < len(res_data):
                    r_idx = len(udf_rows)
                    row = res_data[r_idx]
                    lead = [
                        row[0] if len(row) > 0 else "🧪 UDF Sample Test",
                        row[1] if len(row) > 1 else "",
                        row[2] if len(row) > 2 else ""
                    ]
                    lead.extend([""] * (len(udf_headers) - 3))
                    udf_rows.append(lead)

                for r_idx in range(len(udf_rows)):
                    if r_idx < len(res_data):
                        row = res_data[r_idx]
                        for c_idx in extra_indices:
                            val = row[c_idx] if c_idx < len(row) else ""
                            udf_rows[r_idx].append(val)
                    else:
                        for _ in extra_indices:
                            udf_rows[r_idx].append("")

            if not has_llm:
                if progress_callback:
                    progress_callback(1.0, f"Evaluated {total_udfs} UDFs on {len(udf_rows)} sample rows.")
                return {
                    "status": "success",
                    "headers": udf_headers,
                    "datatypes": udf_datatypes,
                    "data": udf_rows,
                    "count": len(udf_rows),
                    "is_udf": True
                }

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
                prompt_template=remaining_prompt,
                system_prompt=resolved_sys_prompt,
                table_dir=clean_dir,
                table_name=clean_tbl,
                provider=provider,
                sample_count=int(sample_count),
                auto_split=is_auto_split,
                progress_callback=progress_callback
            )

            all_keys = []
            if is_auto_split:
                for r in results:
                    for k in r.get("extracted_columns", []):
                        if k not in all_keys:
                            all_keys.append(k)

                if all_keys:
                    llm_cols = all_keys
                    llm_types = ["str"] * len(all_keys)
                    llm_data_cells = []
                    for r in results:
                        parsed = r.get("parsed_json", {})
                        llm_data_cells.append([str(parsed.get(k, "")) for k in all_keys])
                else:
                    llm_cols = ["Model Output"]
                    llm_types = ["str"]
                    llm_data_cells = [[str(r.get("llm_output", r.get("model_output", "")))] for r in results]
            else:
                llm_cols = ["Source Snippet", "Rendered Prompt", "Model Output"]
                llm_types = ["str", "str", "str"]
                llm_data_cells = [
                    [str(r.get("source_content", "")), str(r.get("prompt_rendered", "")), str(r.get("llm_output", r.get("model_output", "")))]
                    for r in results
                ]

            if udf_headers:
                merged_headers = list(udf_headers) + llm_cols
                merged_datatypes = list(udf_datatypes) + llm_types
                merged_rows = []
                for r_idx in range(max(len(udf_rows), len(llm_data_cells))):
                    u_part = udf_rows[r_idx] if r_idx < len(udf_rows) else (["🧪 Sample Test", "", ""] + [""] * (len(udf_headers) - 3))
                    l_part = llm_data_cells[r_idx] if r_idx < len(llm_data_cells) else [""] * len(llm_cols)
                    merged_rows.append(list(u_part) + list(l_part))

                if progress_callback:
                    progress_callback(1.0, f"Evaluated {len(udf_matches)} UDFs and LLM on {len(merged_rows)} sample rows.")

                return {
                    "status": "success",
                    "headers": merged_headers,
                    "datatypes": merged_datatypes,
                    "data": merged_rows,
                    "count": len(merged_rows),
                    "is_udf": True
                }

            full_headers = ["Status", "Row ID", "File Name"] + llm_cols
            full_datatypes = ["str", "str", "str"] + llm_types
            full_rows = []
            for idx, r in enumerate(results):
                lead = ["🧪 Test Preview", str(r.get("row_id", "")), str(r.get("file_name", ""))]
                row_vals = llm_data_cells[idx] if idx < len(llm_data_cells) else [""] * len(llm_cols)
                full_rows.append(lead + row_vals)

            return {
                "status": "success",
                "headers": full_headers,
                "datatypes": full_datatypes,
                "data": full_rows,
                "count": len(full_rows),
                "keys": all_keys if is_auto_split else []
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

        from src.core.udf_registry import UDFRegistry
        udf_matches = UDFRegistry.match_all_prompts(prompt_template)
        remaining_prompt = UDFRegistry.strip_udf_triggers(prompt_template) if udf_matches else prompt_template
        has_llm = bool(remaining_prompt.strip())

        all_cols_created = []
        udf_summary_lines = []

        if udf_matches:
            total_udfs = len(udf_matches)
            for u_idx, (udf_def, udf_kwargs) in enumerate(udf_matches):
                if progress_callback:
                    progress_callback(
                        u_idx / (total_udfs + (1 if has_llm else 0)),
                        f"Declaratively attaching UDF '{udf_def.name}' ({u_idx + 1}/{total_udfs}) computed columns to table..."
                    )
                attach_res = udf_def.attach_fn(clean_dir, clean_tbl, **udf_kwargs)
                if attach_res.get("status") != "success":
                    return {
                        "status": "error",
                        "message": f"### ❌ UDF '{udf_def.name}' Execution Failed\n```\n{attach_res.get('message', 'Unknown error')}\n```"
                    }
                cols = attach_res.get("columns", [])
                for c in cols:
                    if c not in all_cols_created:
                        all_cols_created.append(c)
                udf_summary_lines.append(
                    f"- **UDF:** `{udf_def.name}` ({', '.join(f'{k}={v}' for k, v in udf_kwargs.items())}) -> Columns: `{', '.join(cols)}`"
                )

        if not has_llm:
            if progress_callback:
                progress_callback(1.0, f"Successfully attached {len(all_cols_created)} columns from {len(udf_matches)} UDFs.")

            raw_preview = DBManager.get_table_data(clean_dir, clean_tbl, limit=25, lightweight=is_lightweight)
            raw_cols = raw_preview.get("columns", [])
            raw_data = raw_preview.get("data", [])

            lead_cols = [c for c in ["id", "file_name"] if c in raw_cols]
            created_in_raw = [c for c in all_cols_created if c in raw_cols and c not in lead_cols]
            other_cols = [c for c in raw_cols if c not in lead_cols and c not in created_in_raw]
            ordered_cols = lead_cols + created_in_raw + other_cols

            col_indices = [raw_cols.index(c) for c in ordered_cols]
            out_headers = ["Status"] + ordered_cols
            out_rows = []
            for idx, r in enumerate(raw_data):
                reordered_row = [r[i] for i in col_indices]
                out_rows.append([f"💾 Saved ({idx + 1})"] + reordered_row)

            raw_dt = raw_preview.get("datatypes", ["str"] * len(raw_cols))
            dt_map = dict(zip(raw_cols, raw_dt))
            out_datatypes = ["str"] + [dt_map.get(c, "str") for c in ordered_cols]

            status_msg = (
                f"### ✅ UDF Batch Execution Successful!\n"
                f"- **Table:** `{clean_dir}.{clean_tbl}`\n"
                + "\n".join(udf_summary_lines) + "\n"
                f"- **Total Columns Attached:** `{', '.join(all_cols_created)}`\n"
                f"- **Execution Model:** Declarative Pixeltable Computed Columns (zero row loops)"
            )
            return {
                "status": "success",
                "message": status_msg,
                "output_headers": out_headers,
                "output_datatypes": out_datatypes,
                "output_data": out_rows,
                "columns_created": all_cols_created,
                "rows_processed": len(raw_data)
            }

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
            prompt_template=remaining_prompt,
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
            llm_cols_created = res.get("columns", [clean_col])
            rows_done = res.get("rows_processed", 0)
            for c in llm_cols_created:
                if c not in all_cols_created:
                    all_cols_created.append(c)

            summary_header = "### ✅ Hybrid (UDF + LLM) Batch Execution Successful!" if udf_matches else "### ✅ Batch Execution Successful!"
            status_msg = (
                f"{summary_header}\n"
                f"- **Table:** `{clean_dir}.{clean_tbl}`\n"
                + (("\n".join(udf_summary_lines) + "\n") if udf_summary_lines else "")
                + f"- **Rows Enriched:** {rows_done}\n"
                f"- **All Columns Created / Updated:** `{', '.join(all_cols_created)}`\n"
                f"- **Model / Provider:** `{provider}` ({model})"
            )
            # Fetch updated table data with newly created columns highlighted
            raw_preview = DBManager.get_table_data(clean_dir, clean_tbl, limit=25, lightweight=is_lightweight)
            raw_cols = raw_preview.get("columns", [])
            raw_data = raw_preview.get("data", [])

            # Prioritize newly created columns so they appear immediately after row identifier columns
            lead_cols = [c for c in ["id", "file_name"] if c in raw_cols]
            created_in_raw = [c for c in all_cols_created if c in raw_cols and c not in lead_cols]
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

            raw_dt = raw_preview.get("datatypes", ["str"] * len(raw_cols))
            dt_map = dict(zip(raw_cols, raw_dt))
            out_datatypes = ["str"] + [dt_map.get(c, "str") for c in ordered_cols]

            return {
                "status": "success",
                "message": status_msg,
                "output_headers": out_headers,
                "output_datatypes": out_datatypes,
                "output_data": out_rows,
                "columns_created": all_cols_created,
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

    @staticmethod
    def handle_compute_spectrogram(domain: str, table_name: str, is_lightweight: bool = True) -> Dict[str, Any]:
        """Declaratively attach Mel Spectrogram computed columns and refresh preview."""
        if not domain or not table_name:
            return {
                "status": "error",
                "message": "⚠️ Please select a valid Domain and Table."
            }

        from src.audio.spectrogram import attach_spectrogram_columns
        clean_dir = domain.strip()
        clean_tbl = table_name.strip()
        res = attach_spectrogram_columns(clean_dir, clean_tbl)

        if res.get("status") == "success":
            preview = PlaygroundController.load_table_preview(clean_dir, clean_tbl, lightweight=is_lightweight)
            return {
                "status": "success",
                "message": f"### 🎵 Mel Spectrogram Enriched\n{res.get('message', '')}",
                "columns_added": res.get("columns", []),
                "preview": preview
            }
        else:
            return {
                "status": "error",
                "message": f"### ❌ Mel Spectrogram Failed\n{res.get('message', '')}"
            }
