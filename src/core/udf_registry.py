"""
UDF Registry & Prompt-Driven Declarative Execution
==================================================
Central registry for declarative Pixeltable UDFs callable via prompts or slash commands.
Provides metadata, parameter parsing, sample test evaluation, and declarative batch computed column attachment.
"""

import os
import re
from typing import Dict, Any, Optional, List, Callable, Tuple, Set, Union
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
    def match_all_prompts(cls, prompt: str) -> List[Tuple[UDFDefinition, Dict[str, Any]]]:
        """
        Check if a prompt invokes one or more registered UDFs via:
        1. Slash commands: e.g. `/mel_spectrogram hop_length=256 /chroma colormap=coolwarm`
        2. Natural language triggers: e.g. `mel_spectrograph and chroma for {file_name}`
        Returns a list of (UDFDefinition, parsed_kwargs) in order of appearance in prompt.
        """
        if not prompt or not prompt.strip():
            return []
        clean_p = prompt.strip()

        candidates = []
        for udf in cls._registry.values():
            triggers = set()
            # 1. Slash commands (/name or /alias)
            triggers.add(f"/{udf.name}")
            for a in udf.aliases:
                if a.startswith("/"):
                    triggers.add(a)

            # 2. Natural language triggers (name or aliases, with spaces or underscores)
            triggers.add(udf.name)
            triggers.add(udf.name.replace("_", " "))
            for a in udf.aliases:
                if not a.startswith("/"):
                    triggers.add(a)
                    triggers.add(a.replace(" ", "_"))
                    triggers.add(a.replace("_", " "))

            sorted_triggers = sorted(triggers, key=lambda x: len(x), reverse=True)

            for t in sorted_triggers:
                if t.startswith("/"):
                    pat = rf"(?<!\S){re.escape(t)}(?![\w/])"
                else:
                    pat = rf"(?<![\w/]){re.escape(t)}(?![\w/])"
                for m in re.finditer(pat, clean_p, re.IGNORECASE):
                    candidates.append((m.start(), m.end(), udf, t))

        # Sort candidate matches by start position ascending, then longest match descending
        candidates.sort(key=lambda c: (c[0], -(c[1] - c[0])))

        accepted = []
        seen_udfs = set()
        for start, end, udf, t in candidates:
            if udf.name in seen_udfs:
                continue
            # Check overlap with any already accepted match span
            overlap = False
            for a_start, a_end, _, _ in accepted:
                if start < a_end and end > a_start:
                    overlap = True
                    break
            if not overlap:
                accepted.append((start, end, udf, t))
                seen_udfs.add(udf.name)

        # Re-sort accepted matches by start index
        accepted.sort(key=lambda c: c[0])

        if not accepted:
            return []

        trailing_text = clean_p[accepted[-1][1]:].strip() if len(accepted) > 1 else ""
        is_any_slash = any(t.startswith("/") for _, _, _, t in accepted)

        results = []
        for i, (start, end, udf, t) in enumerate(accepted):
            next_start = accepted[i + 1][0] if i + 1 < len(accepted) else len(clean_p)
            segment = clean_p[end:next_start].strip()
            kwargs, explicit_keys = cls._parse_params(segment, udf.parameters, return_explicit=True)

            # In natural language mode (when no slash commands are involved), allow shared trailing
            # parameters (e.g. "mel_spectrogram and chroma with colormap=coolwarm") to populate
            # parameters that were not explicitly set in the UDF's local segment.
            # Slash commands are strictly scoped and never inherit trailing text.
            if not is_any_slash and trailing_text and segment != trailing_text:
                trailing_kwargs, trailing_explicit = cls._parse_params(trailing_text, udf.parameters, return_explicit=True)
                for k in trailing_explicit:
                    if k not in explicit_keys:
                        kwargs[k] = trailing_kwargs[k]

            results.append((udf, kwargs))

        return results

    @classmethod
    def match_all(cls, prompt: str) -> List[Tuple[UDFDefinition, Dict[str, Any]]]:
        """Alias for match_all_prompts."""
        return cls.match_all_prompts(prompt)

    @classmethod
    def match_prompt(cls, prompt: str) -> Optional[Tuple[UDFDefinition, Dict[str, Any]]]:
        """
        Check if a prompt invokes a registered UDF.
        Returns the first matched (UDFDefinition, parsed_kwargs) or None.
        """
        matches = cls.match_all_prompts(prompt)
        return matches[0] if matches else None

    @classmethod
    def _parse_params(
        cls,
        text: str,
        param_schema: Dict[str, Dict[str, Any]],
        return_explicit: bool = False
    ) -> Union[Dict[str, Any], Tuple[Dict[str, Any], Set[str]]]:
        """Extract typed parameters from text matching key=value, key: value, or schema defaults."""
        kwargs = {}
        for param, meta in param_schema.items():
            kwargs[param] = meta.get("default")

        explicit_keys: Set[str] = set()
        if not text:
            return (kwargs, explicit_keys) if return_explicit else kwargs

        # Match key=val or key: val or key="val" or key='val'
        pattern = r'(?:(\w+)\s*[:=]\s*(?:"([^"]*)"|\'([^\']*)\'|(\S+)))'
        matches = re.findall(pattern, text)
        for m in matches:
            k = m[0].lower()
            if k in param_schema:
                val_str = (m[1] or m[2] or m[3]).strip()
                if not m[1] and not m[2]:
                    val_str = val_str.rstrip(",);]")
                param_type = param_schema[k].get("type", str)
                try:
                    if param_type == int:
                        kwargs[k] = int(val_str)
                        explicit_keys.add(k)
                    elif param_type == float:
                        kwargs[k] = float(val_str)
                        explicit_keys.add(k)
                    elif param_type == bool:
                        kwargs[k] = val_str.lower() in ("true", "1", "yes")
                        explicit_keys.add(k)
                    else:
                        kwargs[k] = str(val_str)
                        explicit_keys.add(k)
                except (ValueError, TypeError):
                    pass

        return (kwargs, explicit_keys) if return_explicit else kwargs

    @classmethod
    def generate_markdown_help(cls) -> str:
        """Generate formatted Markdown documentation describing all registered UDFs, parameters, and invocation examples."""
        lines = [
            "### 📚 Registered Declarative UDFs & Audio DSP Suite",
            "",
            "The **Pipeline Tools UDF Registry** enables declarative execution of audio and signal processing functions directly in Pixeltable via prompt templates and slash commands. These functions run as native Pixeltable `@pxt.udf` computed columns with automatic database-level caching, zero token costs, and $O(1)$ memory streaming.",
            "",
            "| Function | Description | Primary Triggers / Aliases | Output Columns | Example Invocations |",
            "| :--- | :--- | :--- | :--- | :--- |"
        ]

        for udf in cls._registry.values():
            aliases_display = ", ".join(f"`{a}`" for a in udf.aliases[:4])
            if len(udf.aliases) > 4:
                aliases_display += f" *(+{len(udf.aliases) - 4} more)*"

            slash_ex = f"`/{udf.name}`"
            if udf.parameters:
                first_param, first_meta = next(iter(udf.parameters.items()))
                slash_ex = f"`/{udf.name} {first_param}={first_meta.get('default')}`"
            nl_ex = f'`"{udf.name} of {{file_name}}"`'
            ex_display = f"{slash_ex}<br>{nl_ex}"

            cols_map = {
                "mel_spectrogram": "`mel_spectrogram` (Array), `mel_spectrogram_img` (Image)",
                "mfcc": "`mfcc` (Array), `mfcc_img` (Image)",
                "chroma": "`chroma` (Array), `chroma_img` (Image)",
                "audio_stats": "`audio_stats` (JSON)"
            }
            out_cols = cols_map.get(udf.name, f"`{udf.name}`")

            lines.append(f"| **`{udf.name}`** | {udf.description} | {aliases_display} | {out_cols} | {ex_display} |")

        lines.extend([
            "",
            "---",
            "",
            "#### ⚙️ Detailed Parameter Reference & Schemas",
            ""
        ])

        for udf in cls._registry.values():
            lines.append(f"##### 🔹 `/{udf.name}` — {udf.description}")
            lines.append(f"- **Trigger Keywords:** {', '.join(f'`{a}`' for a in udf.aliases)}")
            if udf.parameters:
                lines.append("- **Parameters:**")
                for p_name, p_meta in udf.parameters.items():
                    p_type = p_meta.get("type", str).__name__
                    p_default = p_meta.get("default")
                    p_desc = p_meta.get("description", "")
                    lines.append(f"  - `{p_name}` (*{p_type}*, default: `{p_default}`): {p_desc}")
            else:
                lines.append("- **Parameters:** *None (runs with default settings)*")
            lines.append("")

        lines.extend([
            "---",
            "",
            "#### 💡 How to Invoke UDFs in Prompts",
            "1. **Slash Command Mode (Recommended)**: Start your prompt with `/function_name` followed by optional parameter overrides:",
            "   - `/mel_spectrogram hop_length=256 colormap=plasma`",
            "   - `/mfcc n_mfcc=20 colormap=plasma`",
            "   - `/chroma n_chroma=12 colormap=coolwarm`",
            "   - `/audio_stats sr=22050 hop_length=512`",
            "2. **Natural Language Trigger Mode**: Include the trigger phrase in your user prompt:",
            "   - `Compute the mel spectrogram for {file_name}`",
            "   - `Extract mfcc voice timbre for {file_name}`",
            "   - `Analyze pitch classes and chroma of {file_name}`",
            "   - `Calculate audio stats and noise floor for {file_name}`",
            "3. **Testing vs. Batching**:",
            "   - Click **🚀 Run Test on Sample Rows** to audition the UDF on 1–N sample records with inline graphical previews.",
            "   - Click **💾 Execute on Table & Save Columns** to declaratively attach computed columns across the entire dataset."
        ])

        return "\n".join(lines)


