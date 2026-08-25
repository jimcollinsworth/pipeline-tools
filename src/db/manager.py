import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

try:
    import pixeltable as pxt
    from pixeltable.functions.uuid import uuid7
    PIXELTABLE_AVAILABLE = True
except ImportError:
    pxt = None
    uuid7 = None
    PIXELTABLE_AVAILABLE = False

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


class DBManager:
    @staticmethod
    def list_dirs() -> List[str]:
        """List all pixeltable directories/domains."""
        if not PIXELTABLE_AVAILABLE:
            return ["default (local memory)"]
        try:
            return pxt.list_dirs()
        except Exception:
            return []

    @staticmethod
    def list_tables(dir_name: str = "") -> List[str]:
        """List all tables under a directory/domain or root."""
        if not PIXELTABLE_AVAILABLE:
            return ["raw_assets"]
        try:
            if dir_name:
                return pxt.list_tables(dir_name)
            return pxt.list_tables()
        except Exception:
            return []

    @staticmethod
    def get_or_create_table(dir_name: str, table_name: str):
        """Create or get a unified multimodal table in Pixeltable."""
        if not PIXELTABLE_AVAILABLE:
            return None

        dir_name = dir_name.strip() if dir_name else "default"
        table_name = table_name.strip() if table_name else "raw_assets"
        full_table_path = f"{dir_name}.{table_name}"
        
        pxt.create_dir(dir_name, if_exists="ignore")
        
        table = pxt.create_table(
            full_table_path,
            {
                "id": uuid7(),
                "file_name": pxt.String,
                "file_path": pxt.String,
                "rel_path": pxt.String,
                "modality": pxt.String,
                "file_type": pxt.String,
                "file_size": pxt.Int,
                "content": pxt.String,
                "doc": pxt.Document,
                "image": pxt.Image,
                "audio": pxt.Audio,
                "video": pxt.Video,
                "metadata": pxt.Json,
                "created_at": pxt.Timestamp
            },
            primary_key=["id"],
            if_exists="ignore"
        )
        return table

    @staticmethod
    def extract_file_content(file_path: str, modality: str, file_type: str) -> str:
        """Extract textual content for text/doc files."""
        try:
            p = Path(file_path)
            if not p.exists():
                return ""
            
            ext = p.suffix.lower()
            if ext in [".md", ".markdown", ".txt", ".json", ".yaml", ".yml", ".csv", ".py"]:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            elif ext == ".pdf":
                if fitz is not None:
                    doc = fitz.open(p)
                    text_pages = [page.get_text() for page in doc]
                    return "\n\n--- PAGE BREAK ---\n\n".join(text_pages)
                return "[PDF text extraction requires pymupdf]"
        except Exception as e:
            return f"Error extracting text: {str(e)}"
        return ""

    @classmethod
    def ingest_files(cls, dir_name: str, table_name: str, files_info: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Ingest a list of scanned file metadata into the selected Pixeltable table."""
        if not files_info:
            return {"status": "error", "message": "No files provided for ingestion."}

        if not PIXELTABLE_AVAILABLE:
            return {
                "status": "error",
                "message": "Pixeltable is not installed in the current environment (`uv pip install pixeltable`)."
            }

        table = cls.get_or_create_table(dir_name, table_name)
        rows_to_insert = []

        for f in files_info:
            abs_path = f.get("abs_path", "")
            modality = f.get("modality", "other")
            ext = f.get("extension", "")
            content = cls.extract_file_content(abs_path, modality, ext)

            row = {
                "file_name": f.get("name", Path(abs_path).name),
                "file_path": abs_path,
                "rel_path": f.get("rel_path", ""),
                "modality": modality,
                "file_type": ext,
                "file_size": int(f.get("size_bytes", 0)),
                "content": content if content else None,
                "doc": abs_path if ext == ".pdf" else None,
                "image": abs_path if modality == "images" else None,
                "audio": abs_path if modality == "audio" else None,
                "video": abs_path if modality == "video" else None,
                "metadata": {
                    "source": "directory_scanner",
                    "extension": ext,
                    "scanned_size": f.get("size", "")
                },
                "created_at": datetime.now()
            }
            rows_to_insert.append(row)

        try:
            status = table.insert(rows_to_insert, on_error="ignore")
            total_count = table.count()
            return {
                "status": "success",
                "message": f"Successfully ingested {len(rows_to_insert)} rows into '{dir_name}.{table_name}'. Total rows in table: {total_count}",
                "inserted_count": len(rows_to_insert),
                "total_count": total_count
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to insert rows: {str(e)}"}

    @classmethod
    def get_table_data(cls, dir_name: str, table_name: str, limit: int = 50) -> Dict[str, Any]:
        """Fetch rows from Pixeltable table for UI display."""
        if not PIXELTABLE_AVAILABLE:
            return {
                "columns": ["Notice"],
                "data": [["Pixeltable is not installed yet. Run `uv pip install pixeltable` to enable DB storage."]],
                "total_rows": 0
            }
        try:
            full_table_path = f"{dir_name}.{table_name}"
            table = pxt.get_table(full_table_path)
            columns = list(table.columns.keys())
            df = table.limit(limit).collect().to_pandas()
            return {
                "columns": list(df.columns),
                "data": df.fillna("").values.tolist(),
                "total_rows": table.count()
            }
        except Exception as e:
            return {"columns": [], "data": [], "total_rows": 0, "error": str(e)}

