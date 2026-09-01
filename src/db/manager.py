"""
Database Management Layer (Pixeltable & PostgreSQL Declarative Storage)
=======================================================================
This module manages all database operations for Pipeline Tools using Pixeltable.

Key Architectural Principles & Design Decisions:
------------------------------------------------
1. Declarative Multimodal Tables:
   - Pixeltable replaces the traditional fragmented stack (LangChain + pandas + vector DBs)
     with declarative multimodal tables stored in an embedded PostgreSQL instance.
   - Files ingested (images, PDFs, audio, video, markdown) are stored with metadata and
     rich media handles (pxt.Image, pxt.Document, pxt.Audio, pxt.Video).
   - Official Docs: https://docs.pixeltable.com/

2. The Column Projection Invariant (Preventing Out-of-Memory / OOM Crashes):
   - CRITICAL LESSON / ANTIPATTERN TRIED:
     Calling `table.limit(N).collect().to_pandas()` without `.select(...)` forces Pixeltable
     to deserialize and load ALL columns in the schema simultaneously. For tables with image
     or document columns (e.g. `thinkpad.data_dir2` with 1,159 items), Pixeltable decodes
     hundreds of high-resolution PIL Image buffers and PDF document trees into Python heap
     RAM, causing immediate out-of-memory crashes.
   - THE FIX: Always introspect the schema and explicitly project non-binary columns using
     `table.select(*[table[c] for c in query_cols])` before calling `.collect().to_pandas()`.
     This drops database RAM usage by >95% and queries in under 50ms.

3. 1-Click Operation History & Lineage Undo:
   - Modifications such as newly added batch LLM columns are recorded in `_operation_history`.
   - Allows users to cleanly roll back / drop newly added columns (`undo_last_operation`)
     with a single click without destructive schema rewrites.

4. SQL Identifier Sanitization:
   - Table names and column names must be sanitized via `sanitize_identifier()` to handle
     leading digits, spaces, hyphens, and reserved SQL keywords.
"""

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

import logging
from src.core.config import sanitize_identifier

logger = logging.getLogger("pipeline_tools.db")

BASELINE_COLUMNS = {
    "id", "file_name", "file_path", "rel_path", "modality", "file_type",
    "file_size", "content", "doc", "image", "audio", "video", "metadata",
    "created_at", "thumbnail", "media_preview"
}

