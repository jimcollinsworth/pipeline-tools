"""
Prompt Execution Engine (LLM Batch Processing & Schema Generation)
===================================================================
This module executes prompt templates over Pixeltable dataset records, supporting both
interactive single-row previews and full batch table enrichment.

Key Features & Engineering Design:
----------------------------------
1. Unified Multi-Provider Routing:
   - Routes generation requests dynamically to local Ollama or cloud Gemini models.
   - Transparently passes media paths for multimodal vision/audio prompts.
2. Robust JSON Extraction (`extract_json_payload`):
   - Handles raw JSON, markdown-wrapped JSON code fences, and text with leading/trailing chatter.
3. Auto-Split Column Type Inference (`infer_pixeltable_type`):
   - Inspects parsed JSON values and dynamically maps them to native Pixeltable schema types:
     * bool -> pxt.Bool
     * int -> pxt.Int
     * float -> pxt.Float
     * list/dict -> pxt.Json
     * string/other -> pxt.String
4. Column Projection Invariant during Batch Runs:
   - Queries avoid collecting heavy binary columns (`doc`, `image`, `video`, `audio`) into RAM,
     ensuring batch processing runs smoothly across large (1,000+ row) datasets.
"""

import re
import os
import json
from typing import List, Dict, Any, Optional, Tuple
from src.core.config import get_settings, sanitize_identifier
from src.core.llm_service import LLMService
from src.core.exceptions import (
    LLMQuotaExceededError,
    LLMAuthError,
    LLMServiceUnavailableError,
    LLMExecutionCancelledError,
)

try:
    import pixeltable as pxt
    PIXELTABLE_AVAILABLE = True
except ImportError:
    pxt = None
    PIXELTABLE_AVAILABLE = False

from src.db.manager import DBManager


def extract_json_payload(response_text: str) -> Optional[Dict[str, Any]]:
    """Robustly extract and parse a JSON object from raw LLM output or markdown blocks."""
    if not response_text or not response_text.strip():
        return None

    raw = response_text.strip()

    # 1. Try direct parse
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 2. Try extracting from markdown code fences (```json ... ``` or ``` ... ```)
    code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.IGNORECASE)
    if code_block_match:
        try:
            data = json.loads(code_block_match.group(1).strip())
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    # 3. Try finding outermost { ... }
    brace_start = raw.find("{")
    brace_end = raw.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        candidate = raw[brace_start:brace_end + 1]
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return None


def infer_pixeltable_type(val: Any) -> Any:
    """Infer the appropriate Pixeltable column type for a Python value."""
    if not PIXELTABLE_AVAILABLE or pxt is None:
        return None

    if isinstance(val, bool):
        return pxt.Bool
    elif isinstance(val, int):
        return pxt.Int
    elif isinstance(val, float):
        return pxt.Float
    elif isinstance(val, (dict, list)):
        return pxt.Json
    return pxt.String


def format_cell_value(val: Any) -> Any:
    """Format extracted JSON value cleanly for Pixeltable storage."""
    if isinstance(val, list):
        if all(isinstance(x, (str, int, float)) for x in val):
            return ", ".join(str(x) for x in val)
        return val
    elif isinstance(val, dict):
        return val
    return val


def get_row_media_path(row: Dict[str, Any], enable_vision: bool = False) -> Optional[str]:
    """Inspect row fields and return absolute media path ONLY if enable_vision is True."""
    if not enable_vision:
        return None
    for field in ["image", "file_path", "doc", "video", "audio"]:
        p = row.get(field)
        if p and isinstance(p, str) and os.path.exists(p):
            ext = os.path.splitext(p)[1].lower()
            if ext in [".jpg", ".jpeg", ".png", ".webp", ".pdf"]:
                return p
    return None


if PIXELTABLE_AVAILABLE and pxt is not None:
    @pxt.udf
    def pxt_generate_text(
        prompt: str,
        system: str = "",
        model: str = "llama3.2",
        provider: str = "Ollama",
        json_mode: bool = False,
        media_path: str = ""
    ) -> str:
        """Declarative Pixeltable UDF for single-column text generation."""
        return LLMService.generate(
            provider=provider,
            model=model,
            prompt=prompt,
            system=system,
            media_path=media_path if media_path else None,
            json_mode=json_mode
        )

    @pxt.udf
    def pxt_generate_json(
        prompt: str,
        system: str = "",
        model: str = "llama3.2",
        provider: str = "Ollama",
        media_path: str = ""
    ) -> dict:
        """Declarative Pixeltable UDF returning structured JSON payload cached per cell in PostgreSQL."""
        raw = LLMService.generate(
            provider=provider,
            model=model,
            prompt=prompt,
            system=system,
            media_path=media_path if media_path else None,
            json_mode=True
        )
        parsed = extract_json_payload(raw)
        return parsed if parsed is not None else {"llm_output": raw}


