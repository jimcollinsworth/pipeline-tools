import os
from pathlib import Path
from typing import List, Dict, Any

SUPPORTED_EXTENSIONS = {
    "docs": {".pdf", ".md", ".markdown", ".txt", ".json", ".yaml", ".yml", ".csv"},
    "images": {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"},
    "audio": {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"},
    "video": {".mp4", ".mkv", ".mov", ".avi", ".webm"}
}

def classify_modality(ext: str) -> str:
    ext = ext.lower()
    for modality, extensions in SUPPORTED_EXTENSIONS.items():
        if ext in extensions:
            return modality
    return "other"

def scan_directory(directory_path: str, recursive: bool = True, modalities: List[str] = None) -> List[Dict[str, Any]]:
    """Recursively scan a directory for supported multimodal files."""
    root = Path(directory_path)
    if not root.exists() or not root.is_dir():
        return []

    if modalities is None:
        modalities = ["docs", "images", "audio", "video", "other"]

    files_info = []
    pattern = "**/*" if recursive else "*"

    for p in root.glob(pattern):
        if p.is_file():
            ext = p.suffix.lower()
            modality = classify_modality(ext)
            if modality in modalities:
                try:
                    stat = p.stat()
                    size_kb = round(stat.st_size / 1024, 2)
                    size_mb = round(size_kb / 1024, 2)
                    size_str = f"{size_mb} MB" if size_mb >= 1.0 else f"{size_kb} KB"
                    files_info.append({
                        "name": p.name,
                        "rel_path": str(p.relative_to(root)),
                        "abs_path": str(p.resolve()),
                        "modality": modality,
                        "extension": ext,
                        "size": size_str,
                        "size_bytes": stat.st_size,
                        "modified": stat.st_mtime
                    })
                except Exception:
                    continue

    return sorted(files_info, key=lambda x: (x["modality"], x["name"]))


def scan_single_file(file_path: str, max_preview_rows: int = 10) -> Dict[str, Any]:
    """Inspect a single row-oriented file (CSV/TSV) without directory traversal."""
    import csv
    p = Path(file_path)
    if not p.exists() or not p.is_file():
        return {
            "status": "error",
            "message": f"File '{file_path}' does not exist or is not a regular file."
        }

    ext = p.suffix.lower()
    if ext not in [".csv", ".tsv", ".tab"]:
        return {
            "status": "error",
            "message": f"Unsupported row-oriented file extension '{ext}'. Only .csv and .tsv files are supported."
        }

    delimiter = "\t" if ext in [".tsv", ".tab"] else ","
    stat = p.stat()
    size_kb = round(stat.st_size / 1024, 2)
    size_mb = round(size_kb / 1024, 2)
    size_str = f"{size_mb} MB" if size_mb >= 1.0 else f"{size_kb} KB"

    headers: List[str] = []
    preview_rows: List[List[str]] = []
    total_rows = 0

    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f, delimiter=delimiter)
            try:
                headers = next(reader)
            except StopIteration:
                return {
                    "status": "error",
                    "message": f"File '{p.name}' is empty."
                }

            # Strip whitespace and normalize header names
            headers = [h.strip() if h else f"col_{i+1}" for i, h in enumerate(headers)]

            # Read sample preview rows
            for row in reader:
                total_rows += 1
                if len(preview_rows) < max_preview_rows:
                    # Pad or truncate row to header length
                    padded = list(row) + [""] * (len(headers) - len(row))
                    preview_rows.append([str(c) for c in padded[:len(headers)]])

            # Continue counting any remaining rows without loading into memory
            for _ in reader:
                total_rows += 1

    except Exception as e:
        return {
            "status": "error",
            "message": f"Error reading file '{p.name}': {str(e)}"
        }

    return {
        "status": "success",
        "name": p.name,
        "abs_path": str(p.resolve()),
        "rel_path": p.name,
        "modality": "docs",
        "extension": ext,
        "size": size_str,
        "size_bytes": stat.st_size,
        "row_count": total_rows,
        "columns": headers,
        "preview_rows": preview_rows
    }
