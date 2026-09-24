"""
Segmenter Registry & Declarative Multimodal Chunking
=====================================================
Central registry for declarative Pixeltable segmenters and chunking iterators.
Supports prompt-driven slash commands (/split_pages, /split_paragraphs, /split_sentences,
/split_audio, /extract_frames) and one-click presets to create native Pixeltable views.
"""

import os
import re
from typing import Dict, Any, Optional, List, Callable, Tuple, Iterator
from dataclasses import dataclass, field
from pathlib import Path

try:
    import pixeltable as pxt
    from pixeltable.functions.string import StringChunk
except ImportError:
    pxt = None
    StringChunk = None


# -------------------------------------------------------------------------
# Custom / Fallback Module-Level Iterators
# -------------------------------------------------------------------------
if pxt is not None and StringChunk is not None:
    @pxt.iterator
    def sentence_splitter_udf(text: str) -> Iterator[StringChunk]:
        """Fast regex-based sentence splitter iterator (splits on sentence boundaries)."""
        if not text:
            return
        # Split on sentence-ending punctuation followed by whitespace
        for part in re.split(r'(?<=[.!?])\s+', str(text)):
            cleaned = part.strip()
            if cleaned:
                yield StringChunk(text=cleaned)

    @pxt.iterator
    def paragraph_splitter_udf(text: str) -> Iterator[StringChunk]:
        """Fast paragraph splitter iterator (splits on double newlines)."""
        if not text:
            return
        for part in re.split(r'\n\s*\n+', str(text)):
            cleaned = part.strip()
            if cleaned:
                yield StringChunk(text=cleaned)
else:
    sentence_splitter_udf = None
    paragraph_splitter_udf = None


@dataclass
class SegmenterDefinition:
    name: str
    description: str
    modality: str  # 'document', 'text', 'audio', 'video'
    aliases: List[str]
    parameters: Dict[str, Dict[str, Any]]
    create_iterator_fn: Callable[..., Any]
    preview_fn: Callable[..., Dict[str, Any]]