def _resolve_sample_audio_paths(domain: str, table_name: str, cols: List[str], sample_count: int) -> Dict[str, str]:
    """Helper to retrieve audio paths from table when 'file_path' is not in projected columns."""
    if "file_path" in cols:
        return {}
    try:
        import pixeltable as pxt
        from src.db.manager import DBManager
        full_table_path = DBManager.resolve_table_path(domain, table_name)
        tbl = pxt.get_table(full_table_path)
        tbl_cols = list(tbl.columns()) if callable(tbl.columns) else list(tbl._schema.keys())
        if "audio" in tbl_cols:
            fallback = {}
            aud_rows = tbl.select(tbl.audio).limit(sample_count).collect()
            for idx, ar in enumerate(aud_rows):
                v = ar.get("audio")
                if v is not None:
                    fallback[f"idx_{idx}"] = str(v)
            key_col = tbl.id if "id" in tbl_cols else tbl.file_name if "file_name" in tbl_cols else None
            if key_col is not None:
                key_name = "id" if "id" in tbl_cols else "file_name"
                aud_keyed = tbl.select(key_col, tbl.audio).limit(sample_count).collect()
                for ar in aud_keyed:
                    k = ar.get(key_name)
                    v = ar.get("audio")
                    if k is not None and v is not None:
                        fallback[str(k)] = str(v)
            return fallback
    except Exception:
        pass
    return {}


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

    audio_fallback = _resolve_sample_audio_paths(domain, table_name, cols, sample_count)

    for idx, row in enumerate(data):
        row_dict = dict(zip(cols, row))
        row_id = row_dict.get("id", str(idx + 1))
        file_name = row_dict.get("file_name", f"Row {idx + 1}")
        file_path = str(row_dict.get("file_path") or audio_fallback.get(str(row_id)) or audio_fallback.get(str(file_name)) or audio_fallback.get(f"idx_{idx}") or "")
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


