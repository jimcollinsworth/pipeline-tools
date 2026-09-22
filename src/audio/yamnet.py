"""
YAMNet Audio Event Classification & Acoustic Scene Tagging
==========================================================
Provides lightweight ONNX-based deep learning inference for Google's YAMNet model.
Predicts 521 AudioSet event categories (e.g. Speech, Music, Animal sounds, Vehicle noise, Sirens).
Exposes declarative Pixeltable UDFs for table computed columns and prompt-driven evaluation.
"""

import os
import csv
import logging
import functools
import urllib.request
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import numpy as np

import pixeltable as pxt
from src.db.manager import DBManager
from src.core.progress_tracker import RowProgressTracker

logger = logging.getLogger("pipeline_tools.audio.yamnet")

# Model assets URLs (Hugging Face verified mirror and TensorFlow official AudioSet class map)
YAMNET_ONNX_URL = "https://huggingface.co/zeropointnine/yamnet-onnx/resolve/main/yamnet.onnx"
YAMNET_CLASS_MAP_URL = "https://raw.githubusercontent.com/tensorflow/models/master/research/audioset/yamnet/yamnet_class_map.csv"

# Global session & class cache
_SESSION = None
_CLASS_NAMES: Optional[List[str]] = None


def get_yamnet_cache_dir() -> Path:
    """Return local cache directory for YAMNet assets."""
    try:
        cache_dir = Path.home() / ".cache" / "pipeline_tools" / "models" / "yamnet"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir
    except Exception:
        fallback = Path("./.cache/models/yamnet")
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def ensure_yamnet_assets() -> Tuple[Path, Path]:
    """Ensure yamnet.onnx and yamnet_class_map.csv exist locally, downloading if necessary."""
    cache_dir = get_yamnet_cache_dir()
    model_path = cache_dir / "yamnet.onnx"
    csv_path = cache_dir / "yamnet_class_map.csv"

    if not model_path.exists() or model_path.stat().st_size < 1000000:
        logger.info(f"Downloading YAMNet ONNX model to {model_path}...")
        try:
            req = urllib.request.Request(YAMNET_ONNX_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp, open(model_path, "wb") as f:
                f.write(resp.read())
            logger.info(f"Successfully downloaded YAMNet ONNX model ({model_path.stat().st_size} bytes).")
        except Exception as e:
            logger.error(f"Failed to download YAMNet ONNX model: {e}")
            raise RuntimeError(f"Could not download YAMNet ONNX model: {e}")

    if not csv_path.exists() or csv_path.stat().st_size < 1000:
        logger.info(f"Downloading YAMNet class map to {csv_path}...")
        try:
            req = urllib.request.Request(YAMNET_CLASS_MAP_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp, open(csv_path, "wb") as f:
                f.write(resp.read())
            logger.info("Successfully downloaded YAMNet class map.")
        except Exception as e:
            logger.error(f"Failed to download YAMNet class map: {e}")
            raise RuntimeError(f"Could not download YAMNet class map: {e}")

    return model_path, csv_path


def load_yamnet_classes() -> List[str]:
    """Load the 521 AudioSet display names from class map CSV."""
    global _CLASS_NAMES
    if _CLASS_NAMES is not None:
        return _CLASS_NAMES

    _, csv_path = ensure_yamnet_assets()
    names = []
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            names.append(row["display_name"])

    _CLASS_NAMES = names
    return _CLASS_NAMES


def get_yamnet_session():
    """Return cached ONNX Runtime InferenceSession for YAMNet."""
    global _SESSION
    if _SESSION is not None:
        return _SESSION

    import onnxruntime as ort
    model_path, _ = ensure_yamnet_assets()
    _SESSION = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    return _SESSION


def load_yamnet_waveform(
    audio_path: Optional[str],
    max_duration: Optional[float] = 60.0
) -> Optional[np.ndarray]:
    """
    Load audio and format as a 1D float32 waveform at 16,000 Hz normalized to [-1.0, 1.0].
    YAMNet strictly expects 16 kHz mono audio. Caps duration to max_duration (default 60s).
    """
    if not audio_path:
        return None

    path_obj = Path(audio_path)
    if not path_obj.exists() or not path_obj.is_file():
        return None

    # Load audio at 16,000 Hz using librosa / PyAV fallback with duration cap
    y = None
    target_sr = 16000

    try:
        from src.audio.spectrogram import load_audio_signal
        res = load_audio_signal(audio_path, sr=target_sr, duration=max_duration)
        if res is not None:
            y, sr = res
    except Exception as e:
        logger.debug(f"Direct signal load failed for '{audio_path}': {e}")

    if y is None or len(y) == 0:
        return None

    # Ensure float32 mono
    y = np.asarray(y, dtype=np.float32)
    if y.ndim > 1:
        y = np.mean(y, axis=0)

    # Normalize amplitude to [-1.0, 1.0] if clipping or high dynamic range
    max_abs = float(np.max(np.abs(y)))
    if max_abs > 1.0:
        y = y / max_abs

    # YAMNet requires at least ~0.1s (1600 samples)
    if len(y) < 1600:
        padded = np.zeros(1600, dtype=np.float32)
        padded[:len(y)] = y
        y = padded

    return y


@functools.lru_cache(maxsize=128)
def classify_audio_yamnet_core(
    audio_path: Optional[str],
    top_k: int = 5,
    min_confidence: float = 0.05,
    duration: float = 60.0
) -> Optional[Dict[str, Any]]:
    """
    Execute YAMNet inference on an audio file and return structured prediction results.
    Results are cached across top_k, min_confidence, and duration to eliminate redundant ONNX evaluations.
    """
    y = load_yamnet_waveform(audio_path, max_duration=duration)
    if y is None:
        return None

    try:
        session = get_yamnet_session()
        class_names = load_yamnet_classes()

        outputs = session.run(None, {"waveform": y})
        scores = outputs[0]  # Shape: (num_frames, 521)
        if scores.size == 0:
            return None

        # Mean probability across time frames
        mean_scores = np.mean(scores, axis=0)
        sorted_indices = np.argsort(mean_scores)[::-1]

        top_scores: Dict[str, float] = {}
        summary_items: List[str] = []

        primary_cat = "Unknown"
        primary_conf = 0.0

        for idx in sorted_indices:
            score = float(mean_scores[idx])
            if score < min_confidence and len(top_scores) >= 1:
                break
            cat_name = class_names[idx] if idx < len(class_names) else f"Class_{idx}"
            if not primary_cat or primary_cat == "Unknown":
                primary_cat = cat_name
                primary_conf = round(score, 4)

            top_scores[cat_name] = round(score, 4)
            pct = int(round(score * 100))
            summary_items.append(f"{cat_name} ({pct}%)")

            if len(top_scores) >= top_k:
                break

        sound_events = ", ".join(summary_items) if summary_items else primary_cat

        duration_sec = round(len(y) / 16000.0, 3)

        return {
            "primary_category": primary_cat,
            "primary_confidence": primary_conf,
            "sound_events": sound_events,
            "top_scores": top_scores,
            "duration_sec": duration_sec
        }
    except Exception as e:
        logger.error(f"YAMNet classification failed for '{audio_path}': {e}")
        return None


def get_yamnet_primary_category_core(
    audio_path: Optional[str],
    top_k: int = 5,
    min_confidence: float = 0.05,
    duration: float = 60.0
) -> Optional[str]:
    """Return top single predicted sound category name (hits single-pass LRU cache)."""
    res = classify_audio_yamnet_core(audio_path, top_k=top_k, min_confidence=min_confidence, duration=duration)
    return res["primary_category"] if res else None


def get_yamnet_sound_events_core(
    audio_path: Optional[str],
    top_k: int = 5,
    min_confidence: float = 0.05,
    duration: float = 60.0
) -> Optional[str]:
    """Return human-readable top-K sound events summary string (hits single-pass LRU cache)."""
    res = classify_audio_yamnet_core(audio_path, top_k=top_k, min_confidence=min_confidence, duration=duration)
    return res["sound_events"] if res else None


def get_yamnet_scores_core(
    audio_path: Optional[str],
    top_k: int = 5,
    min_confidence: float = 0.05,
    duration: float = 60.0
) -> Optional[Dict[str, float]]:
    """Return structured JSON dictionary of top-K sound event scores (hits single-pass LRU cache)."""
    res = classify_audio_yamnet_core(audio_path, top_k=top_k, min_confidence=min_confidence, duration=duration)
    return res["top_scores"] if res else None


# -------------------------------------------------------------------------
# Declarative Pixeltable UDFs
# -------------------------------------------------------------------------
@pxt.udf
def yamnet_primary_category(
    audio: Optional[pxt.Audio],
    top_k: int = 5,
    min_confidence: float = 0.05,
    duration: float = 60.0
) -> Optional[pxt.String]:
    """Declarative Pixeltable UDF: Extract top primary sound category via YAMNet."""
    RowProgressTracker.step(row_label=str(audio or ""))
    return get_yamnet_primary_category_core(audio, top_k=top_k, min_confidence=min_confidence, duration=duration)


@pxt.udf
def yamnet_sound_events(
    audio: Optional[pxt.Audio],
    top_k: int = 5,
    min_confidence: float = 0.05,
    duration: float = 60.0
) -> Optional[pxt.String]:
    """Declarative Pixeltable UDF: Extract top-K sound events summary string via YAMNet."""
    RowProgressTracker.step(row_label=str(audio or ""))
    return get_yamnet_sound_events_core(audio, top_k=top_k, min_confidence=min_confidence, duration=duration)


@pxt.udf
def yamnet_scores(
    audio: Optional[pxt.Audio],
    top_k: int = 5,
    min_confidence: float = 0.05,
    duration: float = 60.0
) -> Optional[pxt.Json]:
    """Declarative Pixeltable UDF: Extract top-K sound categories and confidence scores as JSON."""
    RowProgressTracker.step(row_label=str(audio or ""))
    return get_yamnet_scores_core(audio, top_k=top_k, min_confidence=min_confidence, duration=duration)


# -------------------------------------------------------------------------
# Declarative Table Attachment Helper
# -------------------------------------------------------------------------
def attach_yamnet_columns(
    domain: str,
    table_name: str,
    top_k: int = 5,
    min_confidence: float = 0.05,
    duration: float = 60.0
) -> Dict[str, Any]:
    """
    Declaratively attach sound_category, sound_events, and sound_scores computed columns
    to a Pixeltable table using native computed columns (no imperative loops).
    All 3 columns hit the single-pass LRU cache to execute ONNX inference only once per file.
    """
    full_table_path = DBManager.resolve_table_path(domain, table_name)
    try:
        tbl = pxt.get_table(full_table_path)
    except Exception as e:
        return {"status": "error", "message": f"Table '{full_table_path}' not found: {e}"}

    cols = list(tbl.columns()) if callable(tbl.columns) else list(tbl._schema.keys())
    audio_col = None
    if "audio" in cols:
        audio_col = tbl.audio
    elif "file_path" in cols:
        audio_col = tbl.file_path
    else:
        return {"status": "error", "message": f"Table '{full_table_path}' lacks an 'audio' or 'file_path' column."}

    columns_added = []
    total_rows = tbl.count()

    # 1. sound_category: top single category (e.g. "Speech")
    if "sound_category" not in cols:
        RowProgressTracker.start("YAMNet Sound Category", total_rows)
        tbl.add_computed_column(
            sound_category=yamnet_primary_category(
                audio_col, top_k=top_k, min_confidence=min_confidence, duration=duration
            ),
            if_exists="ignore"
        )
        RowProgressTracker.finish()
        columns_added.append("sound_category")

    # 2. sound_events: top-k human readable string (e.g. "Speech (87%), Music (62%)")
    if "sound_events" not in cols:
        RowProgressTracker.start("YAMNet Sound Events", total_rows)
        tbl.add_computed_column(
            sound_events=yamnet_sound_events(
                audio_col, top_k=top_k, min_confidence=min_confidence, duration=duration
            ),
            if_exists="ignore"
        )
        RowProgressTracker.finish()
        columns_added.append("sound_events")

    # 3. sound_scores: structured top-k dictionary (JSON)
    if "sound_scores" not in cols:
        RowProgressTracker.start("YAMNet Sound Scores", total_rows)
        tbl.add_computed_column(
            sound_scores=yamnet_scores(
                audio_col, top_k=top_k, min_confidence=min_confidence, duration=duration
            ),
            if_exists="ignore"
        )
        RowProgressTracker.finish()
        columns_added.append("sound_scores")

    return {
        "status": "success",
        "message": f"Successfully attached YAMNet audio classification columns to `{full_table_path}`.",
        "columns": columns_added or ["sound_category", "sound_events", "sound_scores"],
        "table": full_table_path
    }