class SegmenterRegistry:
    """Registry and execution engine for declarative Pixeltable segmenters."""
    _registry: Dict[str, SegmenterDefinition] = {}

    @classmethod
    def register(cls, seg_def: SegmenterDefinition) -> None:
        cls._registry[seg_def.name] = seg_def

    @classmethod
    def get(cls, name: str) -> Optional[SegmenterDefinition]:
        return cls._registry.get(name)

    @classmethod
    def list_segmenters(cls) -> List[SegmenterDefinition]:
        return list(cls._registry.values())

    @classmethod
    def match_prompt(cls, prompt: str) -> Optional[Tuple[SegmenterDefinition, Dict[str, Any]]]:
        """
        Match a prompt against registered segmenters via:
        1. Slash command: e.g. `/split_audio duration=15.0` or `/split_paragraphs`
        2. Natural language trigger: e.g. `split into pages`, `extract video frames`
        Returns (SegmenterDefinition, parsed_kwargs) or None.
        """
        if not prompt or not prompt.strip():
            return None
        clean_p = prompt.strip()
        lower_p = clean_p.lower()

        for seg in cls._registry.values():
            matched = False
            remaining_text = ""

            # 1. Slash command matching (/name or /alias)
            slash_cmd = f"/{seg.name}".lower()
            if lower_p.startswith(slash_cmd):
                matched = True
                remaining_text = clean_p[len(slash_cmd):].strip()
            else:
                for alias in seg.aliases:
                    alias_lower = alias.lower()
                    if alias_lower.startswith("/") and lower_p.startswith(alias_lower):
                        matched = True
                        remaining_text = clean_p[len(alias_lower):].strip()
                        break

            # 2. Natural language trigger matching
            if not matched:
                for alias in seg.aliases:
                    alias_lower = alias.lower()
                    if not alias_lower.startswith("/") and alias_lower in lower_p:
                        matched = True
                        remaining_text = clean_p
                        break

            if matched:
                parsed_kwargs = cls._parse_params(remaining_text, seg.parameters)
                return seg, parsed_kwargs

        return None

    @classmethod
    def _parse_params(cls, text: str, param_schema: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Extract typed parameters from text matching key=value, key: value, or schema defaults."""
        kwargs = {}
        for param, meta in param_schema.items():
            kwargs[param] = meta.get("default")

        if not text:
            return kwargs

        # Match key=val or key: val or key="val" or key='val'
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

    @classmethod
    def preview_segmentation(
        cls,
        domain: str,
        table_name: str,
        segmenter_name_or_prompt: str,
        sample_count: int = 2,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute dry-run segmentation preview on sample rows from table.
        Accepts either a segmenter name ('split_pages') or a prompt ('/split_pages').
        """
        match = cls.match_prompt(segmenter_name_or_prompt)
        if match:
            seg_def, prompt_kwargs = match
            merged_kwargs = {**prompt_kwargs, **kwargs}
        else:
            seg_def = cls.get(segmenter_name_or_prompt)
            merged_kwargs = kwargs

        if not seg_def:
            return {
                "status": "error",
                "message": f"Unknown segmenter or unrecognized command: '{segmenter_name_or_prompt}'",
                "headers": ["Error"],
                "datatypes": ["str"],
                "data": [[f"Segmenter '{segmenter_name_or_prompt}' not found."]],
                "count": 0
            }

        return seg_def.preview_fn(domain, table_name, sample_count=sample_count, **merged_kwargs)

    @classmethod
    def create_segmented_view(
        cls,
        domain: str,
        source_table: str,
        view_name: str,
        segmenter_name_or_prompt: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Declaratively create a native Pixeltable view using the registered segmenter iterator.
        """
        if not pxt:
            return {"status": "error", "message": "Pixeltable is not installed or available."}

        match = cls.match_prompt(segmenter_name_or_prompt)
        if match:
            seg_def, prompt_kwargs = match
            merged_kwargs = {**prompt_kwargs, **kwargs}
        else:
            seg_def = cls.get(segmenter_name_or_prompt)
            merged_kwargs = kwargs

        if not seg_def:
            return {"status": "error", "message": f"Unknown segmenter: '{segmenter_name_or_prompt}'"}

        from src.db.manager import DBManager
        source_path = DBManager.resolve_table_path(domain, source_table)
        view_path = DBManager.resolve_table_path(domain, view_name)

        try:
            t = pxt.get_table(source_path)
        except Exception as e:
            return {"status": "error", "message": f"Could not find source table '{source_path}': {e}"}

        try:
            iterator = seg_def.create_iterator_fn(t, **merged_kwargs)
            view = pxt.create_view(view_path, t, iterator=iterator, if_exists="replace")
            view_cols = [str(c) for c in view.columns()]
            total_rows = view.count()
            return {
                "status": "success",
                "message": f"Successfully created segmented view '{view_path}' ({total_rows} rows).",
                "domain": domain,
                "view_name": view_name,
                "view_path": view_path,
                "source_table": source_table,
                "segmenter": seg_def.name,
                "columns": view_cols,
                "count": total_rows
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to create segmented view '{view_path}' with {seg_def.name}: {e}"
            }

    @classmethod
    def generate_markdown_help(cls) -> str:
        """Generate formatted Markdown documentation describing all registered segmenters."""
        lines = [
            "### ✂️ Registered Declarative Segmenters & Iterators",
            "",
            "The **Pipeline Tools Segmenter Registry** enables declarative sub-row chunking of documents, text, audio, and video directly into native Pixeltable views. Views store zero duplicate data, maintain automatic parent lineage, and automatically chunk newly ingested rows.",
            "",
            "| Segmenter | Modality | Description | Primary Triggers / Aliases | Example Invocations |",
            "| :--- | :--- | :--- | :--- | :--- |"
        ]

        for seg in cls._registry.values():
            aliases_display = ", ".join(f"`{a}`" for a in seg.aliases[:4])
            if len(seg.aliases) > 4:
                aliases_display += f" *(+{len(seg.aliases) - 4} more)*"

            slash_ex = f"`/{seg.name}`"
            if seg.parameters:
                first_param, first_meta = next(iter(seg.parameters.items()))
                slash_ex = f"`/{seg.name} {first_param}={first_meta.get('default')}`"
            nl_ex = f'`"{seg.aliases[1] if len(seg.aliases) > 1 else seg.name}"`'
            ex_display = f"{slash_ex}<br>{nl_ex}"

            lines.append(f"| **`{seg.name}`** | `{seg.modality}` | {seg.description} | {aliases_display} | {ex_display} |")

        lines.extend([
            "",
            "---",
            "",
            "#### ⚙️ Detailed Parameter Reference & Schemas",
            ""
        ])

        for seg in cls._registry.values():
            lines.append(f"##### 🔹 `/{seg.name}` — {seg.description}")
            lines.append(f"- **Modality:** `{seg.modality}`")
            lines.append(f"- **Aliases:** {', '.join(f'`{a}`' for a in seg.aliases)}")
            if seg.parameters:
                lines.append("- **Parameters:**")
                for p_name, p_meta in seg.parameters.items():
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
            "#### 💡 How to Use Segmentation in Pipeline Tools",
            "1. **Select Source Table**: Choose any domain and table containing documents, text, audio, or video.",
            "2. **Choose or Prompt Segmenter**:",
            "   - Click one of the quick preset buttons (`📄 Split Pages`, `📝 Split Paragraphs`, `🔤 Split Sentences`, `🎙️ Audio Segments`, `🎬 Video Frames`).",
            "   - Or type a custom slash command: `/split_audio duration=15.0 overlap=2.0` or `/extract_frames fps=0.5`.",
            "3. **🔬 Preview Segments**: Click Preview to inspect the sub-row chunks generated from sample rows without writing to the database.",
            "4. **✂️ Create Segmented View**: Click Create Segmented View to build a permanent, live Pixeltable view ready for Data Enhancement prompts."
        ])

        return "\n".join(lines)


# -------------------------------------------------------------------------
# Segmenter 1: Split Pages (PDF / Documents)
# -------------------------------------------------------------------------
def _create_split_pages_iterator(t, **kwargs):
    from pixeltable.functions.document import document_splitter
    col_name = kwargs.get("column", "doc")
    target_col = getattr(t, col_name, None)
    if target_col is None:
        for cand in ["doc", "document", "pdf"]:
            if hasattr(t, cand):
                target_col = getattr(t, cand)
                break
    if target_col is None:
        raise ValueError(f"Table does not have a document column (expected '{col_name}').")

    elements_val = kwargs.get("elements", "text")
    if isinstance(elements_val, str):
        elements = [e.strip() for e in elements_val.split(",") if e.strip()]
    else:
        elements = list(elements_val) if elements_val else ["text"]
    metadata = str(kwargs.get("metadata", "page"))
    image_dpi = int(kwargs.get("image_dpi", 300))
    return document_splitter(target_col, separators="page", elements=elements, metadata=metadata, image_dpi=image_dpi)


def _preview_split_pages(domain: str, table_name: str, sample_count: int = 2, **kwargs) -> Dict[str, Any]:
    from src.db.manager import DBManager
    res = DBManager.get_table_data(domain, table_name, limit=sample_count, lightweight=False)
    cols = res.get("columns", [])
    data = res.get("data", [])

    if not data:
        return {
            "status": "error",
            "message": f"Table '{domain}.{table_name}' has no rows to preview.",
            "headers": ["Status", "Message"],
            "datatypes": ["str", "str"],
            "data": [["Error", f"Table '{domain}.{table_name}' is empty."]],
            "count": 0
        }

    headers = ["Preview Status", "Parent Row ID", "File Name", "Page Number", "Character Count", "Page Snippet"]
    datatypes = ["str", "str", "str", "str", "str", "str"]
    rows = []

    for idx, r in enumerate(data):
        row_dict = dict(zip(cols, r))
        row_id = str(row_dict.get("id", idx + 1))
        file_name = str(row_dict.get("file_name", f"Row {idx + 1}"))
        file_path = str(row_dict.get("file_path", ""))
        content = str(row_dict.get("content", ""))

        pages_found = 0
        if file_path and Path(file_path).suffix.lower() == ".pdf" and Path(file_path).is_file():
            try:
                import pypdfium2 as pdfium
                with pdfium.PdfDocument(file_path) as pdf:
                    for page_idx in range(len(pdf)):
                        page = pdf.get_page(page_idx)
                        try:
                            textpage = page.get_textpage()
                            try:
                                page_text = textpage.get_text_range().strip()
                                char_count = str(len(page_text))
                                snippet = (page_text[:140] + "...") if len(page_text) > 140 else (page_text or "[Empty Page]")
                                rows.append(["🔬 Page Preview", row_id, file_name, f"Page {page_idx + 1}", char_count, snippet])
                                pages_found += 1
                            finally:
                                textpage.close()
                        finally:
                            page.close()
            except Exception:
                pass

        if pages_found == 0:
            # Fallback for non-PDF or empty text: show single page preview
            char_count = str(len(content))
            snippet = (content[:140] + "...") if len(content) > 140 else (content or "[No text content]")
            rows.append(["🔬 Page Preview", row_id, file_name, "Page 1", char_count, snippet])

    return {
        "status": "success",
        "message": f"Previewed {len(rows)} page segment(s) from {len(data)} source row(s).",
        "headers": headers,
        "datatypes": datatypes,
        "data": rows,
        "count": len(rows)
    }


SegmenterRegistry.register(
    SegmenterDefinition(
        name="split_pages",
        description="Split PDF and document files into one row per page with page numbers and text.",
        modality="document",
        aliases=[
            "/split_pages",
            "split pages",
            "split_pages",
            "pages",
            "page splitter",
            "split pdf pages",
            "pdf pages"
        ],
        parameters={
            "metadata": {"type": str, "default": "page", "description": "Metadata fields to include ('page', 'title')"},
            "elements": {"type": str, "default": "text", "description": "Elements to extract: 'text' or 'text,image'"},
            "image_dpi": {"type": int, "default": 300, "description": "DPI for extracted page images (PDF only)"}
        },
        create_iterator_fn=_create_split_pages_iterator,
        preview_fn=_preview_split_pages
    )
)


# -------------------------------------------------------------------------
# Segmenter 2: Split Paragraphs (Documents / Text)
# -------------------------------------------------------------------------
def _create_split_paragraphs_iterator(t, **kwargs):
    col_target = kwargs.get("column", "auto").lower()
    if col_target == "doc":
        from pixeltable.functions.document import document_splitter
        target_col = getattr(t, "doc", None)
        if target_col is None:
            raise ValueError("Table does not have a 'doc' column.")
        return document_splitter(target_col, separators="paragraph")
    elif col_target == "content":
        target_col = getattr(t, "content", getattr(t, "text", None))
        if target_col is None:
            raise ValueError("Table does not have a 'content' or 'text' column.")
        if paragraph_splitter_udf is not None:
            return paragraph_splitter_udf(target_col)
        from pixeltable.functions.document import document_splitter
        return document_splitter(target_col, separators="paragraph")
    else:
        # 'auto': prefer t.content or t.text if available, else t.doc
        target_col = getattr(t, "content", getattr(t, "text", None))
        if target_col is not None and paragraph_splitter_udf is not None:
            return paragraph_splitter_udf(target_col)
        if hasattr(t, "doc"):
            from pixeltable.functions.document import document_splitter
            return document_splitter(t.doc, separators="paragraph")
        if target_col is not None:
            if paragraph_splitter_udf is not None:
                return paragraph_splitter_udf(target_col)
        raise ValueError("Table must contain either 'content', 'text', or 'doc' column for paragraph splitting.")


def _preview_split_paragraphs(domain: str, table_name: str, sample_count: int = 2, **kwargs) -> Dict[str, Any]:
    from src.db.manager import DBManager
    res = DBManager.get_table_data(domain, table_name, limit=sample_count, lightweight=False)
    cols = res.get("columns", [])
    data = res.get("data", [])

    if not data:
        return {
            "status": "error",
            "message": f"Table '{domain}.{table_name}' has no rows to preview.",
            "headers": ["Status", "Message"],
            "datatypes": ["str", "str"],
            "data": [["Error", f"Table '{domain}.{table_name}' is empty."]],
            "count": 0
        }

    headers = ["Preview Status", "Parent Row ID", "File Name", "Paragraph #", "Character Count", "Paragraph Snippet"]
    datatypes = ["str", "str", "str", "str", "str", "str"]
    rows = []

    for idx, r in enumerate(data):
        row_dict = dict(zip(cols, r))
        row_id = str(row_dict.get("id", idx + 1))
        file_name = str(row_dict.get("file_name", f"Row {idx + 1}"))
        content = str(row_dict.get("content", ""))

        paras = [p.strip() for p in re.split(r'\n\s*\n+', content) if p.strip()]
        if not paras:
            paras = [content.strip() or "[Empty Content]"]

        for p_idx, p_text in enumerate(paras[:10]):  # Cap sample preview at 10 paragraphs per row
            char_count = str(len(p_text))
            snippet = (p_text[:140] + "...") if len(p_text) > 140 else p_text
            rows.append(["🔬 Para Preview", row_id, file_name, f"Para {p_idx + 1}", char_count, snippet])

    return {
        "status": "success",
        "message": f"Previewed {len(rows)} paragraph segment(s) from {len(data)} source row(s).",
        "headers": headers,
        "datatypes": datatypes,
        "data": rows,
        "count": len(rows)
    }


SegmenterRegistry.register(
    SegmenterDefinition(
        name="split_paragraphs",
        description="Split documents or text content into one row per paragraph.",
        modality="text",
        aliases=[
            "/split_paragraphs",
            "split paragraphs",
            "split_paragraphs",
            "paragraphs",
            "paragraph splitter",
            "split into paragraphs",
            "paragraphs splitter"
        ],
        parameters={
            "column": {"type": str, "default": "auto", "description": "Target column ('doc', 'content', or 'auto')"}
        },
        create_iterator_fn=_create_split_paragraphs_iterator,
        preview_fn=_preview_split_paragraphs
    )
)


# -------------------------------------------------------------------------
# Segmenter 3: Split Sentences (Text / Documents)
# -------------------------------------------------------------------------
def _create_split_sentences_iterator(t, **kwargs):
    col_name = kwargs.get("column", "content")
    target_col = getattr(t, col_name, getattr(t, "content", getattr(t, "text", None)))
    if target_col is None:
        raise ValueError(f"Table does not have a text column ('{col_name}').")

    # Prefer native string_splitter if spacy is available, else fallback to sentence_splitter_udf
    try:
        import spacy
        from pixeltable.functions.string import string_splitter
        return string_splitter(target_col, separators="sentence")
    except Exception:
        if sentence_splitter_udf is not None:
            return sentence_splitter_udf(target_col)
        from pixeltable.functions.string import string_splitter
        return string_splitter(target_col, separators="sentence")


def _preview_split_sentences(domain: str, table_name: str, sample_count: int = 2, **kwargs) -> Dict[str, Any]:
    from src.db.manager import DBManager
    res = DBManager.get_table_data(domain, table_name, limit=sample_count, lightweight=False)
    cols = res.get("columns", [])
    data = res.get("data", [])

    if not data:
        return {
            "status": "error",
            "message": f"Table '{domain}.{table_name}' has no rows to preview.",
            "headers": ["Status", "Message"],
            "datatypes": ["str", "str"],
            "data": [["Error", f"Table '{domain}.{table_name}' is empty."]],
            "count": 0
        }

    headers = ["Preview Status", "Parent Row ID", "File Name", "Sentence #", "Character Count", "Sentence Text"]
    datatypes = ["str", "str", "str", "str", "str", "str"]
    rows = []

    for idx, r in enumerate(data):
        row_dict = dict(zip(cols, r))
        row_id = str(row_dict.get("id", idx + 1))
        file_name = str(row_dict.get("file_name", f"Row {idx + 1}"))
        content = str(row_dict.get("content", ""))

        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', content) if s.strip()]
        if not sentences:
            sentences = [content.strip() or "[Empty Content]"]

        for s_idx, s_text in enumerate(sentences[:15]):  # Cap preview at 15 sentences per row
            char_count = str(len(s_text))
            rows.append(["🔬 Sent Preview", row_id, file_name, f"Sent {s_idx + 1}", char_count, s_text])

    return {
        "status": "success",
        "message": f"Previewed {len(rows)} sentence segment(s) from {len(data)} source row(s).",
        "headers": headers,
        "datatypes": datatypes,
        "data": rows,
        "count": len(rows)
    }


SegmenterRegistry.register(
    SegmenterDefinition(
        name="split_sentences",
        description="Split text content into one row per sentence.",
        modality="text",
        aliases=[
            "/split_sentences",
            "split sentences",
            "split_sentences",
            "sentences",
            "sentence splitter",
            "split into sentences"
        ],
        parameters={
            "column": {"type": str, "default": "content", "description": "Target text column (defaults to 'content')"}
        },
        create_iterator_fn=_create_split_sentences_iterator,
        preview_fn=_preview_split_sentences
    )
)


# -------------------------------------------------------------------------
# Segmenter 4: Split Audio (Temporal Slicing)
# -------------------------------------------------------------------------
def _create_split_audio_iterator(t, **kwargs):
    from pixeltable.functions.audio import audio_splitter
    col_name = kwargs.get("column", "audio")
    target_col = getattr(t, col_name, None)
    if target_col is None:
        for cand in ["audio", "sound"]:
            if hasattr(t, cand):
                target_col = getattr(t, cand)
                break
    if target_col is None:
        raise ValueError(f"Table does not have an audio column (expected '{col_name}').")

    duration = float(kwargs.get("duration", 10.0))
    overlap = float(kwargs.get("overlap", 0.0))
    min_silence = kwargs.get("min_silence_len", 0.3)
    if min_silence is not None:
        try:
            min_silence = float(min_silence)
            if min_silence <= 0:
                min_silence = None
        except (ValueError, TypeError):
            min_silence = None
    trim_silence = bool(kwargs.get("trim_leading_silence", True))
    silence_thresh = float(kwargs.get("silence_thresh", -40.0))
    return audio_splitter(
        target_col,
        duration=duration,
        overlap=overlap,
        min_silence_len=min_silence,
        silence_thresh=silence_thresh,
        trim_leading_silence=trim_silence
    )


def _preview_split_audio(domain: str, table_name: str, sample_count: int = 2, **kwargs) -> Dict[str, Any]:
    from src.db.manager import DBManager
    res = DBManager.get_table_data(domain, table_name, limit=sample_count, lightweight=False)
    cols = res.get("columns", [])
    data = res.get("data", [])

    if not data:
        return {
            "status": "error",
            "message": f"Table '{domain}.{table_name}' has no rows to preview.",
            "headers": ["Status", "Message"],
            "datatypes": ["str", "str"],
            "data": [["Error", f"Table '{domain}.{table_name}' is empty."]],
            "count": 0
        }

    duration_param = float(kwargs.get("duration", 10.0))
    overlap_param = float(kwargs.get("overlap", 0.0))
    step = max(0.5, duration_param - overlap_param)

    headers = ["Preview Status", "Parent Row ID", "File Name", "Segment #", "Time Window", "Duration", "Details"]
    datatypes = ["str", "str", "str", "str", "str", "str", "str"]
    rows = []

    for idx, r in enumerate(data):
        row_dict = dict(zip(cols, r))
        row_id = str(row_dict.get("id", idx + 1))
        file_name = str(row_dict.get("file_name", f"Row {idx + 1}"))
        file_path = str(row_dict.get("file_path", ""))
        modality = str(row_dict.get("modality", "")).lower()

        audio_dur = None
        if modality == "audio" or Path(file_path).suffix.lower() in [".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac"]:
            if Path(file_path).is_file():
                try:
                    import soundfile as sf
                    info = sf.info(file_path)
                    audio_dur = info.duration
                except Exception:
                    pass

        if audio_dur is None:
            audio_dur = 30.0  # Synthetic fallback duration for preview if unreadable

        curr_start = 0.0
        seg_idx = 0
        while curr_start < audio_dur:
            curr_end = min(curr_start + duration_param, audio_dur)
            seg_len = curr_end - curr_start
            window_str = f"{curr_start:.2f}s – {curr_end:.2f}s"
            rows.append([
                "🔬 Audio Preview",
                row_id,
                file_name,
                f"Seg {seg_idx + 1}",
                window_str,
                f"{seg_len:.2f}s",
                f"Slice of {audio_dur:.2f}s total"
            ])
            curr_start += step
            seg_idx += 1
            if seg_idx >= 15:  # Cap preview at 15 segments per audio file
                break

    return {
        "status": "success",
        "message": f"Previewed {len(rows)} audio segment(s) from {len(data)} source row(s).",
        "headers": headers,
        "datatypes": datatypes,
        "data": rows,
        "count": len(rows)
    }


SegmenterRegistry.register(
    SegmenterDefinition(
        name="split_audio",
        description="Split audio files into temporal slices (e.g. 10s chunks) with start/end timestamps.",
        modality="audio",
        aliases=[
            "/split_audio",
            "split audio",
            "split_audio",
            "audio segments",
            "slice audio",
            "chunk audio",
            "audio splitter"
        ],
        parameters={
            "duration": {"type": float, "default": 10.0, "description": "Chunk duration in seconds"},
            "overlap": {"type": float, "default": 0.0, "description": "Overlap between consecutive chunks in seconds"},
            "min_silence_len": {"type": float, "default": 0.3, "description": "Minimum silence duration in seconds for cuts (0 to disable)"},
            "silence_thresh": {"type": float, "default": -40.0, "description": "Silence threshold in dBFS"},
            "trim_leading_silence": {"type": bool, "default": True, "description": "Trim leading silence in segments"}
        },
        create_iterator_fn=_create_split_audio_iterator,
        preview_fn=_preview_split_audio
    )
)


# -------------------------------------------------------------------------
# Segmenter 5: Extract Frames (Video)
# -------------------------------------------------------------------------
def _create_extract_frames_iterator(t, **kwargs):
    from pixeltable.functions.video import frame_iterator
    col_name = kwargs.get("column", "video")
    target_col = getattr(t, col_name, None)
    if target_col is None:
        for cand in ["video", "clip"]:
            if hasattr(t, cand):
                target_col = getattr(t, cand)
                break
    if target_col is None:
        raise ValueError(f"Table does not have a video column (expected '{col_name}').")

    keyframes_only = bool(kwargs.get("keyframes_only", False))
    num_frames = kwargs.get("num_frames", 0)
    if num_frames:
        try:
            num_frames = int(num_frames)
            if num_frames <= 0:
                num_frames = None
        except (ValueError, TypeError):
            num_frames = None
    else:
        num_frames = None

    fps = kwargs.get("fps", 1.0)
    if fps is not None and not num_frames and not keyframes_only:
        fps = float(fps)
    else:
        fps = None

    return frame_iterator(target_col, fps=fps, num_frames=num_frames, keyframes_only=keyframes_only)


def _preview_extract_frames(domain: str, table_name: str, sample_count: int = 2, **kwargs) -> Dict[str, Any]:
    from src.db.manager import DBManager
    res = DBManager.get_table_data(domain, table_name, limit=sample_count, lightweight=False)
    cols = res.get("columns", [])
    data = res.get("data", [])

    if not data:
        return {
            "status": "error",
            "message": f"Table '{domain}.{table_name}' has no rows to preview.",
            "headers": ["Status", "Message"],
            "datatypes": ["str", "str"],
            "data": [["Error", f"Table '{domain}.{table_name}' is empty."]],
            "count": 0
        }

    fps_param = float(kwargs.get("fps", 1.0))
    headers = ["Preview Status", "Parent Row ID", "File Name", "Frame #", "Timestamp", "Frame Rate", "Details"]
    datatypes = ["str", "str", "str", "str", "str", "str", "str"]
    rows = []

    for idx, r in enumerate(data):
        row_dict = dict(zip(cols, r))
        row_id = str(row_dict.get("id", idx + 1))
        file_name = str(row_dict.get("file_name", f"Row {idx + 1}"))
        file_path = str(row_dict.get("file_path", ""))
        modality = str(row_dict.get("modality", "")).lower()

        video_dur = None
        if modality == "video" or Path(file_path).suffix.lower() in [".mp4", ".mov", ".avi", ".mkv"]:
            if Path(file_path).is_file():
                try:
                    import av
                    container = av.open(file_path)
                    video_dur = float(container.duration / av.time_base)
                    container.close()
                except Exception:
                    pass

        if video_dur is None:
            video_dur = 10.0  # Synthetic fallback duration for preview if unreadable

        interval = 1.0 / max(0.1, fps_param)
        curr_t = 0.0
        frame_idx = 0
        while curr_t < video_dur:
            rows.append([
                "🔬 Frame Preview",
                row_id,
                file_name,
                f"Frame {frame_idx + 1}",
                f"t = {curr_t:.2f}s",
                f"{fps_param} fps",
                f"Extracted image at {curr_t:.2f}s"
            ])
            curr_t += interval
            frame_idx += 1
            if frame_idx >= 15:  # Cap preview at 15 frames per video
                break

    return {
        "status": "success",
        "message": f"Previewed {len(rows)} video frame(s) from {len(data)} source row(s).",
        "headers": headers,
        "datatypes": datatypes,
        "data": rows,
        "count": len(rows)
    }


SegmenterRegistry.register(
    SegmenterDefinition(
        name="extract_frames",
        description="Extract video frames at a fixed frame rate (fps) or keyframe intervals as image rows.",
        modality="video",
        aliases=[
            "/extract_frames",
            "extract frames",
            "extract_frames",
            "video frames",
            "split video",
            "frame extractor",
            "video splitter",
            "frames"
        ],
        parameters={
            "fps": {"type": float, "default": 1.0, "description": "Frames per second to extract (e.g. 1.0, 0.5)"},
            "num_frames": {"type": int, "default": 0, "description": "Exact number of frames to extract (0 for fps-based)"},
            "keyframes_only": {"type": bool, "default": False, "description": "Extract only keyframes"}
        },
        create_iterator_fn=_create_extract_frames_iterator,
        preview_fn=_preview_extract_frames
    )
)
