import re
from typing import List, Dict, Any, Optional
from src.core.config import get_settings
from src.core.ollama_client import OllamaClient

try:
    import pixeltable as pxt
    PIXELTABLE_AVAILABLE = True
except ImportError:
    pxt = None
    PIXELTABLE_AVAILABLE = False


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
    def run_sample_test(cls, host: str, model: str, prompt_template: str, system_prompt: str,
                        table_dir: str, table_name: str, sample_count: int = 3) -> List[Dict[str, Any]]:
        """Run prompt test against 1 to N sample rows from table."""
        full_table_path = f"{table_dir}.{table_name}"
        table = pxt.get_table(full_table_path)
        
        # Collect sample rows as dicts
        df = table.limit(sample_count).collect().to_pandas()
        records = df.to_dict(orient="records")
        
        client = OllamaClient(host=host)
        results = []

        for idx, row in enumerate(records):
            prompt = cls.format_prompt(prompt_template, row)
            # Call Ollama
            output = client.generate(model=model, prompt=prompt, system=system_prompt)
            results.append({
                "row_id": str(row.get("id", idx)),
                "file_name": row.get("file_name", ""),
                "prompt_rendered": prompt,
                "model_output": output,
                "source_content": (str(row.get("content", ""))[:300] + "...") if row.get("content") else ""
            })
            
        return results

    @classmethod
    def apply_prompt_to_table(cls, host: str, model: str, prompt_template: str, system_prompt: str,
                              table_dir: str, table_name: str, target_column: str,
                              mode: str = "replace", limit: Optional[int] = None) -> Dict[str, Any]:
        """
        Run prompt against table rows and write results back to target column.
        mode: 'replace' (overwrites column value) or 'append' (appends to existing value).
        """
        full_table_path = f"{table_dir}.{table_name}"
        table = pxt.get_table(full_table_path)
        
        # Check if target_column exists; if not, add it as String
        existing_cols = list(table.columns.keys())
        target_col_clean = target_column.strip()
        if not target_col_clean:
            return {"status": "error", "message": "Target column name cannot be empty."}

        if target_col_clean not in existing_cols:
            table.add_column(**{target_col_clean: pxt.String})

        # Fetch rows
        query = table
        if limit:
            query = query.limit(limit)
        df = query.collect().to_pandas()
        records = df.to_dict(orient="records")
        
        client = OllamaClient(host=host)
        updated_rows = []
        
        for row in records:
            prompt = cls.format_prompt(prompt_template, row)
            res = client.generate(model=model, prompt=prompt, system=system_prompt)
            
            existing_val = str(row.get(target_col_clean, "")) if row.get(target_col_clean) is not None else ""
            if mode == "append" and existing_val:
                new_val = f"{existing_val}\n\n{res}"
            else:
                new_val = res
                
            table.update({target_col_clean: new_val}, where=(table.id == row["id"]))
            updated_rows.append(row["id"])

        return {
            "status": "success",
            "message": f"Successfully processed {len(updated_rows)} rows and saved to column '{target_col_clean}' ({mode} mode).",
            "count": len(updated_rows)
        }
