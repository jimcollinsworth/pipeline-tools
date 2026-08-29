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



from src.core.config import sanitize_identifier

class DBManager:
    @staticmethod
    def list_dirs() -> List[str]:
        """List all pixeltable directories/domains."""
        if not PIXELTABLE_AVAILABLE:
            return ["default"]
        try:
            dirs = pxt.list_dirs()
            return dirs if dirs else ["default"]
        except Exception:
            return ["default"]

    @staticmethod
    def list_tables(dir_name: str = "") -> List[str]:
        """List bare table names under a directory/domain or root."""
        if not PIXELTABLE_AVAILABLE:
            return ["raw_assets"]
        try:
            if dir_name:
                raw_tables = pxt.list_tables(dir_name)
            else:
                raw_tables = pxt.list_tables()
            
            # Pixeltable returns 'domain/table' or 'domain.table' - extract bare table name
            clean_names = []
            for t in raw_tables:
                name = str(t)
                if "/" in name:
                    name = name.split("/")[-1]
                elif "." in name:
                    name = name.split(".")[-1]
                clean_names.append(name)
            return clean_names if clean_names else []
        except Exception:
            return []

    @staticmethod
    def resolve_table_path(dir_name: str, table_name: str) -> str:
        """Resolve clean domain and table into a valid Pixeltable path."""
        raw_tbl = str(table_name).strip()
        raw_dir = str(dir_name).strip()

        # If user passed 'dir/tbl' or 'dir.tbl' in table_name, split them
        if "/" in raw_tbl:
            parts = raw_tbl.split("/", 1)
            raw_dir, raw_tbl = parts[0], parts[1]
        elif "." in raw_tbl:
            parts = raw_tbl.split(".", 1)
            raw_dir, raw_tbl = parts[0], parts[1]

        _, safe_dir, _ = sanitize_identifier(raw_dir or "default")
        _, safe_tbl, _ = sanitize_identifier(raw_tbl or "raw_assets")
        return f"{safe_dir}.{safe_tbl}"

    @staticmethod
    def get_or_create_table(dir_name: str, table_name: str):
        """Create or get a unified multimodal table in Pixeltable with sanitization."""
        if not PIXELTABLE_AVAILABLE:
            return None

        full_table_path = DBManager.resolve_table_path(dir_name, table_name)
        safe_dir = full_table_path.split(".")[0]
        
        pxt.create_dir(safe_dir, if_exists="ignore")


        
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
        """Extract text content for text, markdown, and PDF files."""
        try:
            p = Path(file_path)
            if not p.exists():
                return ""
            
            ext = p.suffix.lower()
            if ext in [".md", ".markdown", ".txt", ".json", ".yaml", ".yml", ".csv", ".py", ".html", ".xml", ".log"]:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            elif ext == ".pdf":
                try:
                    import pypdfium2 as pdfium
                    pdf = pdfium.PdfDocument(p)
                    pages_text = []
                    for page_idx in range(len(pdf)):
                        page = pdf.get_page(page_idx)
                        textpage = page.get_textpage()
                        text = textpage.get_text_range()
                        if text and text.strip():
                            # Filter non-printable / raw binary bytes
                            clean_text = "".join(c for c in text if c.isprintable() or c in "\n\r\t")
                            if clean_text.strip():
                                pages_text.append(clean_text.strip())
                    if pages_text:
                        return "\n\n--- PAGE BREAK ---\n\n".join(pages_text)
                    return "[Scanned/Image PDF - no extractable text found]"
                except Exception as pdf_err:
                    return f"[Error extracting PDF text: {str(pdf_err)}]"
        except Exception as e:
            return f"Error reading file: {str(e)}"
        return ""



    @classmethod
    def ingest_files(cls, dir_name: str, table_name: str, files_info: List[Dict[str, Any]],
                     progress_callback: Optional[Any] = None) -> Dict[str, Any]:
        """Ingest a list of scanned file metadata into the selected Pixeltable table."""
        if not files_info:
            return {"status": "error", "message": "No files provided for ingestion. Please scan a directory first."}

        if not PIXELTABLE_AVAILABLE:
            return {
                "status": "error",
                "message": "Pixeltable is not installed in the current environment (`uv pip install pixeltable`)."
            }

        try:
            valid_dir, safe_dir, dir_msg = sanitize_identifier(dir_name or "default")
            valid_tbl, safe_tbl, tbl_msg = sanitize_identifier(table_name or "raw_assets")
            if not valid_dir:
                return {"status": "error", "message": f"Invalid Domain name: {dir_msg}"}
            if not valid_tbl:
                return {"status": "error", "message": f"Invalid Table name: {tbl_msg}"}

            if progress_callback:
                progress_callback(0, len(files_info), f"Initializing table '{safe_dir}.{safe_tbl}'...")

            table = cls.get_or_create_table(safe_dir, safe_tbl)
            rows_to_insert = []
            total_files = len(files_info)

            for idx, f in enumerate(files_info):
                abs_path = f.get("abs_path", "")
                modality = f.get("modality", "other")
                ext = f.get("extension", "")
                file_name = f.get("name", Path(abs_path).name)

                if progress_callback and (idx % 5 == 0 or idx == total_files - 1):
                    progress_callback(idx + 1, total_files, f"Reading file {idx + 1}/{total_files}: {file_name}")

                content = cls.extract_file_content(abs_path, modality, ext)

                row = {
                    "file_name": file_name,
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

            if progress_callback:
                progress_callback(total_files, total_files, f"Committing {len(rows_to_insert)} rows to database...")

            table.insert(rows_to_insert, on_error="ignore")
            total_count = table.count()
            
            note = f" (Name adjusted: '{safe_dir}.{safe_tbl}')" if (safe_dir != dir_name or safe_tbl != table_name) else ""
            return {
                "status": "success",
                "message": f"Successfully ingested {len(rows_to_insert)} rows into '{safe_dir}.{safe_tbl}'{note}. Total rows in table: {total_count}",
                "inserted_count": len(rows_to_insert),
                "total_count": total_count,
                "domain": safe_dir,
                "table": safe_tbl
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to ingest files into Pixeltable:\n{type(e).__name__}: {str(e)}\n\n"
                           f"Hint: Table and Domain names cannot contain dashes '-' or start with digits."
            }

    @classmethod
    def get_table_data(cls, dir_name: str, table_name: str, limit: int = 50,
                       lightweight: bool = True) -> Dict[str, Any]:
        """Fetch rows from Pixeltable table for UI display with lightweight/full toggle."""
        if not PIXELTABLE_AVAILABLE:
            return {
                "columns": ["Notice"],
                "data": [["Pixeltable is not installed yet. Run `uv pip install pixeltable` to enable DB storage."]],
                "total_rows": 0
            }
        try:
            full_table_path = cls.resolve_table_path(dir_name, table_name)
            safe_dir, safe_tbl = full_table_path.split(".", 1)
            
            table = pxt.get_table(full_table_path)
            df = table.limit(limit).collect().to_pandas()
            
            display_cols = list(df.columns)
            if lightweight:
                # Omit raw binary media handles from preview
                heavy_cols = {"doc", "image", "audio", "video"}
                display_cols = [c for c in display_cols if c not in heavy_cols]
                df = df[display_cols]
                
                # Truncate long text columns to 250 chars for fast rendering
                for col in df.columns:
                    if df[col].dtype == "object":
                        df[col] = df[col].apply(
                            lambda x: (str(x)[:250] + "...") if isinstance(x, str) and len(x) > 250 else (str(x) if x is not None else "")
                        )
            else:
                for col in df.columns:
                    if df[col].dtype == "object":
                        df[col] = df[col].apply(lambda x: str(x) if x is not None else "")

            return {
                "columns": list(df.columns),
                "data": df.fillna("").values.tolist(),
                "total_rows": table.count(),
                "domain": safe_dir,
                "table": safe_tbl
            }
        except Exception as e:
            return {
                "columns": [],
                "data": [],
                "total_rows": 0,
                "error": f"{type(e).__name__}: {str(e)}"
            }