def build_prompt_expr(template: str, table: Any) -> Any:
    """
    Construct a Pixeltable string expression from a prompt template string.
    Finds {column} placeholders and concatenates table columns dynamically.
    """
    if not PIXELTABLE_AVAILABLE or pxt is None or table is None:
        return template

    available_cols = set(table.columns() if callable(table.columns) else table._schema.keys())
    parts = re.split(r"(\{[_a-zA-Z0-9]+\})", template)
    expr_parts = []
    has_column_ref = False

    for part in parts:
        if not part:
            continue
        if part.startswith("{") and part.endswith("}"):
            col_name = part[1:-1]
            if col_name in available_cols:
                col_expr = table[col_name]
                expr_parts.append(col_expr)
                has_column_ref = True
            else:
                expr_parts.append(part)
        else:
            expr_parts.append(part)

    if not has_column_ref or not expr_parts:
        return template

    # Concatenate expression parts
    res_expr = expr_parts[0]
    for p in expr_parts[1:]:
        res_expr = res_expr + p
    return res_expr



class PromptExecutor:
    _cancel_requested: bool = False

    @classmethod
    def cancel_execution(cls) -> None:
        """Set cancellation flag to halt ongoing batch loops on the next row."""
        cls._cancel_requested = True

    @classmethod
    def reset_cancellation(cls) -> None:
        """Reset cancellation flag before starting a new run."""
        cls._cancel_requested = False

    @classmethod
    def is_cancelled(cls) -> bool:
        """Check whether cancellation was requested."""
        return cls._cancel_requested

    @staticmethod
    def format_prompt(template: str, row: Dict[str, Any]) -> str:
        """Replace {column_name} variables in prompt template with row values."""
        formatted = template
        for k, v in row.items():
            placeholder = f"{{{k}}}"
            val_str = str(v) if v is not None else ""
            formatted = formatted.replace(placeholder, val_str)
        return formatted

    @classmethod
    def run_sample_test(cls, model: str, prompt_template: str, system_prompt: str,
                        table_dir: Optional[str] = None, table_name: Optional[str] = None,
                        provider: str = "Ollama", sample_count: int = 3, auto_split: bool = True,
                        enable_vision: bool = False, dir_name: Optional[str] = None,
                        progress_callback: Optional[Any] = None) -> List[Dict[str, Any]]:
        """Run prompt test against 1 to N sample rows from table with multimodal and JSON auto-split support."""
        cls.reset_cancellation()
        effective_dir = dir_name or table_dir or "default"
        full_table_path = DBManager.resolve_table_path(effective_dir, table_name or "raw_assets")
        table = pxt.get_table(full_table_path)
        
        # Collect sample rows as dicts (excluding heavy binary columns from RAM)
        available_cols = list(table.columns()) if callable(table.columns) else list(table._schema.keys())
        query_cols = [c for c in available_cols if c not in {"image", "doc", "video", "audio"}]
        query = table.select(*[table[c] for c in query_cols]) if query_cols else table
        df = query.limit(sample_count).collect().to_pandas()
        records = df.to_dict(orient="records")
        total = len(records)
        
        results = []

        for idx, row in enumerate(records):
            if cls.is_cancelled():
                break

            file_name = row.get("file_name", f"Row {idx + 1}")
            if progress_callback:
                progress_callback(idx + 1, total, f"[{provider}] Evaluating sample {idx + 1}/{total}: {file_name}")

            prompt = cls.format_prompt(prompt_template, row)
            # Only attach media path if enable_vision is explicitly checked
            media_path = get_row_media_path(row, enable_vision=enable_vision)

            # Call unified LLM service with multimodal & JSON mode
            try:
                output = LLMService.generate(
                    provider=provider,
                    model=model,
                    prompt=prompt,
                    system=system_prompt,
                    media_path=media_path,
                    json_mode=auto_split
                )
            except (LLMQuotaExceededError, LLMAuthError, LLMServiceUnavailableError) as fatal_err:
                # Fatal rate-limit, quota exhaustion, or auth error: break immediately!
                if not results:
                    raise fatal_err
                break
            except Exception as e:
                err_str = str(e)
                if "RESOURCE_EXHAUSTED" in err_str or "429" in err_str:
                    if not results:
                        raise LLMQuotaExceededError(err_str)
                    break
                output = f"[Generation error: {err_str}]"

            # Extract latency & throughput telemetry
            last_telem = LLMService.get_last_telemetry()
            telemetry_str = last_telem.get("summary", "") if last_telem else ""

            record_entry: Dict[str, Any] = {
                "row_id": str(row.get("id", idx)),
                "file_name": file_name,
                "telemetry": telemetry_str,
                "prompt_rendered": prompt,
                "model_output": output,
                "source_content": (str(row.get("content", ""))[:300] + "...") if row.get("content") else ""
            }

            if auto_split:
                parsed = extract_json_payload(output)
                if parsed:
                    record_entry["parsed_json"] = parsed
                    record_entry["extracted_columns"] = list(parsed.keys())
                    for k, v in parsed.items():
                        record_entry[f"col_{k}"] = str(v)

            results.append(record_entry)
            
        return results

    @classmethod
    def test_sample_prompt(cls, dir_name: str, table_name: str, prompt_template: str,
                           system_prompt: str, provider: str = "Ollama", model: str = "llama3.2",
                           limit: int = 1, auto_split: bool = True, enable_vision: bool = False,
                           progress_callback: Optional[Any] = None) -> Dict[str, Any]:
        """Alias for run_sample_test matching controller parameter signature."""
        try:
            samples = cls.run_sample_test(
                model=model,
                prompt_template=prompt_template,
                system_prompt=system_prompt,
                table_dir=dir_name,
                table_name=table_name,
                provider=provider,
                sample_count=limit,
                auto_split=auto_split,
                enable_vision=enable_vision,
                progress_callback=progress_callback
            )
            # Format results for controller
            formatted = []
            for s in samples:
                formatted.append({
                    "row_id": s.get("row_id", ""),
                    "file_name": s.get("file_name", ""),
                    "telemetry": s.get("telemetry", ""),
                    "source_snippet": s.get("source_content", ""),
                    "rendered_prompt": s.get("prompt_rendered", ""),
                    "llm_output": s.get("model_output", "")
                })
            return {"status": "success", "results": formatted}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @classmethod
    def apply_prompt_to_table(cls, model: str, prompt_template: str, system_prompt: str,
                              table_dir: Optional[str] = None, table_name: Optional[str] = None,
                              target_column: Optional[str] = None,
                              provider: str = "Ollama",
                              auto_split: bool = True,
                              mode: str = "replace", limit: Optional[int] = None,
                              enable_vision: bool = False,
                              dir_name: Optional[str] = None,
                              write_mode: Optional[str] = None,
                              auto_split_json: Optional[bool] = None,
                              progress_callback: Optional[Any] = None) -> Dict[str, Any]:
        """
        Apply prompt across table rows using native Pixeltable computed columns with automatic
        PostgreSQL database-level caching, lineage versioning, and cell-level error tracking.
        """
        effective_dir = dir_name or table_dir or "default"
        effective_tbl = table_name or "raw_assets"
        effective_mode = write_mode or mode or "replace"
        effective_auto_split = auto_split_json if auto_split_json is not None else auto_split

        cls.reset_cancellation()

        full_table_path = DBManager.resolve_table_path(effective_dir, effective_tbl)
        table = pxt.get_table(full_table_path)
        total_rows = table.count()

        if total_rows == 0:
            return {"status": "error", "message": "No rows found in table to process."}

        available_cols = list(table.columns()) if callable(table.columns) else list(table._schema.keys())
        media_expr = table.file_path if (enable_vision and "file_path" in available_cols) else None

        # Build declarative Pixeltable string expression for the prompt
        prompt_expr = build_prompt_expr(prompt_template, table)

        # ------------------------------------------------------------------
        # 1. Native Computed Column Strategy (Auto-Split Mode)
        # ------------------------------------------------------------------
        if effective_auto_split:
            temp_json_col = "_pxt_llm_json"
            native_success = False
            created_columns = set()

            try:
                if progress_callback:
                    progress_callback(0.2, 1.0, f"[{provider}] Adding native computed column on '{effective_tbl}'...")

                if temp_json_col in available_cols:
                    table.drop_column(temp_json_col)

                # Add declarative computed JSON column; Pixeltable evaluates & caches in PostgreSQL
                table.add_computed_column(**{
                    temp_json_col: pxt_generate_json(
                        prompt=prompt_expr,
                        system=system_prompt,
                        model=model,
                        provider=provider,
                        media_path=media_expr
                    )
                })

                # Sample computed JSON outputs to discover generated keys
                sample_df = table.select(table[temp_json_col]).limit(5).collect().to_pandas()
                extracted_keys = set()
                for val in sample_df[temp_json_col]:
                    if isinstance(val, dict):
                        extracted_keys.update(val.keys())

                current_cols = list(table.columns()) if callable(table.columns) else list(table._schema.keys())
                for k in sorted(extracted_keys):
                    valid_k, safe_k, _ = sanitize_identifier(k)
                    if valid_k and safe_k != temp_json_col:
                        if safe_k in current_cols and effective_mode == "replace":
                            table.drop_column(safe_k)
                        # Extract JSON key natively into typed computed column (0 extra LLM calls!)
                        table.add_computed_column(**{safe_k: table[temp_json_col][k]})
                        created_columns.add(safe_k)

                # Clean up intermediate raw JSON column
                if temp_json_col in (table.columns() if callable(table.columns) else table._schema.keys()):
                    table.drop_column(temp_json_col)

                native_success = True
            except Exception:
                # Fallback to safe row-level batch execution if UDF or table expression is unsupported
                native_success = False

            if not native_success:
                # Fallback implementation ensuring 100% compatibility with test mocks
                query_cols = [c for c in available_cols if c not in {"image", "doc", "video", "audio"}]
                query = table.select(*[table[c] for c in query_cols]) if query_cols else table
                if limit:
                    query = query.limit(limit)
                records = query.collect().to_pandas().to_dict(orient="records")
                total = len(records)
                all_parsed_rows = []
                cols_type_map: Dict[str, Any] = {}
                abort_reason = None

                for idx, row in enumerate(records):
                    if cls.is_cancelled():
                        abort_reason = "Execution cancelled by user."
                        break

                    file_name = row.get("file_name", f"Row {idx + 1}")
                    if progress_callback:
                        progress_callback(idx + 1, total, f"[{provider}] Generating JSON {idx + 1}/{total}: {file_name}")

                    prompt = cls.format_prompt(prompt_template, row)
                    media_p = get_row_media_path(row, enable_vision=enable_vision)
                    try:
                        res = LLMService.generate(
                            provider=provider, model=model, prompt=prompt,
                            system=system_prompt, media_path=media_p, json_mode=True
                        )
                    except (LLMQuotaExceededError, LLMAuthError, LLMServiceUnavailableError) as fatal_err:
                        abort_reason = str(fatal_err)
                        break
                    except Exception as row_err:
                        err_str = str(row_err)
                        if "RESOURCE_EXHAUSTED" in err_str or "429" in err_str:
                            abort_reason = f"Quota exceeded (429): {err_str}"
                            break
                        res = f'{{"error": "{err_str}"}}'

                    parsed = extract_json_payload(res) or {"llm_output": res}
                    all_parsed_rows.append((row["id"], parsed))
                    for k, v in parsed.items():
                        valid_col, safe_col, _ = sanitize_identifier(k)
                        if valid_col and safe_col not in cols_type_map:
                            cols_type_map[safe_col] = infer_pixeltable_type(v)

                existing_cols = list(table.columns()) if callable(table.columns) else list(table._schema.keys())
                for col_name, col_type in cols_type_map.items():
                    if col_name not in existing_cols:
                        table.add_column(**{col_name: col_type or pxt.String})
                        created_columns.add(col_name)

                updated_count = 0
                for row_id, parsed in all_parsed_rows:
                    update_dict = {safe_col: format_cell_value(v) for k, v in parsed.items() if (safe_col := sanitize_identifier(k)[1])}
                    if update_dict:
                        table.update(update_dict, where=(table.id == row_id))
                        updated_count += 1
                total_rows = updated_count

                if abort_reason and updated_count == 0:
                    return {
                        "status": "error",
                        "message": f"Execution halted: {abort_reason}",
                        "rows_processed": 0,
                        "columns": []
                    }
                elif abort_reason and updated_count > 0:
                    cols_summary = ", ".join(f"`{c}`" for c in sorted(created_columns))
                    DBManager.record_operation(
                        dir_name=effective_dir,
                        table_name=effective_tbl,
                        op_data={"action": "add_columns", "columns": list(created_columns), "rows_updated": total_rows}
                    )
                    return {
                        "status": "warning",
                        "message": f"Batch halted after {updated_count}/{total} rows: {abort_reason}. Saved {len(created_columns)} columns: {cols_summary}",
                        "count": total_rows,
                        "rows_processed": total_rows,
                        "columns": list(created_columns)
                    }

            cols_summary = ", ".join(f"`{c}`" for c in sorted(created_columns))
            DBManager.record_operation(
                dir_name=effective_dir,
                table_name=effective_tbl,
                op_data={"action": "add_columns", "columns": list(created_columns), "rows_updated": total_rows}
            )
            return {
                "status": "success",
                "message": f"Successfully enriched {total_rows} rows via [{provider}] '{model}'. Added {len(created_columns)} native Pixeltable columns: {cols_summary}",
                "count": total_rows,
                "rows_processed": total_rows,
                "columns": list(created_columns)
            }

        # ------------------------------------------------------------------
        # 2. Native Computed Column Strategy (Single Column Mode)
        # ------------------------------------------------------------------
        else:
            valid_col, safe_col, col_msg = sanitize_identifier(target_column or "llm_summary")
            if not valid_col:
                return {"status": "error", "message": f"Invalid Target Column name '{target_column}': {col_msg}"}

            native_success = False
            try:
                if safe_col in available_cols and effective_mode == "replace":
                    table.drop_column(safe_col)

                if safe_col not in (table.columns() if callable(table.columns) else table._schema.keys()):
                    if progress_callback:
                        progress_callback(0.3, 1.0, f"[{provider}] Computing native column '{safe_col}'...")
                    table.add_computed_column(**{
                        safe_col: pxt_generate_text(
                            prompt=prompt_expr,
                            system=system_prompt,
                            model=model,
                            provider=provider,
                            json_mode=False,
                            media_path=media_expr
                        )
                    })
                    native_success = True
            except Exception:
                native_success = False

            if not native_success:
                # Safe row update fallback for append mode or test mocks
                query_cols = [c for c in available_cols if c not in {"image", "doc", "video", "audio"}]
                query = table.select(*[table[c] for c in query_cols]) if query_cols else table
                if limit:
                    query = query.limit(limit)
                records = query.collect().to_pandas().to_dict(orient="records")
                total = len(records)
                existing_cols = list(table.columns()) if callable(table.columns) else list(table._schema.keys())
                if safe_col not in existing_cols:
                    table.add_column(**{safe_col: pxt.String})

                updated_count = 0
                abort_reason = None
                for idx, row in enumerate(records):
                    if cls.is_cancelled():
                        abort_reason = "Execution cancelled by user."
                        break

                    file_name = row.get("file_name", f"Row {idx + 1}")
                    if progress_callback:
                        progress_callback(idx + 1, total, f"[{provider}] Processing row {idx + 1}/{total}: {file_name}")
                    prompt = cls.format_prompt(prompt_template, row)
                    media_p = get_row_media_path(row, enable_vision=enable_vision)
                    try:
                        res = LLMService.generate(
                            provider=provider, model=model, prompt=prompt,
                            system=system_prompt, media_path=media_p, json_mode=False
                        )
                    except (LLMQuotaExceededError, LLMAuthError, LLMServiceUnavailableError) as fatal_err:
                        abort_reason = str(fatal_err)
                        break
                    except Exception as row_err:
                        err_str = str(row_err)
                        if "RESOURCE_EXHAUSTED" in err_str or "429" in err_str:
                            abort_reason = f"Quota exceeded (429): {err_str}"
                            break
                        res = f"[Error: {err_str}]"

                    existing_val = str(row.get(safe_col, "")) if row.get(safe_col) is not None else ""
                    new_val = f"{existing_val}\n\n{res}" if (effective_mode == "append" and existing_val) else res
                    table.update({safe_col: new_val}, where=(table.id == row["id"]))
                    updated_count += 1
                total_rows = updated_count

                if abort_reason and updated_count == 0:
                    return {
                        "status": "error",
                        "message": f"Execution halted: {abort_reason}",
                        "rows_processed": 0,
                        "column": safe_col
                    }
                elif abort_reason and updated_count > 0:
                    DBManager.record_operation(
                        dir_name=effective_dir,
                        table_name=effective_tbl,
                        op_data={"action": "single_column", "column": safe_col, "rows_updated": total_rows}
                    )
                    note = f" (Column name formatted as '{safe_col}')" if safe_col != target_column else ""
                    return {
                        "status": "warning",
                        "message": f"Batch halted after {updated_count}/{total} rows: {abort_reason}. Saved {updated_count} rows to column '{safe_col}'{note}.",
                        "count": total_rows,
                        "rows_processed": total_rows,
                        "column": safe_col
                    }

            note = f" (Column name formatted as '{safe_col}')" if safe_col != target_column else ""
            DBManager.record_operation(
                dir_name=effective_dir,
                table_name=effective_tbl,
                op_data={"action": "single_column", "column": safe_col, "rows_updated": total_rows}
            )
            return {
                "status": "success",
                "message": f"Successfully processed {total_rows} rows using [{provider}] '{model}' and saved to native column '{safe_col}'{note} ({effective_mode} mode).",
                "count": total_rows,
                "rows_processed": total_rows,
                "column": safe_col
            }




