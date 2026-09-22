"""
Mel Spectrogram Audio Analysis & Visualization (Declarative Pixeltable UDFs)
===========================================================================
This module provides declarative Pixeltable UDFs for computing Mel Spectrograms
from audio records, generating:
1. mel_spectrogram: 2D numpy array [128, T] representing dB-scaled mel power spectral density (pxt.Array).
2. mel_spectrogram_img: Rendered colormap PIL Image (pxt.Image) for visual inspection and UI display.
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use("Agg")  # Thread-safe headless rendering
import matplotlib.pyplot as plt
import librosa
import pixeltable as pxt
from src.db.manager import DBManager

logger = logging.getLogger("pipeline_tools.audio")


def load_audio_pyav(audio_path: str, target_sr: int = 22050) -> Optional[np.ndarray]:
    """Decode audio using PyAV into a 1D float32 mono array at target_sr (supports .m4a, .aac, .mp3, etc.)."""
    try:
        import av
        container = av.open(str(audio_path))
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            container.close()
            return None
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=target_sr)
        frames = []
        for packet in container.demux(stream):
            for frame in packet.decode():
                for rf in resampler.resample(frame):
                    frames.append(rf.to_ndarray().reshape(-1))
        for rf in resampler.resample(None):
            frames.append(rf.to_ndarray().reshape(-1))
        container.close()
        if not frames:
            return None
        return np.concatenate(frames).astype(np.float32)
    except Exception as e:
        logger.debug(f"PyAV audio decoding failed for '{audio_path}': {e}")
        return None


def load_audio_signal(audio_path: Optional[str], sr: int = 22050) -> Optional[Tuple[np.ndarray, int]]:
    """Helper to load audio using librosa with PyAV fallback, returning (y, sr) or None."""
    if not audio_path or not isinstance(audio_path, (str, Path)):
        return None
    p = Path(audio_path)
    if not p.is_file():
        return None

    y = None
    sample_rate = sr
    try:
        y, sample_rate = librosa.load(str(p), sr=sr, mono=True)
    except Exception as e:
        logger.debug(f"librosa.load failed for '{audio_path}', attempting PyAV fallback: {e}")
        y = load_audio_pyav(str(p), target_sr=sr)
        sample_rate = sr

    if y is None or len(y) == 0:
        return None
    return y, sample_rate


def compute_mel_spectrogram_core(
    audio_path: Optional[str],
    sr: int = 22050,
    n_mels: int = 128,
    n_fft: int = 2048,
    hop_length: int = 512
) -> Optional[np.ndarray]:
    """Pure Python core for computing dB-scaled Mel Spectrogram 2D matrix."""
    res = load_audio_signal(audio_path, sr=sr)
    if res is None:
        return None
    y, sample_rate = res

    try:
        # Compute mel power spectrogram
        s_mel = librosa.feature.melspectrogram(
            y=y,
            sr=sample_rate,
            n_fft=n_fft,
            hop_length=hop_length,
            n_mels=n_mels,
            fmin=0.0,
            fmax=8000.0
        )
        # Convert to decibels relative to peak
        s_db = librosa.power_to_db(s_mel, ref=np.max)
        return s_db.astype(np.float32)
    except Exception as e:
        logger.debug(f"Could not compute mel spectrogram for '{audio_path}': {e}")
        return None


def render_spectrogram_array_to_image(
    s_db: np.ndarray,
    colormap: str = "magma"
) -> Optional[Image.Image]:
    """Pure Python utility to render a 2D dB-scaled mel spectrogram array directly into a PIL Image."""
    if s_db is None or not isinstance(s_db, np.ndarray) or s_db.ndim != 2 or s_db.size == 0:
        return None
    try:
        min_val = float(s_db.min())
        max_val = float(s_db.max())
        diff = max_val - min_val
        norm_s = (s_db - min_val) / (diff if diff > 1e-6 else 1.0)

        # Invert vertical axis so lower frequencies are at the bottom
        norm_s = np.flipud(norm_s)

        # Apply colormap directly to numpy array (with graceful fallback for unknown colormaps)
        try:
            cmap = plt.get_cmap(colormap)
        except Exception:
            cmap = plt.get_cmap("magma")
        rgba_img = (cmap(norm_s) * 255).astype(np.uint8)

        # Convert to PIL Image
        pil_img = Image.fromarray(rgba_img).convert("RGB")
        target_w = max(512, pil_img.width) if pil_img.width < 256 else pil_img.width
        target_h = max(256, pil_img.height) if pil_img.height < 128 else pil_img.height
        if target_w != pil_img.width or target_h != pil_img.height:
            pil_img = pil_img.resize((target_w, target_h), resample=Image.Resampling.BILINEAR)
        return pil_img
    except Exception as e:
        logger.debug(f"Could not render spectrogram array to image: {e}")
        return None


def render_mel_spectrogram_image_core(
    audio_path: Optional[str],
    sr: int = 22050,
    n_mels: int = 128,
    n_fft: int = 2048,
    hop_length: int = 512,
    colormap: str = "magma"
) -> Optional[Image.Image]:
    """Pure Python core for rendering Mel Spectrogram as a colormapped PIL Image."""
    s_db = compute_mel_spectrogram_core(audio_path, sr=sr, n_mels=n_mels, n_fft=n_fft, hop_length=hop_length)
    if s_db is None or s_db.size == 0:
        return None
    return render_spectrogram_array_to_image(s_db, colormap=colormap)


@pxt.udf
def compute_mel_spectrogram(
    audio: Optional[pxt.Audio],
    sr: int = 22050,
    n_mels: int = 128,
    n_fft: int = 2048,
    hop_length: int = 512
) -> Optional[pxt.Array]:
    """Declarative Pixeltable UDF: Compute dB-scaled Mel Spectrogram 2D matrix."""
    return compute_mel_spectrogram_core(audio, sr=sr, n_mels=n_mels, n_fft=n_fft, hop_length=hop_length)


@pxt.udf
def render_mel_spectrogram_image(
    audio: Optional[pxt.Audio],
    sr: int = 22050,
    n_mels: int = 128,
    n_fft: int = 2048,
    hop_length: int = 512,
    colormap: str = "magma"
) -> Optional[pxt.Image]:
    """Declarative Pixeltable UDF: Render Mel Spectrogram as a colormapped PIL Image."""
    return render_mel_spectrogram_image_core(audio, sr=sr, n_mels=n_mels, n_fft=n_fft, hop_length=hop_length, colormap=colormap)


def attach_spectrogram_columns(
    domain: str,
    table_name: str,
    sr: int = 22050,
    n_mels: int = 128,
    n_fft: int = 2048,
    hop_length: int = 512,
    colormap: str = "magma"
) -> Dict[str, Any]:
    """
    Declaratively attach mel_spectrogram and mel_spectrogram_img computed columns to a Pixeltable table.
    """
    full_table_path = DBManager.resolve_table_path(domain, table_name)
    try:
        tbl = pxt.get_table(full_table_path)
    except Exception as e:
        return {"status": "error", "message": f"Table '{full_table_path}' not found: {e}"}

    cols = list(tbl.columns()) if callable(tbl.columns) else list(tbl._schema.keys())
    
    # Determine the audio source column
    audio_col = None
    if "audio" in cols:
        audio_col = tbl.audio
    elif "file_path" in cols:
        audio_col = tbl.file_path
    else:
        return {"status": "error", "message": f"Table '{full_table_path}' lacks an 'audio' or 'file_path' column."}

    columns_added = []
    
    # Add numerical array computed column
    if "mel_spectrogram" not in cols:
        tbl.add_computed_column(
            mel_spectrogram=compute_mel_spectrogram(
                audio_col, sr=sr, n_mels=n_mels, n_fft=n_fft, hop_length=hop_length
            ),
            if_exists="ignore"
        )
        columns_added.append("mel_spectrogram")

    # Add visual image computed column
    if "mel_spectrogram_img" not in cols:
        tbl.add_computed_column(
            mel_spectrogram_img=render_mel_spectrogram_image(
                audio_col, sr=sr, n_mels=n_mels, n_fft=n_fft, hop_length=hop_length, colormap=colormap
            ),
            if_exists="ignore"
        )
        columns_added.append("mel_spectrogram_img")

    return {
        "status": "success",
        "message": f"Successfully attached spectrogram columns to `{full_table_path}`.",
        "columns": columns_added or ["mel_spectrogram", "mel_spectrogram_img"],
        "table": full_table_path
    }


# -------------------------------------------------------------------------
# MFCC (Mel-Frequency Cepstral Coefficients)
# -------------------------------------------------------------------------
def compute_mfcc_core(
    audio_path: Optional[str],
    sr: int = 22050,
    n_mfcc: int = 20,
    n_fft: int = 2048,
    hop_length: int = 512
) -> Optional[np.ndarray]:
    """Pure Python core for computing Mel-Frequency Cepstral Coefficients (MFCCs)."""
    res = load_audio_signal(audio_path, sr=sr)
    if res is None:
        return None
    y, sample_rate = res
    try:
        mfcc = librosa.feature.mfcc(
            y=y,
            sr=sample_rate,
            n_mfcc=n_mfcc,
            n_fft=n_fft,
            hop_length=hop_length
        )
        return mfcc.astype(np.float32)
    except Exception as e:
        logger.debug(f"Could not compute MFCC for '{audio_path}': {e}")
        return None


def render_mfcc_image_core(
    audio_path: Optional[str],
    sr: int = 22050,
    n_mfcc: int = 20,
    n_fft: int = 2048,
    hop_length: int = 512,
    colormap: str = "plasma"
) -> Optional[Image.Image]:
    """Pure Python core for rendering MFCC as a colormapped PIL Image."""
    mfcc = compute_mfcc_core(audio_path, sr=sr, n_mfcc=n_mfcc, n_fft=n_fft, hop_length=hop_length)
    if mfcc is None or mfcc.size == 0:
        return None
    return render_spectrogram_array_to_image(mfcc, colormap=colormap)


@pxt.udf
def compute_mfcc(
    audio: Optional[pxt.Audio],
    sr: int = 22050,
    n_mfcc: int = 20,
    n_fft: int = 2048,
    hop_length: int = 512
) -> Optional[pxt.Array]:
    """Declarative Pixeltable UDF: Compute Mel-Frequency Cepstral Coefficients (MFCC) 2D matrix."""
    return compute_mfcc_core(audio, sr=sr, n_mfcc=n_mfcc, n_fft=n_fft, hop_length=hop_length)


@pxt.udf
def render_mfcc_image(
    audio: Optional[pxt.Audio],
    sr: int = 22050,
    n_mfcc: int = 20,
    n_fft: int = 2048,
    hop_length: int = 512,
    colormap: str = "plasma"
) -> Optional[pxt.Image]:
    """Declarative Pixeltable UDF: Render MFCC as a colormapped PIL Image."""
    return render_mfcc_image_core(audio, sr=sr, n_mfcc=n_mfcc, n_fft=n_fft, hop_length=hop_length, colormap=colormap)


def attach_mfcc_columns(
    domain: str,
    table_name: str,
    sr: int = 22050,
    n_mfcc: int = 20,
    n_fft: int = 2048,
    hop_length: int = 512,
    colormap: str = "plasma"
) -> Dict[str, Any]:
    """Declaratively attach mfcc and mfcc_img computed columns to a Pixeltable table."""
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
    if "mfcc" not in cols:
        tbl.add_computed_column(
            mfcc=compute_mfcc(
                audio_col, sr=sr, n_mfcc=n_mfcc, n_fft=n_fft, hop_length=hop_length
            ),
            if_exists="ignore"
        )
        columns_added.append("mfcc")

    if "mfcc_img" not in cols:
        tbl.add_computed_column(
            mfcc_img=render_mfcc_image(
                audio_col, sr=sr, n_mfcc=n_mfcc, n_fft=n_fft, hop_length=hop_length, colormap=colormap
            ),
            if_exists="ignore"
        )
        columns_added.append("mfcc_img")

    return {
        "status": "success",
        "message": f"Successfully attached MFCC columns to `{full_table_path}`.",
        "columns": columns_added or ["mfcc", "mfcc_img"],
        "table": full_table_path
    }


# -------------------------------------------------------------------------
# Chroma STFT (Pitch Classes)
# -------------------------------------------------------------------------
def compute_chroma_core(
    audio_path: Optional[str],
    sr: int = 22050,
    n_chroma: int = 12,
    n_fft: int = 2048,
    hop_length: int = 512
) -> Optional[np.ndarray]:
    """Pure Python core for computing Chroma STFT (12 semitone pitch classes)."""
    res = load_audio_signal(audio_path, sr=sr)
    if res is None:
        return None
    y, sample_rate = res
    try:
        chroma = librosa.feature.chroma_stft(
            y=y,
            sr=sample_rate,
            n_chroma=n_chroma,
            n_fft=n_fft,
            hop_length=hop_length
        )
        return chroma.astype(np.float32)
    except Exception as e:
        logger.debug(f"Could not compute Chroma STFT for '{audio_path}': {e}")
        return None


def render_chroma_image_core(
    audio_path: Optional[str],
    sr: int = 22050,
    n_chroma: int = 12,
    n_fft: int = 2048,
    hop_length: int = 512,
    colormap: str = "coolwarm"
) -> Optional[Image.Image]:
    """Pure Python core for rendering Chroma STFT as a colormapped PIL Image."""
    chroma = compute_chroma_core(audio_path, sr=sr, n_chroma=n_chroma, n_fft=n_fft, hop_length=hop_length)
    if chroma is None or chroma.size == 0:
        return None
    return render_spectrogram_array_to_image(chroma, colormap=colormap)


@pxt.udf
def compute_chroma(
    audio: Optional[pxt.Audio],
    sr: int = 22050,
    n_chroma: int = 12,
    n_fft: int = 2048,
    hop_length: int = 512
) -> Optional[pxt.Array]:
    """Declarative Pixeltable UDF: Compute Chroma STFT 2D matrix (pitch classes)."""
    return compute_chroma_core(audio, sr=sr, n_chroma=n_chroma, n_fft=n_fft, hop_length=hop_length)


@pxt.udf
def render_chroma_image(
    audio: Optional[pxt.Audio],
    sr: int = 22050,
    n_chroma: int = 12,
    n_fft: int = 2048,
    hop_length: int = 512,
    colormap: str = "coolwarm"
) -> Optional[pxt.Image]:
    """Declarative Pixeltable UDF: Render Chroma STFT as a colormapped PIL Image."""
    return render_chroma_image_core(audio, sr=sr, n_chroma=n_chroma, n_fft=n_fft, hop_length=hop_length, colormap=colormap)


def attach_chroma_columns(
    domain: str,
    table_name: str,
    sr: int = 22050,
    n_chroma: int = 12,
    n_fft: int = 2048,
    hop_length: int = 512,
    colormap: str = "coolwarm"
) -> Dict[str, Any]:
    """Declaratively attach chroma and chroma_img computed columns to a Pixeltable table."""
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
    if "chroma" not in cols:
        tbl.add_computed_column(
            chroma=compute_chroma(
                audio_col, sr=sr, n_chroma=n_chroma, n_fft=n_fft, hop_length=hop_length
            ),
            if_exists="ignore"
        )
        columns_added.append("chroma")

    if "chroma_img" not in cols:
        tbl.add_computed_column(
            chroma_img=render_chroma_image(
                audio_col, sr=sr, n_chroma=n_chroma, n_fft=n_fft, hop_length=hop_length, colormap=colormap
            ),
            if_exists="ignore"
        )
        columns_added.append("chroma_img")

    return {
        "status": "success",
        "message": f"Successfully attached Chroma columns to `{full_table_path}`.",
        "columns": columns_added or ["chroma", "chroma_img"],
        "table": full_table_path
    }


# -------------------------------------------------------------------------
# Audio & Noise Summary Statistics
# -------------------------------------------------------------------------
def compute_audio_stats_core(
    audio_path: Optional[str],
    sr: int = 22050,
    hop_length: int = 512
) -> Optional[Dict[str, Any]]:
    """Pure Python core for computing audio and noise summary metrics (RMS, ZCR, Centroid, Rolloff, Silence ratio)."""
    res = load_audio_signal(audio_path, sr=sr)
    if res is None:
        return None
    y, sample_rate = res
    try:
        duration = float(len(y) / sample_rate)
        rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
        zcr = librosa.feature.zero_crossing_rate(y=y, hop_length=hop_length)[0]
        cent = librosa.feature.spectral_centroid(y=y, sr=sample_rate, hop_length=hop_length)[0]
        rolloff = librosa.feature.spectral_rolloff(y=y, sr=sample_rate, hop_length=hop_length)[0]

        rms_max = float(np.max(rms)) if len(rms) > 0 else 0.0
        threshold = max(0.01, 0.05 * rms_max)
        silence_ratio = float(np.mean(rms < threshold)) if len(rms) > 0 else 0.0

        return {
            "duration_sec": round(duration, 3),
            "sample_rate": int(sample_rate),
            "rms_mean": round(float(np.mean(rms)), 4),
            "rms_std": round(float(np.std(rms)), 4),
            "zcr_mean": round(float(np.mean(zcr)), 4),
            "spectral_centroid_mean": round(float(np.mean(cent)), 1),
            "spectral_rolloff_mean": round(float(np.mean(rolloff)), 1),
            "silence_ratio": round(silence_ratio, 4)
        }
    except Exception as e:
        logger.debug(f"Could not compute audio stats for '{audio_path}': {e}")
        return None


@pxt.udf
def compute_audio_stats(
    audio: Optional[pxt.Audio],
    sr: int = 22050,
    hop_length: int = 512
) -> Optional[pxt.Json]:
    """Declarative Pixeltable UDF: Compute audio and noise summary statistics dictionary."""
    return compute_audio_stats_core(audio, sr=sr, hop_length=hop_length)


def attach_audio_stats_columns(
    domain: str,
    table_name: str,
    sr: int = 22050,
    hop_length: int = 512
) -> Dict[str, Any]:
    """Declaratively attach audio_stats computed column to a Pixeltable table."""
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
    if "audio_stats" not in cols:
        tbl.add_computed_column(
            audio_stats=compute_audio_stats(
                audio_col, sr=sr, hop_length=hop_length
            ),
            if_exists="ignore"
        )
        columns_added.append("audio_stats")

    return {
        "status": "success",
        "message": f"Successfully attached audio_stats column to `{full_table_path}`.",
        "columns": columns_added or ["audio_stats"],
        "table": full_table_path
    }