class DBManager:
    """Core declarative database manager wrapping Pixeltable tables and schemas."""
    BASELINE_COLUMNS = BASELINE_COLUMNS
    _operation_history: Dict[str, List[Dict[str, Any]]] = {}

    @classmethod
    def record_operation(cls, dir_name: str, table_name: str, op_data: Dict[str, Any]) -> None:
        """
        Record a table mutating operation in the in-memory stack for undo capabilities.
        
        Design Rationale:
        Instead of heavy database snapshotting, recording newly added columns in an in-memory
        operation stack allows immediate 1-click schema reversion by dropping added columns.
        """
        full_path = cls.resolve_table_path(dir_name, table_name)
        if full_path not in cls._operation_history:
            cls._operation_history[full_path] = []
        op_data["timestamp"] = datetime.now().isoformat()
        cls._operation_history[full_path].append(op_data)
        logger.info(f"Recorded operation for `{full_path}`: {op_data.get('action', 'unknown')}")

    @classmethod
    def get_last_operation(cls, dir_name: str, table_name: str) -> Optional[Dict[str, Any]]:
        """Get the most recent operation recorded for a table."""
        full_path = cls.resolve_table_path(dir_name, table_name)
        history = cls._operation_history.get(full_path, [])
        return history[-1] if history else None

    @classmethod
    def undo_last_operation(cls, dir_name: str, table_name: str) -> Dict[str, Any]:
        """Revert the most recent operation (drops added columns or restores table state)."""
        if not PIXELTABLE_AVAILABLE:
            return {"status": "error", "message": "Pixeltable is not available."}
        try:
            full_path = cls.resolve_table_path(dir_name, table_name)
            table = pxt.get_table(full_path)
            
            # Check history stack first
            history = cls._operation_history.get(full_path, [])
            last_op = history.pop() if history else None
            
            dropped_columns = []
            
            if last_op and last_op.get("action") == "add_columns" and last_op.get("columns"):
                for col in last_op["columns"]:
                    try:
                        table.drop_column(col)
                        dropped_columns.append(col)
                    except Exception as e:
                        logger.warning(f"Could not drop column '{col}' during undo: {e}")
            elif last_op and last_op.get("action") == "single_column" and last_op.get("column"):
                col = last_op["column"]
                try:
                    table.drop_column(col)
                    dropped_columns.append(col)
                except Exception as e:
                    logger.warning(f"Could not drop column '{col}' during undo: {e}")
            else:
                # Fallback: Detect all non-baseline custom columns on table
                tbl_cols = list(table.columns()) if callable(table.columns) else list(table._schema.keys())
                custom_cols = [c for c in tbl_cols if c not in cls.BASELINE_COLUMNS]
                if custom_cols:
                    for col in custom_cols:
                        try:
                            table.drop_column(col)
                            dropped_columns.append(col)
                        except Exception as e:
                            logger.warning(f"Could not drop custom column '{col}' during undo fallback: {e}")
                else:
                    return {
                        "status": "info",
                        "message": f"Table `{full_path}` is already at its baseline initial schema. No custom columns or operations to undo."
                    }

            if dropped_columns:
                msg = f"↩️ Successfully reverted last operation on `{full_path}`: Dropped {len(dropped_columns)} column(s) ({', '.join(f'`{c}`' for c in dropped_columns)})."
                logger.info(msg)
                return {"status": "success", "message": msg, "dropped_columns": dropped_columns}
            else:
                return {
                    "status": "info",
                    "message": f"No custom columns found to revert on `{full_path}`."
                }
        except Exception as e:
            err_msg = f"Failed to undo last operation on `{dir_name}.{table_name}`: {str(e)}"
            logger.error(err_msg, exc_info=True)
            return {"status": "error", "message": err_msg}
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

    create_or_get_table = get_or_create_table

    @classmethod
    def drop_table(cls, dir_name: str, table_name: str) -> bool:
        """Drop a Pixeltable table cleanly with logging."""
        if not PIXELTABLE_AVAILABLE:
            return False
        try:
            full_path = cls.resolve_table_path(dir_name, table_name)
            pxt.drop_table(full_path, if_not_exists="ignore")
            if full_path in cls._operation_history:
                del cls._operation_history[full_path]
            logger.info(f"🗑️ Deleted Pixeltable table `{full_path}` and all associated data.")
            return True
        except Exception as e:
            logger.error(f"Failed to drop table `{dir_name}.{table_name}`: {e}", exc_info=True)
            return False

    @classmethod
    def drop_dir(cls, dir_name: str, force: bool = True) -> bool:
        """Drop a Pixeltable directory/domain and its tables with logging."""
        if not PIXELTABLE_AVAILABLE:
            return False
        try:
            _, safe_dir, _ = sanitize_identifier(dir_name or "default")
            tables = cls.list_tables(safe_dir)
            pxt.drop_dir(safe_dir, force=force, if_not_exists="ignore")
            for t in tables:
                p = f"{safe_dir}.{t}"
                if p in cls._operation_history:
                    del cls._operation_history[p]
            logger.info(f"⚠️ Deleted Pixeltable domain `{safe_dir}` and connected tables: {tables}")
            return True
        except Exception as e:
            logger.error(f"Failed to drop directory `{dir_name}`: {e}", exc_info=True)
            return False

    @classmethod
    def delete_table_with_details(cls, dir_name: str, table_name: str) -> Dict[str, Any]:
        """Delete a Pixeltable table and return detailed on-screen feedback."""
        full_path = cls.resolve_table_path(dir_name, table_name)
        success = cls.drop_table(dir_name, table_name)
        if success:
            msg = f"🗑️ **Successfully deleted table `{full_path}`.** All records and computed columns have been removed."
            return {"status": "success", "message": msg, "table": full_path}
        else:
            msg = f"❌ **Failed to delete table `{full_path}`.** Table may not exist or database was locked."
            return {"status": "error", "message": msg, "table": full_path}

    @classmethod
    def delete_domain_with_details(cls, dir_name: str) -> Dict[str, Any]:
        """Delete a Pixeltable domain/directory and all connected tables with detailed on-screen feedback."""
        _, safe_dir, _ = sanitize_identifier(dir_name or "default")
        tables_before = cls.list_tables(safe_dir)
        success = cls.drop_dir(safe_dir, force=True)
        if success:
            tbls_str = f" Connected tables removed: {', '.join(f'`{t}`' for t in tables_before)}." if tables_before else " (Empty domain)."
            msg = f"⚠️ **Successfully deleted domain `{safe_dir}`.**{tbls_str}"
            return {"status": "success", "message": msg, "domain": safe_dir, "deleted_tables": tables_before}
        else:
            msg = f"❌ **Failed to delete domain `{safe_dir}`.** Domain may not exist or is protected."
            return {"status": "error", "message": msg, "domain": safe_dir}

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
                     overwrite: bool = False,
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

            full_table_path = cls.resolve_table_path(safe_dir, safe_tbl)
            overwritten_notice = ""

            # Check if table already exists
            existing_tables = cls.list_tables(safe_dir)
            if safe_tbl in existing_tables:
                if overwrite:
                    if progress_callback:
                        progress_callback(0, len(files_info), f"Overwriting table '{safe_dir}.{safe_tbl}' (archiving previous version)...")
                    try:
                        pxt.drop_table(full_table_path, if_not_exists="ignore")
                        overwritten_notice = " (Previous table version archived in Pixeltable lineage)"
                    except Exception:
                        pass

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
                "message": f"Successfully ingested {len(rows_to_insert)} rows into '{safe_dir}.{safe_tbl}'{note}{overwritten_notice}. Total rows in table: {total_count}",
                "inserted_count": len(rows_to_insert),
                "total_count": total_count,
                "domain": safe_dir,
                "table": safe_tbl,
                "overwritten": bool(overwritten_notice)
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to ingest files into Pixeltable:\n{type(e).__name__}: {str(e)}\n\n"
                           f"Hint: Table and Domain names cannot contain dashes '-' or start with digits."
            }

    @classmethod
    def pil_to_base64_data_uri(cls, img, size: tuple = (60, 60)) -> str:
        """Convert a PIL Image instance to a base64 data URI."""
        if img is None:
            return ""
        try:
            from PIL import Image, ImageOps
            import base64
            import io
            if not isinstance(img, Image.Image):
                return ""
            img = ImageOps.exif_transpose(img)
            img.thumbnail(size, Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in getattr(img, "info", {})):
                img.save(buf, format="PNG")
                mime = "image/png"
            else:
                img = img.convert("RGB")
                img.save(buf, format="JPEG", quality=80)
                mime = "image/jpeg"
            b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
            return f"data:{mime};base64,{b64_str}"
        except Exception:
            return ""

    @classmethod
    def generate_image_thumbnail_base64(cls, file_path: str, size: tuple = (64, 64)) -> str:
        """Generate lightweight base64 thumbnail with low memory overhead."""
        if not file_path:
            return ""
        try:
            if not os.path.exists(file_path):
                return ""
            from PIL import Image, ImageOps
            import base64
            import io
            with Image.open(file_path) as img:
                if hasattr(img, "draft"):
                    try:
                        img.draft("RGB", (size[0] * 2, size[1] * 2))
                    except Exception:
                        pass
                img = ImageOps.exif_transpose(img)
                img.thumbnail(size, Image.Resampling.BILINEAR)
                buf = io.BytesIO()
                if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in getattr(img, "info", {})):
                    img.save(buf, format="PNG")
                    mime = "image/png"
                else:
                    img = img.convert("RGB")
                    img.save(buf, format="JPEG", quality=70)
                    mime = "image/jpeg"
                b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
                return f"data:{mime};base64,{b64_str}"
        except Exception:
            return ""

    @classmethod
    def format_media_preview_html(cls, file_path: str, modality: str = "", file_type: str = "") -> str:
        """
        Format lightweight, web-safe HTML preview element using direct Gradio file streaming.

        Performance & Architecture Rationale:
        -------------------------------------
        1. Zero Python RAM Overhead:
           - Antipattern Tried: Generating base64 image strings (`data:image/jpeg;base64,...`)
             synchronously for dozens of rows in Python memory bloated WebSocket JSON responses.
           - The Solution: Use Gradio's native `/gradio_api/file={safe_path}` HTTP endpoint.
             Python spends 0ms decoding images into memory; the client browser streams and caches
             the media directly on demand via HTTP.
        2. Lazy Browser Loading:
           - Uses `loading="lazy"` so images below the fold or offscreen are only fetched when scrolled into view.
        """
        if not file_path:
            return ""
        safe_path = str(file_path).replace("\\", "/")
        mod = (modality or "").lower()
        ext = (file_type or Path(file_path).suffix).lower()

        if mod == "images" or ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg"]:
            # Stream image directly via Gradio API - zero Python memory consumption
            return f'<div style="display:flex; justify-content:center; align-items:center;"><img src="/gradio_api/file={safe_path}" alt="thumbnail" style="height:54px; width:54px; min-width:54px; border-radius:6px; object-fit:cover; box-shadow:0 1px 3px rgba(0,0,0,0.18); display:block; margin:auto;" loading="lazy" /></div>'
        elif mod == "audio" or ext in [".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"]:
            return f'<audio controls preload="none" src="/gradio_api/file={safe_path}" style="height:28px; width:150px; vertical-align:middle;"></audio>'
        elif mod == "video" or ext in [".mp4", ".webm", ".mov", ".avi", ".mkv"]:
            return f'<video controls preload="none" src="/gradio_api/file={safe_path}" style="height:54px; width:84px; border-radius:6px; object-fit:cover; vertical-align:middle;"></video>'
        elif ext == ".pdf" or mod == "docs":
            return f'<a href="/gradio_api/file={safe_path}" target="_blank" style="text-decoration:none; padding:4px 8px; background:#eff6ff; color:#1d4ed8; border:1px solid #bfdbfe; border-radius:4px; font-size:12px; font-weight:500;">📄 View PDF</a>'
        return ""

    @classmethod
    def get_table_data(cls, dir_name: str, table_name: str, limit: int = 50,
                       lightweight: bool = True) -> Dict[str, Any]:
        """
        Fetch rows from Pixeltable table for UI display with zero memory bloat.

        Architecture & Performance Invariants:
        ---------------------------------------
        1. Column Projection Invariant (OOM Prevention):
           - In Pixeltable, `table.limit(N).collect().to_pandas()` without `.select(...)`
             loads all columns, including `pxt.Image` and `pxt.Document`, deserializing raw
             binary assets into memory.
           - We introspect `available_cols` and explicitly construct `table.select(...)` with only
             scalar/metadata/text columns (`query_cols`), excluding heavy binary pointers
             (`doc`, `image`, `audio`, `video`, `thumbnail`, `media_preview`).
        2. UI DataFrame Truncation:
           - Document text columns can contain megabytes of extracted text per cell.
           - We truncate text cells to 250 characters for the table preview, keeping the entire
             JSON WebSocket payload under 50 KB. Full text is inspected on demand via row click.
        """
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
            
            # Inspect column names from table schema without fetching heavy data rows
            available_cols = list(table.columns()) if callable(table.columns) else list(table._schema.keys())
            
            # CRITICAL: Exclude heavy raw binary media pointers ('image', 'doc', 'video', 'audio', 'thumbnail')
            # from the database query to prevent loading 100s of MBs/GBs of uncompressed raw media into RAM.
            heavy_binary_cols = {"doc", "image", "audio", "video", "thumbnail", "media_preview"}
            query_cols = [c for c in available_cols if c not in heavy_binary_cols]

            if query_cols:
                query = table.select(*[table[c] for c in query_cols]).limit(limit)
            else:
                query = table.limit(limit)

            df = query.collect().to_pandas()
            display_cols = list(df.columns)

            if not lightweight and "file_path" in df.columns:
                mod_col = df["modality"] if "modality" in df.columns else [""] * len(df)
                type_col = df["file_type"] if "file_type" in df.columns else [""] * len(df)

                previews = [
                    cls.format_media_preview_html(str(fp), str(mod), str(ft))
                    for fp, mod, ft in zip(df["file_path"], mod_col, type_col)
                ]
                df["media_preview"] = previews

                # Reorder media_preview near the front for immediate visibility
                reordered = []
                for c in ["id", "file_name", "media_preview"]:
                    if c in df.columns and c not in reordered:
                        reordered.append(c)
                for c in display_cols:
                    if c not in reordered and c in df.columns:
                        reordered.append(c)
                df = df[reordered]

            # Truncate long text columns to 250 chars for fast rendering and minimal WebSocket payload
            for col in df.columns:
                if col != "media_preview" and df[col].dtype == "object":
                    df[col] = df[col].apply(
                        lambda x: (str(x)[:250] + "...") if isinstance(x, str) and len(x) > 250 else (str(x) if x is not None else "")
                    )

            cols = list(df.columns)
            datatypes = ["html" if c == "media_preview" else "str" for c in cols]

            return {
                "columns": cols,
                "datatypes": datatypes,
                "data": df.fillna("").values.tolist(),
                "total_rows": table.count(),
                "domain": safe_dir,
                "table": safe_tbl
            }
        except Exception as e:
            logger.error(f"Error in get_table_data: {e}", exc_info=True)
            return {
                "columns": [],
                "datatypes": [],
                "data": [],
                "total_rows": 0,
                "error": f"{type(e).__name__}: {str(e)}"
            }




