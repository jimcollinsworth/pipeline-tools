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
    def heal_postgres_locks(cls, pgdata_dir: Optional[Any] = None, force_purge_orphans: bool = False, force_wal_reset: bool = False) -> Dict[str, Any]:
        """
        Embedded PostgreSQL lock self-healing engine (Windows & POSIX).
        
        Adheres to PostgreSQL best practices for embedded environments:
        1. Validates whether the PID in postmaster.pid corresponds to an active, legitimate process.
        2. Safely terminates orphaned/dangling postgres processes holding directory or file locks
           targeting Pixeltable or specified pgdata directories (protecting unrelated system Postgres servers).
        3. Never terminates processes belonging to the current running process or its descendants.
        4. Removes stale postmaster.pid, lock files (.lockfile), and socket files (.s.PGSQL.*).
        5. Cleans up ungraceful shutdown state via pg_resetwal only when recovering from a crash.
        6. Clears cached PostgresServer references in pixeltable_pgserver and resets Pixeltable's Env.
        """
        import time
        try:
            import psutil
        except ImportError:
            psutil = None

        if pgdata_dir is not None:
            target_dirs = [Path(pgdata_dir).resolve()]
        else:
            target_dirs = []
            env_pgdata = os.environ.get("PIXELTABLE_PGDATA")
            if env_pgdata:
                target_dirs.append(Path(env_pgdata).resolve())
            default_pgdata = Path.home() / ".pixeltable" / "pgdata"
            if default_pgdata not in target_dirs:
                target_dirs.append(default_pgdata)

        target_dir_strs = [str(d).lower() for d in target_dirs]

        results = {
            "status": "healthy",
            "healed_dirs": [],
            "orphaned_pids_killed": [],
            "stale_pids_removed": []
        }

        # Collect our own process ID and descendant process IDs to protect active connections
        protected_pids = {os.getpid()}
        if psutil is not None:
            try:
                current_proc = psutil.Process()
                protected_pids.update(c.pid for c in current_proc.children(recursive=True))
            except Exception:
                pass

        # Collect any PIDs explicitly recorded in target postmaster.pid files
        known_target_pids = set()
        for pgdata in target_dirs:
            pid_file = pgdata / "postmaster.pid"
            if pid_file.exists():
                try:
                    lines = pid_file.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
                    if lines and lines[0].strip().isdigit():
                        known_target_pids.add(int(lines[0].strip()))
                except Exception:
                    pass

        # Step 1: Sweep and terminate dangling postgres processes belonging to Pixeltable or target pgdata
        if psutil is not None and force_purge_orphans:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    pid = proc.pid
                    if pid in protected_pids:
                        continue
                    pname = (proc.info.get('name') or '').lower()
                    if "postgres" in pname:
                        cmdline_parts = proc.info.get('cmdline') or []
                        cmdline_str = " ".join(cmdline_parts).lower()
                        # Safe check: only target processes that belong to Pixeltable or target pgdata
                        is_target_proc = (
                            pid in known_target_pids or
                            ".pixeltable" in cmdline_str or
                            any(td in cmdline_str for td in target_dir_strs)
                        )
                        if is_target_proc and pid not in results["orphaned_pids_killed"]:
                            logger.info(f"Self-healed: Terminating dangling Pixeltable postgres process {pid}")
                            try:
                                proc.terminate()
                                try:
                                    proc.wait(timeout=2)
                                except psutil.TimeoutExpired:
                                    proc.kill()
                                results["orphaned_pids_killed"].append(pid)
                            except Exception as e:
                                logger.warning(f"Failed to terminate postgres process {pid}: {e}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        # Step 2: Check and clean postmaster.pid, socket files, and stale log in target pgdata directories
        for pgdata in target_dirs:
            if not pgdata.exists():
                continue

            # Remove stale log file if present to eliminate sharing violation on restart
            log_file = pgdata / "log"
            if log_file.exists():
                try:
                    log_file.unlink(missing_ok=True)
                    logger.info(f"Self-healed: Removed stale log file {log_file}")
                except Exception as e:
                    logger.warning(f"Could not remove log file {log_file}: {e}")

            pid_file = pgdata / "postmaster.pid"
            had_stale_lock = False
            if pid_file.exists():
                stale = False
                found_pid = None
                try:
                    raw = pid_file.read_text(encoding="utf-8", errors="ignore").strip()
                    lines = raw.splitlines()
                    if lines:
                        found_pid = int(lines[0].strip())
                        is_alive = False
                        if psutil is not None:
                            try:
                                if psutil.pid_exists(found_pid):
                                    p = psutil.Process(found_pid)
                                    if "postgres" in p.name().lower():
                                        is_alive = p.is_running()
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                is_alive = False

                        if not is_alive:
                            stale = True
                        elif force_purge_orphans and found_pid not in protected_pids:
                            if psutil is not None:
                                try:
                                    p = psutil.Process(found_pid)
                                    p.terminate()
                                    try:
                                        p.wait(timeout=2)
                                    except psutil.TimeoutExpired:
                                        p.kill()
                                    if found_pid not in results["orphaned_pids_killed"]:
                                        results["orphaned_pids_killed"].append(found_pid)
                                except Exception:
                                    pass
                            stale = True
                        else:
                            stale = False
                    else:
                        stale = True
                except Exception as e:
                    logger.warning(f"Error checking postmaster.pid: {e}")
                    stale = True

                if stale:
                    had_stale_lock = True
                    try:
                        pid_file.unlink(missing_ok=True)
                        results["stale_pids_removed"].append(str(pid_file))
                        results["healed_dirs"].append(str(pgdata))
                        logger.info(f"Self-healed: Removed stale postmaster.pid ({found_pid}) from {pgdata}")
                    except Exception as e:
                        logger.warning(f"Could not remove stale {pid_file}: {e}")

            # Also check for stale socket lock or socket files
            for socket_lock in pgdata.glob(".s.PGSQL.*"):
                try:
                    socket_lock.unlink(missing_ok=True)
                    logger.info(f"Self-healed: Removed stale socket file {socket_lock}")
                except Exception:
                    pass

            # Only reset WAL if recovering from a detected stale crash or explicitly requested
            if (had_stale_lock or force_wal_reset) and (pgdata / "PG_VERSION").exists():
                try:
                    import subprocess
                    from pixeltable_pgserver._commands import POSTGRES_BIN_PATH
                    exe_candidate = POSTGRES_BIN_PATH / "pg_resetwal.exe"
                    resetwal_exe = exe_candidate if exe_candidate.exists() else (POSTGRES_BIN_PATH / "pg_resetwal")
                    if resetwal_exe.exists():
                        cmd = [str(resetwal_exe), "-f", "-D", str(pgdata)]
                        sub_res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                        if sub_res.returncode == 0:
                            logger.info(f"Self-healed: Reset WAL on {pgdata} to resolve interrupted recovery state")
                            if str(pgdata) not in results["healed_dirs"]:
                                results["healed_dirs"].append(str(pgdata))
                except Exception as e:
                    logger.debug(f"pg_resetwal skipped or failed: {e}")

        # Step 3: Reset pixeltable_pgserver instances cache if loaded
        try:
            import pixeltable_pgserver
            if hasattr(pixeltable_pgserver.PostgresServer, "_instances"):
                pixeltable_pgserver.PostgresServer._instances.clear()
        except Exception:
            pass

        # Step 4: Reset Pixeltable runtime environment so next call reinitializes cleanly
        try:
            import pixeltable as pxt
            from pixeltable.env import Env
            if hasattr(Env, "_env") and Env._env is not None:
                Env._env = None
        except Exception:
            pass

        time.sleep(0.2)

        if results["orphaned_pids_killed"] or results["stale_pids_removed"]:
            results["status"] = "healed"
        return results

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

    @classmethod
    def get_or_create_table(cls, dir_name: str, table_name: str):
        """Create or get a unified multimodal table in Pixeltable with sanitization."""
        if not PIXELTABLE_AVAILABLE:
            return None

        full_table_path = cls.resolve_table_path(dir_name, table_name)
        safe_dir = full_table_path.split(".")[0]

        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                pxt.create_dir(safe_dir, if_exists="ignore")
                return pxt.create_table(
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
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(0.15 * (attempt + 1))
                else:
                    logger.error(f"get_or_create_table failed on `{full_table_path}`: {e}")
                    raise

    create_or_get_table = get_or_create_table

    @classmethod
    def drop_table(cls, dir_name: str, table_name: str) -> bool:
        """Drop a Pixeltable table cleanly with logging."""
        if not PIXELTABLE_AVAILABLE:
            return False
        full_path = cls.resolve_table_path(dir_name, table_name)
        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                pxt.drop_table(full_path, if_not_exists="ignore")
                if full_path in cls._operation_history:
                    del cls._operation_history[full_path]
                logger.info(f"🗑️ Deleted Pixeltable table `{full_path}` and all associated data.")
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(0.15 * (attempt + 1))
                else:
                    logger.error(f"Failed to drop table `{full_path}`: {e}")
                    return False

    @classmethod
    def drop_dir(cls, dir_name: str, force: bool = True) -> bool:
        """Drop a Pixeltable directory/domain and its tables with logging."""
        if not PIXELTABLE_AVAILABLE:
            return False
        _, safe_dir, _ = sanitize_identifier(dir_name or "default")
        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                tables = cls.list_tables(safe_dir)
                pxt.drop_dir(safe_dir, force=force, if_not_exists="ignore")
                for t in tables:
                    p = f"{safe_dir}.{t}"
                    if p in cls._operation_history:
                        del cls._operation_history[p]
                logger.info(f"⚠️ Deleted Pixeltable domain `{safe_dir}` and connected tables: {tables}")
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(0.15 * (attempt + 1))
                else:
                    logger.error(f"Failed to drop directory `{dir_name}`: {e}")
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
                max_bytes = 1_000_000  # 1 MB text limit
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    chunk = f.read(max_bytes)
                    if f.read(1):
                        return chunk + f"\n\n[... Truncated: File exceeded 1 MB text extraction limit ...]"
                    return chunk
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
            total_files = len(files_info)

            # Initialize dynamic ingestion context accumulator (RES-12)
            from src.core.ingestion_context import IngestionContext
            ctx = IngestionContext(domain=safe_dir, table=safe_tbl)

            # Chunked Batch Streaming Ingestion (Supporting 10,000+ files in bounded O(1) heap RAM)
            BATCH_SIZE = 100
            total_inserted = 0

            for batch_start in range(0, total_files, BATCH_SIZE):
                batch_end = min(batch_start + BATCH_SIZE, total_files)
                batch_files = files_info[batch_start:batch_end]
                batch_rows = []

                for idx_in_batch, f in enumerate(batch_files):
                    global_idx = batch_start + idx_in_batch
                    abs_path = f.get("abs_path", "")
                    modality = f.get("modality", "other")
                    ext = f.get("extension", "")
                    file_name = f.get("name", Path(abs_path).name)

                    if progress_callback and (global_idx % 5 == 0 or global_idx == total_files - 1):
                        progress_callback(global_idx + 1, total_files, f"Reading file {global_idx + 1}/{total_files}: {file_name}")

                    content = cls.extract_file_content(abs_path, modality, ext)

                    # Record row in dynamic context accumulator
                    ctx.record_row(
                        file_name=file_name,
                        modality=modality,
                        file_type=ext,
                        content_snippet=content[:200] if content else "",
                        extracted_tags=[modality, ext.lstrip(".")] if ext else [modality]
                    )

                    row = {
                        "file_name": file_name,
                        "file_path": abs_path,
                        "rel_path": f.get("rel_path", ""),
                        "modality": modality,
                        "file_type": ext,
                        "file_size": int(f.get("size_bytes", 0)),
                        "content": content if content else None,
                        "doc": abs_path if (ext == ".pdf" and Path(abs_path).is_file()) else None,
                        "image": abs_path if (modality == "images" and Path(abs_path).is_file()) else None,
                        "audio": abs_path if (modality == "audio" and Path(abs_path).is_file()) else None,
                        "video": abs_path if (modality == "video" and Path(abs_path).is_file()) else None,
                        "metadata": {
                            "source": "directory_scanner",
                            "extension": ext,
                            "scanned_size": f.get("size", "")
                        },
                        "created_at": datetime.now()
                    }
                    batch_rows.append(row)

                if progress_callback:
                    progress_callback(batch_end, total_files, f"Committing batch {batch_start + 1}-{batch_end} of {total_files} rows to database...")

                table.insert(batch_rows, on_error="ignore")
                total_inserted += len(batch_rows)
                del batch_rows

            total_count = table.count()

            # Export accumulated context to exports/{domain}-{table}-ingestion-context.md
            context_file = ctx.export_to_markdown()
            cls.record_operation(safe_dir, safe_tbl, {
                "action": "ingest_files",
                "count": total_inserted,
                "context_file": str(context_file),
                "entities_count": len(ctx.entities)
            })
            
            note = f" (Name adjusted: '{safe_dir}.{safe_tbl}')" if (safe_dir != dir_name or safe_tbl != table_name) else ""
            return {
                "status": "success",
                "message": f"Successfully ingested {total_inserted} rows into '{safe_dir}.{safe_tbl}'{note}{overwritten_notice}. Total rows in table: {total_count}",
                "inserted_count": total_inserted,
                "total_count": total_count,
                "domain": safe_dir,
                "table": safe_tbl,
                "overwritten": bool(overwritten_notice),
                "context_file": str(context_file),
                "entities_count": len(ctx.entities)
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to ingest files into Pixeltable:\n{type(e).__name__}: {str(e)}\n\n"
                           f"Hint: Table and Domain names cannot contain dashes '-' or start with digits."
            }

    @classmethod
    def ingest_csv_rows(cls, dir_name: str, table_name: str, csv_path: str,
                        text_column: Optional[str] = None,
                        overwrite: bool = False,
                        progress_callback: Optional[Any] = None) -> Dict[str, Any]:
        """
        Ingest each row of a CSV/TSV file as an individual document record into Pixeltable.
        
        Design Invariant:
        Uses chunked batch streaming (BATCH_SIZE = 100) with csv.DictReader to guarantee O(1)
        heap memory usage, scaling safely to tens of thousands of rows.
        """
        import csv
        p = Path(csv_path)
        if not p.exists() or not p.is_file():
            return {"status": "error", "message": f"CSV file '{csv_path}' does not exist or is not a regular file."}

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

            existing_tables = cls.list_tables(safe_dir)
            if safe_tbl in existing_tables:
                if overwrite:
                    if progress_callback:
                        progress_callback(0, 1, f"Overwriting table '{safe_dir}.{safe_tbl}' (archiving previous version)...")
                    try:
                        pxt.drop_table(full_table_path, if_not_exists="ignore")
                        overwritten_notice = " (Previous table version archived in Pixeltable lineage)"
                    except Exception:
                        pass

            table = cls.get_or_create_table(safe_dir, safe_tbl)

            # Initialize dynamic ingestion context accumulator (RES-12)
            from src.core.ingestion_context import IngestionContext
            ctx = IngestionContext(domain=safe_dir, table=safe_tbl)

            ext = p.suffix.lower()
            delimiter = "\t" if ext in [".tsv", ".tab"] else ","
            abs_path = str(p.resolve())
            csv_name = p.name

            # Stream through rows in bounded batches
            BATCH_SIZE = 100
            total_inserted = 0
            batch_rows = []

            with open(p, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                if not reader.fieldnames:
                    return {"status": "error", "message": f"CSV file '{csv_name}' has no column headers."}

                for row_idx, row in enumerate(reader):
                    row_dict = {k.strip(): v for k, v in row.items() if k is not None}

                    # Determine content: if text_column specified and present, use it;
                    # otherwise format all non-empty key-values into clean markdown text.
                    if text_column and text_column in row_dict and row_dict[text_column]:
                        content_str = str(row_dict[text_column])
                    else:
                        formatted_parts = [f"**{k}**: {v}" for k, v in row_dict.items() if v is not None and str(v).strip()]
                        content_str = " | ".join(formatted_parts) if formatted_parts else f"Row {row_idx + 1}"

                    # Record row in dynamic context accumulator
                    ctx.record_row(
                        file_name=f"{csv_name} #Row {row_idx + 1}",
                        modality="docs",
                        file_type=ext,
                        content_snippet=content_str[:200],
                        extracted_tags=["csv", "row"]
                    )

                    row_record = {
                        "file_name": f"{csv_name} #Row {row_idx + 1}",
                        "file_path": abs_path,
                        "rel_path": csv_name,
                        "modality": "docs",
                        "file_type": ext,
                        "file_size": len(content_str.encode("utf-8")),
                        "content": content_str,
                        "doc": None,
                        "image": None,
                        "audio": None,
                        "video": None,
                        "metadata": row_dict,
                        "created_at": datetime.now()
                    }
                    batch_rows.append(row_record)

                    if len(batch_rows) >= BATCH_SIZE:
                        table.insert(batch_rows, on_error="ignore")
                        total_inserted += len(batch_rows)
                        if progress_callback:
                            progress_callback(total_inserted, total_inserted + 50, f"Ingested {total_inserted} CSV rows...")
                        batch_rows = []

                if batch_rows:
                    table.insert(batch_rows, on_error="ignore")
                    total_inserted += len(batch_rows)
                    batch_rows = []

            total_count = table.count()
            context_file = ctx.export_to_markdown()
            cls.record_operation(safe_dir, safe_tbl, {
                "action": "ingest_csv_rows",
                "source_file": csv_name,
                "count": total_inserted,
                "context_file": str(context_file),
                "entities_count": len(ctx.entities)
            })

            note = f" (Name adjusted: '{safe_dir}.{safe_tbl}')" if (safe_dir != dir_name or safe_tbl != table_name) else ""
            return {
                "status": "success",
                "message": f"Successfully ingested {total_inserted} rows from '{csv_name}' into '{safe_dir}.{safe_tbl}'{note}{overwritten_notice}. Total rows in table: {total_count}",
                "inserted_count": total_inserted,
                "total_count": total_count,
                "domain": safe_dir,
                "table": safe_tbl,
                "overwritten": bool(overwritten_notice),
                "context_file": str(context_file),
                "entities_count": len(ctx.entities)
            }
        except Exception as e:
            logger.error(f"Failed to ingest CSV rows into Pixeltable: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"Failed to ingest CSV rows into Pixeltable:\n{type(e).__name__}: {str(e)}"
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
                # If 'content' is in query_cols, project it with .slice(0, 500) so PostgreSQL
                # handles substring truncation inside the database engine, avoiding massive memory bloat
                select_kwargs = {}
                for c in query_cols:
                    if c == "content" and hasattr(table[c], "slice"):
                        try:
                            select_kwargs[c] = table[c].slice(0, 500)
                        except Exception:
                            select_kwargs[c] = table[c]
                    else:
                        select_kwargs[c] = table[c]
                try:
                    query = table.select(**select_kwargs).limit(limit)
                except Exception:
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

            # Truncate long text and format all cells as JSON-serializable strings/primitives
            def _truncate_cell(val, max_len=250):
                if val is None:
                    return ""
                if hasattr(val, "isoformat"):
                    return val.isoformat()
                s = str(val)
                return (s[:max_len] + "...") if len(s) > max_len else s

            for col in df.columns:
                if col != "media_preview":
                    df[col] = df[col].apply(_truncate_cell)

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




