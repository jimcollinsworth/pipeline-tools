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


def get_row_media_path(row: Dict[str, Any]) -> Optional[str]:
    """Inspect row fields and return absolute media path if image/PDF exists."""
    for field in ["image", "file_path", "doc", "video", "audio"]:
        p = row.get(field)
        if p and isinstance(p, str) and os.path.exists(p):
            ext = os.path.splitext(p)[1].lower()
            if ext in [".jpg", ".jpeg", ".png", ".webp", ".pdf"]:
                return p
    return None


class PromptExecutor:
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
                        table_dir: str, table_name: str, provider: str = "Ollama",
                        sample_count: int = 3, auto_split: bool = True,
                        progress_callback: Optional[Any] = None) -> List[Dict[str, Any]]:
        """Run prompt test against 1 to N sample rows from table with multimodal and JSON auto-split support."""
        full_table_path = DBManager.resolve_table_path(table_dir, table_name)
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
            file_name = row.get("file_name", f"Row {idx + 1}")
            if progress_callback:
                progress_callback(idx + 1, total, f"[{provider}] Evaluating sample {idx + 1}/{total}: {file_name}")

            prompt = cls.format_prompt(prompt_template, row)
            media_path = get_row_media_path(row)

            # Call unified LLM service with multimodal & JSON mode
            output = LLMService.generate(
                provider=provider,
                model=model,
                prompt=prompt,
                system=system_prompt,
                media_path=media_path,
                json_mode=auto_split
            )

            record_entry: Dict[str, Any] = {
                "row_id": str(row.get("id", idx)),
                "file_name": file_name,
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
    def apply_prompt_to_table(cls, model: str, prompt_template: str, system_prompt: str,
                              table_dir: str, table_name: str,
                              target_column: Optional[str] = None,
                              provider: str = "Ollama",
                              auto_split: bool = True,
                              mode: str = "replace", limit: Optional[int] = None,
                              progress_callback: Optional[Any] = None) -> Dict[str, Any]:
        """
        Run prompt against table rows and write results back.
        If auto_split=True: Unpacks JSON keys directly into individual typed Pixeltable columns.
        If auto_split=False: Writes full response into single target_column.
        """
        full_table_path = DBManager.resolve_table_path(table_dir, table_name)
        table = pxt.get_table(full_table_path)

        # Fetch rows (excluding heavy binary columns from RAM)
        available_cols = list(table.columns()) if callable(table.columns) else list(table._schema.keys())
        query_cols = [c for c in available_cols if c not in {"image", "doc", "video", "audio"}]
        query = table.select(*[table[c] for c in query_cols]) if query_cols else table
        if limit:
            query = query.limit(limit)
        df = query.collect().to_pandas()
        records = df.to_dict(orient="records")
        total = len(records)

        if total == 0:
            return {"status": "error", "message": "No rows found in table to process."}

        updated_count = 0
        created_columns = set()

        if auto_split:
            # 1. First pass: execute LLM calls and collect parsed outputs
            all_parsed_rows = []
            cols_type_map: Dict[str, Any] = {}

            for idx, row in enumerate(records):
                file_name = row.get("file_name", f"Row {idx + 1}")
                if progress_callback:
                    progress_callback(idx + 1, total, f"[{provider}] Generating JSON {idx + 1}/{total}: {file_name}")

                prompt = cls.format_prompt(prompt_template, row)
                media_path = get_row_media_path(row)

                res = LLMService.generate(
                    provider=provider,
                    model=model,
                    prompt=prompt,
                    system=system_prompt,
                    media_path=media_path,
                    json_mode=True
                )

                parsed = extract_json_payload(res)
                if not parsed:
                    parsed = {"llm_output": res}

                all_parsed_rows.append((row["id"], parsed))

                for k, v in parsed.items():
                    valid_col, safe_col, _ = sanitize_identifier(k)
                    if valid_col:
                        if safe_col not in cols_type_map:
                            cols_type_map[safe_col] = infer_pixeltable_type(v)

            # 2. Ensure all extracted columns exist on the table
            existing_cols = list(table.columns()) if callable(table.columns) else list(table._schema.keys())
            for col_name, col_type in cols_type_map.items():
                if col_name not in existing_cols:
                    if progress_callback:
                        progress_callback(total, total, f"Creating Pixeltable column '{col_name}'...")
                    table.add_column(**{col_name: col_type or pxt.String})
                    created_columns.add(col_name)

            # 3. Update rows with parsed values
            for row_id, parsed in all_parsed_rows:
                update_dict = {}
                for k, v in parsed.items():
                    valid_col, safe_col, _ = sanitize_identifier(k)
                    if valid_col:
                        update_dict[safe_col] = format_cell_value(v)

                if update_dict:
                    table.update(update_dict, where=(table.id == row_id))
                    updated_count += 1

            cols_summary = ", ".join(f"`{c}`" for c in cols_type_map.keys())
            DBManager.record_operation(
                dir_name=table_dir,
                table_name=table_name,
                op_data={"action": "add_columns", "columns": list(cols_type_map.keys()), "rows_updated": updated_count}
            )
            return {
                "status": "success",
                "message": f"Successfully processed {updated_count} rows via [{provider}] '{model}'. Unpacked into {len(cols_type_map)} dynamic columns: {cols_summary}",
                "count": updated_count,
                "columns": list(cols_type_map.keys())
            }

        else:
            # Single Target Column Mode
            valid_col, safe_col, col_msg = sanitize_identifier(target_column or "llm_summary")
            if not valid_col:
                return {"status": "error", "message": f"Invalid Target Column name '{target_column}': {col_msg}"}

            existing_cols = list(table.columns()) if callable(table.columns) else list(table._schema.keys())
            if safe_col not in existing_cols:
                if progress_callback:
                    progress_callback(0, 1, f"Adding column '{safe_col}' to Pixeltable schema...")
                table.add_column(**{safe_col: pxt.String})
                created_columns.add(safe_col)

            for idx, row in enumerate(records):
                file_name = row.get("file_name", f"Row {idx + 1}")
                if progress_callback:
                    progress_callback(idx + 1, total, f"[{provider}] Processing row {idx + 1}/{total}: {file_name}")

                prompt = cls.format_prompt(prompt_template, row)
                media_path = get_row_media_path(row)

                res = LLMService.generate(
                    provider=provider,
                    model=model,
                    prompt=prompt,
                    system=system_prompt,
                    media_path=media_path,
                    json_mode=False
                )

                existing_val = str(row.get(safe_col, "")) if row.get(safe_col) is not None else ""
                if mode == "append" and existing_val:
                    new_val = f"{existing_val}\n\n{res}"
                else:
                    new_val = res

                table.update({safe_col: new_val}, where=(table.id == row["id"]))
                updated_count += 1

            note = f" (Column name formatted as '{safe_col}')" if safe_col != target_column else ""
            DBManager.record_operation(
                dir_name=table_dir,
                table_name=table_name,
                op_data={"action": "single_column", "column": safe_col, "rows_updated": updated_count}
            )
            return {
                "status": "success",
                "message": f"Successfully processed {updated_count} rows using [{provider}] '{model}' and saved to column '{safe_col}'{note} ({mode} mode).",
                "count": updated_count,
                "column": safe_col
            }