# -------------------------------------------------------------------------
# UDF Definitions: MFCC (Mel-Frequency Cepstral Coefficients)
# -------------------------------------------------------------------------
def _eval_mfcc_sample(domain: str, table_name: str, sample_count: int = 2, **kwargs) -> Dict[str, Any]:
    """Dry-run MFCC on sample rows from table."""
    from src.db.manager import DBManager
    from src.audio.spectrogram import compute_mfcc_core, render_mfcc_image_core

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

    headers = ["Status", "Row ID", "File Name", "mfcc_shape", "mfcc_img"]
    rows = []

    sr = kwargs.get("sr", 22050)
    n_mfcc = kwargs.get("n_mfcc", 20)
    n_fft = kwargs.get("n_fft", 2048)
    hop_length = kwargs.get("hop_length", 512)
    colormap = kwargs.get("colormap", "plasma")

    audio_fallback = _resolve_sample_audio_paths(domain, table_name, cols, sample_count)

    for idx, row in enumerate(data):
        row_dict = dict(zip(cols, row))
        row_id = row_dict.get("id", str(idx + 1))
        file_name = row_dict.get("file_name", f"Row {idx + 1}")
        file_path = str(row_dict.get("file_path") or audio_fallback.get(str(row_id)) or audio_fallback.get(str(file_name)) or audio_fallback.get(f"idx_{idx}") or "")
        modality = str(row_dict.get("modality", "")).lower()

        mfcc_arr = None
        img_html = "—"
        shape_str = "None (Non-audio)"

        if modality == "audio" or Path(file_path).suffix.lower() in [".wav", ".mp3", ".ogg", ".m4a", ".flac", ".aac"]:
            mfcc_arr = compute_mfcc_core(file_path, sr=sr, n_mfcc=n_mfcc, n_fft=n_fft, hop_length=hop_length)
            if mfcc_arr is not None:
                shape_str = f"{list(mfcc_arr.shape)} ({colormap})"
                img = render_mfcc_image_core(file_path, sr=sr, n_mfcc=n_mfcc, n_fft=n_fft, hop_length=hop_length, colormap=colormap)
                if img is not None:
                    uri = DBManager.pil_to_base64_data_uri(img, size=(140, 60))
                    if uri:
                        img_html = f'<img src="{uri}" alt="mfcc" style="height:48px; max-width:140px; border-radius:4px; object-fit:contain; display:block; margin:auto;" />'

        rows.append(["🧪 UDF Sample Test", str(row_id), str(file_name), shape_str, img_html])

    return {
        "status": "success",
        "headers": headers,
        "datatypes": ["str", "str", "str", "str", "html"],
        "data": rows,
        "count": len(rows),
        "is_udf": True
    }


