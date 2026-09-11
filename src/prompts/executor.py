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


import logging
logger = logging.getLogger("pipeline_tools.prompts")

def format_prompt(template: str, row: Dict[str, Any], context_fragment: str = "") -> str:
    """Replace {column_name} variables in prompt template with row values."""
    formatted = template
    for k, v in row.items():
        placeholder = f"{{{k}}}"
        val_str = str(v) if v is not None else ""
        formatted = formatted.replace(placeholder, val_str)
    if "{ingestion_context}" in formatted:
        formatted = formatted.replace("{ingestion_context}", context_fragment)
    return formatted


if PIXELTABLE_AVAILABLE and pxt is not None:
    @pxt.udf
    def pxt_generate_text(file_name: Optional[str], content: Optional[str], template: str, system_prompt: str, provider: str, model: str) -> str:
        row_dict = {"file_name": file_name or "", "content": content or ""}
        prompt = format_prompt(template, row_dict)
        res = LLMService.generate(provider=provider, model=model, prompt=prompt, system=system_prompt, json_mode=False)
        return str(res or "")

    @pxt.udf
    def pxt_generate_append(existing_text: Optional[str], file_name: Optional[str], content: Optional[str], template: str, system_prompt: str, provider: str, model: str) -> str:
        row_dict = {"file_name": file_name or "", "content": content or ""}
        prompt = format_prompt(template, row_dict)
        new_res = str(LLMService.generate(provider=provider, model=model, prompt=prompt, system=system_prompt, json_mode=False) or "")
        if existing_text and existing_text.strip():
            return f"{existing_text.strip()}\n\n{new_res}"
        return new_res

    @pxt.udf
    def pxt_generate_json(file_name: Optional[str], content: Optional[str], template: str, system_prompt: str, provider: str, model: str) -> dict:
        row_dict = {"file_name": file_name or "", "content": content or ""}
        prompt = format_prompt(template, row_dict)
        res = LLMService.generate(provider=provider, model=model, prompt=prompt, system=system_prompt, json_mode=True)
        parsed = extract_json_payload(res)
        return parsed or {"llm_output": str(res or "")}
else:
    pxt_generate_text = None
    pxt_generate_append = None
    pxt_generate_json = None


