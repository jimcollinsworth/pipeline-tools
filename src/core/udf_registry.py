"""
UDF Registry & Prompt-Driven Declarative Execution
==================================================
Central registry for declarative Pixeltable UDFs callable via prompts or slash commands.
Provides metadata, parameter parsing, sample test evaluation, and declarative batch computed column attachment.
"""

import os
import re
from typing import Dict, Any, Optional, List, Callable, Tuple
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class UDFDefinition:
    name: str
    description: str
    aliases: List[str]
    parameters: Dict[str, Dict[str, Any]]
    attach_fn: Callable[..., Dict[str, Any]]
    sample_eval_fn: Callable[..., Dict[str, Any]]


class UDFRegistry:
    """Registry and dispatcher for prompt-driven Pixeltable UDFs."""
    _registry: Dict[str, UDFDefinition] = {}

    @classmethod
    def register(cls, udf_def: UDFDefinition) -> None:
        cls._registry[udf_def.name] = udf_def

    @classmethod
    def get(cls, name: str) -> Optional[UDFDefinition]:
        return cls._registry.get(name)

    @classmethod
    def list_udfs(cls) -> List[UDFDefinition]:
        return list(cls._registry.values())

    @classmethod
    def match_prompt(cls, prompt: str) -> Optional[Tuple[UDFDefinition, Dict[str, Any]]]:
        """
        Check if a prompt invokes a registered UDF via:
        1. Slash command: e.g. `/mel_spectrogram hop_length=256 colormap=magma`
        2. Natural language trigger: e.g. `mel spectrogram of {file_name}`, `generate mel spectrogram`
        Returns (UDFDefinition, parsed_kwargs) or None.
        """
        if not prompt or not prompt.strip():
            return None
        clean_p = prompt.strip()
        lower_p = clean_p.lower()

        # Check all registered UDFs
        for udf in cls._registry.values():
            matched = False
            remaining_text = ""

            # 1. Slash command matching (/name or /alias)
            slash_cmd = f"/{udf.name}".lower()
            if lower_p.startswith(slash_cmd):
                matched = True
                remaining_text = clean_p[len(slash_cmd):].strip()
            else:
                for alias in udf.aliases:
                    alias_lower = alias.lower()
                    if alias_lower.startswith("/") and lower_p.startswith(alias_lower):
                        matched = True
                        remaining_text = clean_p[len(alias_lower):].strip()
                        break

            # 2. Natural language trigger matching
            if not matched:
                for alias in udf.aliases:
                    alias_lower = alias.lower()
                    if not alias_lower.startswith("/") and alias_lower in lower_p:
                        matched = True
                        remaining_text = clean_p
                        break

            if matched:
                parsed_kwargs = cls._parse_params(remaining_text, udf.parameters)
                return udf, parsed_kwargs

        return None

    @classmethod
    def _parse_params(cls, text: str, param_schema: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Extract typed parameters from text matching key=value, key: value, or schema defaults."""
        kwargs = {}
        for param, meta in param_schema.items():
            kwargs[param] = meta.get("default")

        if not text:
            return kwargs

        # Match key=val or key: val or key="val"
        pattern = r'(?:(\w+)\s*[:=]\s*(?:"([^"]*)"|\'([^\']*)\'|(\S+)))'
        matches = re.findall(pattern, text)
        for m in matches:
            k = m[0].lower()
            val_str = m[1] or m[2] or m[3]
            if k in param_schema:
                param_type = param_schema[k].get("type", str)
                try:
                    if param_type == int:
                        kwargs[k] = int(val_str)
                    elif param_type == float:
                        kwargs[k] = float(val_str)
                    elif param_type == bool:
                        kwargs[k] = val_str.lower() in ("true", "1", "yes")
                    else:
                        kwargs[k] = str(val_str)
                except (ValueError, TypeError):
                    pass
        return kwargs


# -------------------------------------------------------------------------
# Default UDF Definitions: Mel Spectrogram
# -------------------------------------------------------------------------
def _eval_mel_spectrogram_sample(domain: str, table_name: str, sample_count: int = 2, **kwargs) -> Dict[str, Any]:
    """Dry-run mel spectrogram on sample rows from table."""
    from src.db.manager import DBManager
    from src.audio.spectrogram import compute_mel_spectrogram_core, render_mel_spectrogram_image_core

    res = DBManager.get_table_data(domain, table_name, limit=sample_count, lightweight=False)
    cols = res.get("columns", [])
    data = res.get("data", [])

    if not data:
        return {
            "status": "error",
            "message": f"Table '{domain}.{table_name}' has no rows to test.",
            "headers": ["Error"],
            "data": [[f"Table '{domain}.{table_name}' is empty."]]
        }

    headers = ["Status", "Row ID", "File Name", "mel_spectrogram_shape", "mel_spectrogram_img"]
    rows = []

    sr = kwargs.get("sr", 22050)
    n_mels = kwargs.get("n_mels", 128)
    n_fft = kwargs.get("n_fft", 2048)
    hop_length = kwargs.get("hop_length", 512)
    colormap = kwargs.get("colormap", "magma")

    for idx, row in enumerate(data):
        row_dict = dict(zip(cols, row))
        row_id = row_dict.get("id", str(idx + 1))
        file_name = row_dict.get("file_name", f"Row {idx + 1}")
        file_path = str(row_dict.get("file_path", ""))
        modality = str(row_dict.get("modality", "")).lower()

        spec = None
        img_html = "—"
        shape_str = "None (Non-audio)"

        if modality == "audio" or Path(file_path).suffix.lower() in [".wav", ".mp3", ".ogg", ".m4a", ".flac", ".aac"]:
            spec = compute_mel_spectrogram_core(file_path, sr=sr, n_mels=n_mels, n_fft=n_fft, hop_length=hop_length)
            if spec is not None:
                shape_str = f"{list(spec.shape)} ({colormap})"
                img = render_mel_spectrogram_image_core(file_path, sr=sr, n_mels=n_mels, n_fft=n_fft, hop_length=hop_length, colormap=colormap)
                if img is not None:
                    uri = DBManager.pil_to_base64_data_uri(img, size=(140, 60))
                    if uri:
                        img_html = f'<img src="{uri}" alt="spectrogram" style="height:48px; max-width:140px; border-radius:4px; object-fit:contain; display:block; margin:auto;" />'

        rows.append(["🧪 UDF Sample Test", str(row_id), str(file_name), shape_str, img_html])

    return {
        "status": "success",
        "headers": headers,
        "datatypes": ["str", "str", "str", "str", "html"],
        "data": rows,
        "count": len(rows),
        "is_udf": True
    }


def _attach_mel_spectrogram_batch(domain: str, table_name: str, **kwargs) -> Dict[str, Any]:
    """Declaratively attach Mel Spectrogram computed columns to table."""
    from src.audio.spectrogram import attach_spectrogram_columns
    return attach_spectrogram_columns(domain, table_name, **kwargs)


UDFRegistry.register(
    UDFDefinition(
        name="mel_spectrogram",
        description="Compute dB-scaled Mel Spectrogram array and rendered preview image for audio files.",
        aliases=[
            "mel spectrogram",
            "mel spectrograph",
            "spectrogram",
            "spectrograph",
            "audio spectrogram",
            "audio spectrograph",
            "melspectrogram",
            "/mel_spectrogram",
            "/spectrogram",
            "/mel_spectrograph",
            "/spectrograph"
        ],
        parameters={
            "sr": {"type": int, "default": 22050, "description": "Sampling rate in Hz"},
            "n_mels": {"type": int, "default": 128, "description": "Number of Mel frequency bins"},
            "n_fft": {"type": int, "default": 2048, "description": "Length of FFT window"},
            "hop_length": {"type": int, "default": 512, "description": "Number of samples between successive frames"},
            "colormap": {"type": str, "default": "magma", "description": "Matplotlib colormap name"}
        },
        attach_fn=_attach_mel_spectrogram_batch,
        sample_eval_fn=_eval_mel_spectrogram_sample
    )
)