def _attach_mfcc_batch(domain: str, table_name: str, **kwargs) -> Dict[str, Any]:
    """Declaratively attach MFCC computed columns to table."""
    from src.audio.spectrogram import attach_mfcc_columns
    return attach_mfcc_columns(domain, table_name, **kwargs)


UDFRegistry.register(
    UDFDefinition(
        name="mfcc",
        description="Compute Mel-Frequency Cepstral Coefficients (MFCCs) for voice timbre and speaker recognition.",
        aliases=[
            "mfcc",
            "mel frequency cepstral coefficients",
            "vocal timbre",
            "speaker timbre",
            "/mfcc"
        ],
        parameters={
            "sr": {"type": int, "default": 22050, "description": "Sampling rate in Hz"},
            "n_mfcc": {"type": int, "default": 20, "description": "Number of MFCC coefficients"},
            "n_fft": {"type": int, "default": 2048, "description": "Length of FFT window"},
            "hop_length": {"type": int, "default": 512, "description": "Number of samples between successive frames"},
            "colormap": {"type": str, "default": "plasma", "description": "Matplotlib colormap name"}
        },
        attach_fn=_attach_mfcc_batch,
        sample_eval_fn=_eval_mfcc_sample
    )
)


# -------------------------------------------------------------------------
# UDF Definitions: Chroma STFT (Pitch Classes)
# -------------------------------------------------------------------------
def _eval_chroma_sample(domain: str, table_name: str, sample_count: int = 2, **kwargs) -> Dict[str, Any]:
    """Dry-run Chroma STFT on sample rows from table."""
    from src.db.manager import DBManager
    from src.audio.spectrogram import compute_chroma_core, render_chroma_image_core

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

    headers = ["Status", "Row ID", "File Name", "chroma_shape", "chroma_img"]
    rows = []

    sr = kwargs.get("sr", 22050)
    n_chroma = kwargs.get("n_chroma", 12)
    n_fft = kwargs.get("n_fft", 2048)
    hop_length = kwargs.get("hop_length", 512)
    colormap = kwargs.get("colormap", "coolwarm")

    audio_fallback = _resolve_sample_audio_paths(domain, table_name, cols, sample_count)

    for idx, row in enumerate(data):
        row_dict = dict(zip(cols, row))
        row_id = row_dict.get("id", str(idx + 1))
        file_name = row_dict.get("file_name", f"Row {idx + 1}")
        file_path = str(row_dict.get("file_path") or audio_fallback.get(str(row_id)) or audio_fallback.get(str(file_name)) or audio_fallback.get(f"idx_{idx}") or "")
        modality = str(row_dict.get("modality", "")).lower()

        chroma_arr = None
        img_html = "—"
        shape_str = "None (Non-audio)"

        if modality == "audio" or Path(file_path).suffix.lower() in [".wav", ".mp3", ".ogg", ".m4a", ".flac", ".aac"]:
            chroma_arr = compute_chroma_core(file_path, sr=sr, n_chroma=n_chroma, n_fft=n_fft, hop_length=hop_length)
            if chroma_arr is not None:
                shape_str = f"{list(chroma_arr.shape)} ({colormap})"
                img = render_chroma_image_core(file_path, sr=sr, n_chroma=n_chroma, n_fft=n_fft, hop_length=hop_length, colormap=colormap)
                if img is not None:
                    uri = DBManager.pil_to_base64_data_uri(img, size=(140, 60))
                    if uri:
                        img_html = f'<img src="{uri}" alt="chroma" style="height:48px; max-width:140px; border-radius:4px; object-fit:contain; display:block; margin:auto;" />'

        rows.append(["🧪 UDF Sample Test", str(row_id), str(file_name), shape_str, img_html])

    return {
        "status": "success",
        "headers": headers,
        "datatypes": ["str", "str", "str", "str", "html"],
        "data": rows,
        "count": len(rows),
        "is_udf": True
    }