class PromptExecutor:
    format_prompt = staticmethod(format_prompt)

    @classmethod
    def run_sample_test(cls, model: str, prompt_template: str, system_prompt: str,
                        table_dir: str, table_name: str, provider: str = "Ollama",
                        sample_count: int = 3, auto_split: bool = True,
                        progress_callback: Optional[Any] = None) -> List[Dict[str, Any]]:
        """Run prompt test against 1 to N sample rows from table with multimodal and JSON auto-split support."""
        from src.core.skills import SkillsRegistry
        prompt_template, system_prompt, _ = SkillsRegistry.expand_prompt_with_skills(
            prompt_template, system_prompt
        )

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
        Run prompt against table using Pixeltable native declarative computed columns.
        Eliminates imperative row-by-row updates and leverages Pixeltable's internal
        execution engine, dependency DAG, and automatic incremental update mechanics.
        """
        from src.core.skills import SkillsRegistry
        from src.core.ingestion_context import IngestionContext

        if not PIXELTABLE_AVAILABLE:
            return {"status": "error", "message": "Pixeltable is not available."}

        # Expand prompt slash commands with discovered skills (RES-13)
        prompt_template, system_prompt, applied_skills = SkillsRegistry.expand_prompt_with_skills(
            prompt_template, system_prompt
        )

        full_table_path = DBManager.resolve_table_path(table_dir, table_name)
        table = pxt.get_table(full_table_path)

        total_rows = table.count()
        if total_rows == 0:
            return {"status": "error", "message": "No rows found in table to process."}

        existing_cols = list(table.columns()) if callable(table.columns) else list(table._schema.keys())

        if auto_split:
            # 1. Declarative JSON Column via @pxt.udf
            primary_col = "llm_payload"
            if primary_col in existing_cols:
                try:
                    table.drop_column(primary_col)
                except Exception:
                    pass

            if progress_callback:
                progress_callback(1, 3, f"Computing declarative JSON column '{primary_col}' via [{provider}] '{model}'...")

            # Add declarative computed column via @pxt.udf
            table.add_computed_column(**{
                primary_col: pxt_generate_json(
                    file_name=table.file_name,
                    content=table.content,
                    template=prompt_template,
                    system_prompt=system_prompt,
                    provider=provider,
                    model=model
                )
            })

            if progress_callback:
                progress_callback(2, 3, f"Projecting structured JSON fields into typed Pixeltable columns...")

            # 2. Discover JSON keys from sample output and add declarative projection columns
            sample_df = table.select(table[primary_col]).limit(1).collect().to_pandas()
            sample_payload = sample_df[primary_col].iloc[0] if len(sample_df) > 0 else {}
            if isinstance(sample_payload, str):
                sample_payload = extract_json_payload(sample_payload) or {}

            extracted_cols = []
            if isinstance(sample_payload, dict):
                for k in sample_payload.keys():
                    valid_k, safe_k, _ = sanitize_identifier(k)
                    if valid_k and safe_k != primary_col:
                        if safe_k in existing_cols:
                            try:
                                table.drop_column(safe_k)
                            except Exception:
                                pass
                        # Declarative field extraction from the computed JSON column
                        try:
                            table.add_computed_column(**{safe_k: table[primary_col][k]})
                            extracted_cols.append(safe_k)
                        except Exception as proj_err:
                            logger.warning(f"Could not project declarative field '{k}': {proj_err}")

            created_columns = [primary_col] + extracted_cols
            updated_count = total_rows

            # Dynamic context export (RES-12)
            ctx = IngestionContext(domain=table_dir, table=table_name)
            ctx.record_row(
                file_name="DeclarativeBatch",
                modality="batch_computed",
                content_snippet=prompt_template[:150],
                summary=f"Computed {len(created_columns)} columns via [{provider}] '{model}'",
                extracted_entities=extracted_cols,
                extracted_tags=[provider, model]
            )
            context_file = ctx.export_to_markdown()

            cols_summary = ", ".join(f"`{c}`" for c in created_columns)
            DBManager.record_operation(
                dir_name=table_dir,
                table_name=table_name,
                op_data={
                    "action": "add_columns",
                    "columns": created_columns,
                    "rows_updated": updated_count,
                    "context_file": str(context_file),
                    "applied_skills": applied_skills
                }
            )

            if progress_callback:
                progress_callback(3, 3, f"✅ Computed {len(created_columns)} columns across {updated_count} rows.")

            return {
                "status": "success",
                "message": f"Successfully computed {updated_count} rows via declarative [{provider}] '{model}'. Unpacked into {len(created_columns)} dynamic columns: {cols_summary}",
                "count": updated_count,
                "columns": created_columns,
                "context_file": str(context_file),
                "applied_skills": applied_skills
            }

        else:
            # Single Target Column Mode
            valid_col, safe_col, col_msg = sanitize_identifier(target_column or "llm_summary")
            if not valid_col:
                return {"status": "error", "message": f"Invalid Target Column name '{target_column}': {col_msg}"}

            if progress_callback:
                progress_callback(1, 2, f"Computing declarative column '{safe_col}' via [{provider}] '{model}'...")

            if mode == "append" and safe_col in existing_cols:
                # Use append UDF
                temp_col = f"{safe_col}_appended"
                if temp_col in existing_cols:
                    table.drop_column(temp_col)
                table.add_computed_column(**{
                    temp_col: pxt_generate_append(
                        existing_text=table[safe_col],
                        file_name=table.file_name,
                        content=table.content,
                        template=prompt_template,
                        system_prompt=system_prompt,
                        provider=provider,
                        model=model
                    )
                })
                table.drop_column(safe_col)
                table.add_computed_column(**{safe_col: table[temp_col]})
                table.drop_column(temp_col)
            else:
                if safe_col in existing_cols:
                    table.drop_column(safe_col)
                table.add_computed_column(**{
                    safe_col: pxt_generate_text(
                        file_name=table.file_name,
                        content=table.content,
                        template=prompt_template,
                        system_prompt=system_prompt,
                        provider=provider,
                        model=model
                    )
                })

            updated_count = total_rows

            ctx = IngestionContext(domain=table_dir, table=table_name)
            ctx.record_row(
                file_name="DeclarativeBatch",
                modality="batch_computed",
                content_snippet=prompt_template[:150],
                summary=f"Computed column '{safe_col}' via [{provider}] '{model}'",
                extracted_tags=[provider, model]
            )
            context_file = ctx.export_to_markdown()

            DBManager.record_operation(
                dir_name=table_dir,
                table_name=table_name,
                op_data={
                    "action": "single_column",
                    "column": safe_col,
                    "rows_updated": updated_count,
                    "context_file": str(context_file),
                    "applied_skills": applied_skills
                }
            )

            if progress_callback:
                progress_callback(2, 2, f"✅ Successfully computed column '{safe_col}' across {updated_count} rows.")

            return {
                "status": "success",
                "message": f"Successfully computed column '{safe_col}' across {updated_count} rows using declarative [{provider}] '{model}' ({mode} mode).",
                "count": updated_count,
                "column": safe_col,
                "context_file": str(context_file),
                "applied_skills": applied_skills
            }



