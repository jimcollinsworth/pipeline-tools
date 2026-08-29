import re
from typing import List, Dict, Any, Optional
from src.core.config import get_settings, sanitize_identifier
from src.core.llm_service import LLMService

try:
    import pixeltable as pxt
    PIXELTABLE_AVAILABLE = True
except ImportError:
    pxt = None
    PIXELTABLE_AVAILABLE = False

from src.db.manager import DBManager

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
                        sample_count: int = 3,
                        progress_callback: Optional[Any] = None) -> List[Dict[str, Any]]:
        """Run prompt test against 1 to N sample rows from table."""
        full_table_path = DBManager.resolve_table_path(table_dir, table_name)
        table = pxt.get_table(full_table_path)
        
        # Collect sample rows as dicts
        df = table.limit(sample_count).collect().to_pandas()
        records = df.to_dict(orient="records")
        total = len(records)
        
        results = []

        for idx, row in enumerate(records):
            file_name = row.get("file_name", f"Row {idx + 1}")
            if progress_callback:
                progress_callback(idx + 1, total, f"[{provider}] Evaluating sample {idx + 1}/{total}: {file_name}")

            prompt = cls.format_prompt(prompt_template, row)
            # Call unified LLM service
            output = LLMService.generate(provider=provider, model=model, prompt=prompt, system=system_prompt)
            results.append({
                "row_id": str(row.get("id", idx)),
                "file_name": file_name,
                "prompt_rendered": prompt,
                "model_output": output,
                "source_content": (str(row.get("content", ""))[:300] + "...") if row.get("content") else ""
            })
            
        return results

    @classmethod
    def apply_prompt_to_table(cls, model: str, prompt_template: str, system_prompt: str,
                              table_dir: str, table_name: str, target_column: str,
                              provider: str = "Ollama",
                              mode: str = "replace", limit: Optional[int] = None,
                              progress_callback: Optional[Any] = None) -> Dict[str, Any]:
        """
        Run prompt against table rows and write results back to target column.
        mode: 'replace' (overwrites column value) or 'append' (appends to existing value).
        """
        full_table_path = DBManager.resolve_table_path(table_dir, table_name)
        valid_col, safe_col, col_msg = sanitize_identifier(target_column or "llm_summary")

        if not valid_col:
            return {"status": "error", "message": f"Invalid Target Column name '{target_column}': {col_msg}"}

        table = pxt.get_table(full_table_path)

        # Check existing columns safely
        cols_list = list(table.columns()) if callable(table.columns) else list(table._schema.keys())
        if safe_col not in cols_list:
            if progress_callback:
                progress_callback(0, 1, f"Adding column '{safe_col}' to Pixeltable schema...")
            table.add_column(**{safe_col: pxt.String})

        # Fetch rows
        query = table
        if limit:
            query = query.limit(limit)
        df = query.collect().to_pandas()
        records = df.to_dict(orient="records")
        total = len(records)
        
        updated_count = 0
        
        for idx, row in enumerate(records):
            file_name = row.get("file_name", f"Row {idx + 1}")
            if progress_callback:
                progress_callback(idx + 1, total, f"[{provider}] Processing row {idx + 1}/{total}: {file_name}")

            prompt = cls.format_prompt(prompt_template, row)
            res = LLMService.generate(provider=provider, model=model, prompt=prompt, system=system_prompt)
            
            existing_val = str(row.get(safe_col, "")) if row.get(safe_col) is not None else ""
            if mode == "append" and existing_val:
                new_val = f"{existing_val}\n\n{res}"
            else:
                new_val = res
                
            table.update({safe_col: new_val}, where=(table.id == row["id"]))
            updated_count += 1

        note = f" (Column name formatted as '{safe_col}')" if safe_col != target_column else ""
        return {
            "status": "success",
            "message": f"Successfully processed {updated_count} rows using [{provider}] '{model}' and saved to column '{safe_col}'{note} ({mode} mode).",
            "count": updated_count,
            "column": safe_col
        }