def _attach_chroma_batch(domain: str, table_name: str, **kwargs) -> Dict[str, Any]:
    """Declaratively attach Chroma computed columns to table."""
    from src.audio.spectrogram import attach_chroma_columns
    return attach_chroma_columns(domain, table_name, **kwargs)


UDFRegistry.register(
    UDFDefinition(
        name="chroma",
        description="Compute Chroma STFT (12 semitone pitch classes) for harmonic, tonality, and musical pitch analysis.",
        aliases=[
            "chroma",
            "chroma stft",
            "chromagram",
            "pitch classes",
            "tonality",
            "/chroma"
        ],
        parameters={
            "sr": {"type": int, "default": 22050, "description": "Sampling rate in Hz"},
            "n_chroma": {"type": int, "default": 12, "description": "Number of chroma pitch classes"},
            "n_fft": {"type": int, "default": 2048, "description": "Length of FFT window"},
            "hop_length": {"type": int, "default": 512, "description": "Number of samples between successive frames"},
            "colormap": {"type": str, "default": "coolwarm", "description": "Matplotlib colormap name"}
        },
        attach_fn=_attach_chroma_batch,
        sample_eval_fn=_eval_chroma_sample
    )
)


# -------------------------------------------------------------------------
# UDF Definitions: Audio & Noise Summary Statistics
# -------------------------------------------------------------------------
def _eval_audio_stats_sample(domain: str, table_name: str, sample_count: int = 2, **kwargs) -> Dict[str, Any]:
    """Dry-run Audio & Noise summary stats on sample rows from table."""
    import json
    from src.db.manager import DBManager
    from src.audio.spectrogram import compute_audio_stats_core

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

    headers = ["Status", "Row ID", "File Name", "Duration (s)", "RMS Mean", "ZCR Mean", "Centroid (Hz)", "Silence Ratio", "Stats (JSON)"]
    rows = []

    sr = kwargs.get("sr", 22050)
    hop_length = kwargs.get("hop_length", 512)

    audio_fallback = _resolve_sample_audio_paths(domain, table_name, cols, sample_count)

    for idx, row in enumerate(data):
        row_dict = dict(zip(cols, row))
        row_id = row_dict.get("id", str(idx + 1))
        file_name = row_dict.get("file_name", f"Row {idx + 1}")
        file_path = str(row_dict.get("file_path") or audio_fallback.get(str(row_id)) or audio_fallback.get(str(file_name)) or audio_fallback.get(f"idx_{idx}") or "")
        modality = str(row_dict.get("modality", "")).lower()

        dur_s = "—"
        rms_s = "—"
        zcr_s = "—"
        cent_s = "—"
        sil_s = "—"
        stats_json = "None (Non-audio)"

        if modality == "audio" or Path(file_path).suffix.lower() in [".wav", ".mp3", ".ogg", ".m4a", ".flac", ".aac"]:
            stats = compute_audio_stats_core(file_path, sr=sr, hop_length=hop_length)
            if stats is not None:
                dur_s = str(stats.get("duration_sec", "—"))
                rms_s = str(stats.get("rms_mean", "—"))
                zcr_s = str(stats.get("zcr_mean", "—"))
                cent_s = str(stats.get("spectral_centroid_mean", "—"))
                sil_s = str(stats.get("silence_ratio", "—"))
                stats_json = json.dumps(stats, indent=2)

        rows.append(["🧪 UDF Sample Test", str(row_id), str(file_name), dur_s, rms_s, zcr_s, cent_s, sil_s, stats_json])

    return {
        "status": "success",
        "headers": headers,
        "datatypes": ["str", "str", "str", "str", "str", "str", "str", "str", "str"],
        "data": rows,
        "count": len(rows),
        "is_udf": True
    }


def _attach_audio_stats_batch(domain: str, table_name: str, **kwargs) -> Dict[str, Any]:
    """Declaratively attach Audio Stats computed column to table."""
    from src.audio.spectrogram import attach_audio_stats_columns
    return attach_audio_stats_columns(domain, table_name, **kwargs)


UDFRegistry.register(
    UDFDefinition(
        name="audio_stats",
        description="Compute audio and noise summary metrics (RMS energy, Zero Crossing Rate, Spectral Centroid, Rolloff, silence ratio, duration).",
        aliases=[
            "audio stats",
            "audio_stats",
            "audio statistics",
            "noise stats",
            "sound stats",
            "voice activity",
            "/audio_stats"
        ],
        parameters={
            "sr": {"type": int, "default": 22050, "description": "Sampling rate in Hz"},
            "hop_length": {"type": int, "default": 512, "description": "Number of samples between successive frames"}
        },
        attach_fn=_attach_audio_stats_batch,
        sample_eval_fn=_eval_audio_stats_sample
    )
)

