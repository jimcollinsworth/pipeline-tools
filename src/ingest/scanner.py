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
