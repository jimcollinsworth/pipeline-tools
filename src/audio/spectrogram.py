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
from typing import Optional, Dict, Any
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


def compute_mel_spectrogram_core(
    audio_path: Optional[str],
    sr: int = 22050,
    n_mels: int = 128,
    n_fft: int = 2048,
    hop_length: int = 512
) -> Optional[np.ndarray]:
    """Pure Python core for computing dB-scaled Mel Spectrogram 2D matrix."""
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

        # Apply colormap directly to numpy array
        cmap = plt.get_cmap(colormap)
        rgba_img = (cmap(norm_s) * 255).astype(np.uint8)

        # Convert to PIL Image
        pil_img = Image.fromarray(rgba_img).convert("RGB")
        if pil_img.width < 256:
            pil_img = pil_img.resize((512, 256), resample=Image.Resampling.BILINEAR)
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
