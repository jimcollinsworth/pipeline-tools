"""
Markdown & Document Export Engine (AI Report Synthesis & Sidecar Generation)
============================================================================
This module powers document synthesis and Markdown report generation from Pixeltable tables.

Supported Export Strategies:
----------------------------
1. Single Document Synthesis Mode:
   - Aggregates multi-row dataset context into one structured briefing or catalog.
   - Outputs a unified file: `exports/{domain}_{table}_report_{timestamp}.md`.
2. Per-Row Sidecar Mode (_meta.md):
   - Executes 1 LLM call per record to produce rich, standalone sidecar documents.
   - Automatically embeds row-specific media (`![photo](file_path)`).
   - Outputs individual sidecar files: `exports/{source_stem}_meta.md` (overwriting as needed).
   - Streams live markdown previews row-by-row into the UI.
"""

import os
import re
import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Generator, Tuple
from src.core.config import get_settings
from src.db.manager import DBManager
from src.core.llm_service import LLMService
from src.core.exceptions import (
    LLMQuotaExceededError,
    LLMAuthError,
    LLMServiceUnavailableError,
)


class MarkdownExporter:
    """Engine for generating and exporting structured Markdown reports and per-row sidecars."""

    PRESETS = {
        "Newspaper Story & Embedded Photo": {
            "mode": "sidecar",
            "system_prompt": (
                "You are an award-winning investigative photojournalist and editorial writer. "
                "Write an engaging, evocative, and richly descriptive newspaper/magazine article for the given media item. "
                "Always embed the item's photo or media at the top using valid Markdown: `![Photo Caption]({file_path})`. "
                "Format with a striking headline (# Headline), byline, lead paragraph, pull-quote, deep narrative body, and metadata sidebar."
            ),
            "prompt_template": (
                "Write a captivating newspaper article about this record:\n"
                "- File Name: {file_name}\n"
                "- Media Path: {file_path}\n"
                "- Description / Visual Context: {visual_summary}\n"
                "- Detected Objects / Tags: {object_tags}\n"
                "- Palette / Mood: {dominant_colors}, {mood_palette}\n"
                "- Extracted Content: {content}\n\n"
                "Requirements:\n"
                "1. Embed the image at the top using: `![{file_name}]({file_path})`\n"
                "2. Create an evocative # Headline and Byline.\n"
                "3. Write a vivid 3-paragraph human-interest story weaving together the visual elements and context.\n"
                "4. Include a Markdown table or metadata block summarizing the record properties."
            )
        },
        "Entity & Keyword Intelligence": {
            "mode": "single",
            "system_prompt": (
                "Extract, disambiguate, and structure named entities (persons, organizations, locations, artifacts) "
                "and domain taxonomy keywords from the dataset into organized Markdown tables and categorized lists. "
                "Adhere strictly to factual record context without extrapolating."
            ),
            "prompt_template": (
                "Extract structured entity intelligence from the following {total_rows} records in '{domain}.{table}':\n\n"
                "{table_context}\n\n"
                "Produce an Entity & Knowledge Breakdown:\n"
                "| Category | Identified Entity / Item | Context / Associated Record |\n"
                "|---|---|---|\n"
                "(Populate table for People, Companies/Brands, Locations, and Artifacts)\n\n"
                "### Indexing Tags\n"
                "- List 10-15 key search and metadata tags across the collection."
            )
        },
        "Visual & Multimodal Scene Analysis": {
            "mode": "single",
            "system_prompt": (
                "Analyze visual composition, spatial framing, dominant color palettes (RGB/HSL taxonomy), "
                "lighting conditions (ambient, artificial, directional), and scene geometry across the provided media records. "
                "Produce a rigorous, structured visual taxonomy report."
            ),
            "prompt_template": (
                "Analyze the visual and environmental characteristics across these {total_rows} media records from '{domain}.{table}':\n\n"
                "{table_context}\n\n"
                "Provide a Visual Breakdown:\n"
                "1. **Subject Composition & Framing**: Main subjects, focal points, and object arrangements.\n"
                "2. **Color Palette Distribution**: Group identified dominant colors (Warm, Cool, Earthy, Monochromatic) with file examples.\n"
                "3. **Lighting & Atmosphere**: Daylight, nighttime, artificial, golden hour, or indoor lighting patterns.\n"
                "4. **Scene Classification Summary**: Breakdown of indoor vs. outdoor, portrait vs. landscape vs. macro items."
            )
        },
        "Thematic Summary & Executive Brief": {
            "mode": "single",
            "system_prompt": (
                "Synthesize dataset records into a structured analytical briefing. "
                "Group findings by cross-cutting themes, identify statistical patterns and unique outlier records, "
                "and summarize core data takeaways with crisp, high-density Markdown."
            ),
            "prompt_template": (
                "Synthesize a narrative executive brief based on the {total_rows} records in '{domain}.{table}':\n\n"
                "{table_context}\n\n"
                "Structure the document with:\n"
                "- **Executive Summary**: 2-paragraph high-level narrative of the dataset contents and domain scope.\n"
                "- **Key Trends & Recurring Patterns**: 3-4 major patterns or themes observed across the data.\n"
                "- **Outliers & Standout Items**: Notable exceptions, unusual records, or unique findings.\n"
                "- **Strategic Takeaways**: Key conclusions and recommendations based on the findings."
            )
        },
        "Structured Media Catalog Dossier": {
            "mode": "single",
            "system_prompt": (
                "Format the dataset into an exhaustive, highly-structured Markdown catalog dossier. "
                "Present each record with clean metadata badges, extracted summaries, object tags, and technical properties. "
                "Conclude with an indexing summary table."
            ),
            "prompt_template": (
                "Generate a structured media catalog dossier for the following {total_rows} records from '{domain}.{table}':\n\n"
                "{table_context}\n\n"
                "Format each record systematically with:\n"
                "### 📄 [file_name]\n"
                "- **Attributes:** `[modality]` | `[file_type]` | `[file_size]` | `[rel_path]`\n"
                "- **Summary:** [Concise visual/text summary]\n"
                "- **Entities & Tags:** `[comma-separated tags]`\n"
                "---\n\n"
                "### 📊 Collection Index Table\n"
                "| # | File Name | Modality | Primary Classification | Key Tags |\n"
                "|---|---|---|---|---|\n"
                "(Populate table for all records)"
            )
        }
    }

    @classmethod
    def build_yaml_frontmatter(
        cls,
        title: str,
        description: str,
        domain: str,
        table: str,
        export_strategy: str,
        provider: str,
        model: str,
        total_records: int,
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
        extra_fields: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Construct clean, single-line YAML frontmatter block for exported Markdown files.
        Safely escapes double quotes and collapses newlines to keep lines compact, self-documenting, and parseable.
        """
        def _clean_val(val: Any) -> str:
            if val is None:
                return '""'
            s = str(val).replace('"', '\\"').replace('\r\n', ' ').replace('\n', ' ').strip()
            return f'"{s}"'

        lines = [
            "---",
            f"title: {_clean_val(title)}",
            f"description: {_clean_val(description)}",
            f"exported_at: {_clean_val(datetime.datetime.now().isoformat())}",
            f"domain: {_clean_val(domain)}",
            f"table: {_clean_val(table)}",
            f"export_strategy: {_clean_val(export_strategy)}",
            f"provider: {_clean_val(provider)}",
            f"model: {_clean_val(model)}",
            f"total_records: {total_records}",
            f"system_prompt: {_clean_val(system_prompt or '')}",
            f"user_prompt: {_clean_val(user_prompt or '')}",
        ]

        if extra_fields:
            for k, v in extra_fields.items():
                if isinstance(v, (int, float, bool)):
                    lines.append(f"{k}: {v}")
                else:
                    lines.append(f"{k}: {_clean_val(v)}")

        lines.append("---\n\n")
        return "\n".join(lines)

    @classmethod
    def format_row_template(cls, row_dict: Dict[str, Any], template: str) -> str:
        """Replace {column_name} placeholders in template with row values."""
        rendered = template
        for k, v in row_dict.items():
            val_str = "" if v is None else str(v)
            rendered = rendered.replace(f"{{{k}}}", val_str)
        return rendered


    @classmethod
    def generate_single_report(
        cls,
        domain: str,
        table_name: str,
        prompt_template: str,
        system_prompt: Optional[str] = None,
        provider: str = "Ollama",
        model: Optional[str] = None,
        mode: str = "single",
        max_rows: int = 50,
        output_dir: Optional[str] = None,
        custom_filename: Optional[str] = None,
        progress_callback: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Generate a single unified synthesis report for all rows."""
        clean_dir = (domain or "default").strip()
        clean_tbl = (table_name or "raw_assets").strip()

        if progress_callback:
            progress_callback(0.1, 1.0, f"Fetching data from `{clean_dir}.{clean_tbl}`...")

        table_res = DBManager.get_table_data(clean_dir, clean_tbl, limit=int(max_rows), lightweight=False)
        if table_res.get("error"):
            return {
                "status": "error",
                "message": f"Failed to fetch table data: {table_res.get('error')}"
            }

        columns: List[str] = table_res.get("columns", [])
        data_rows: List[List[Any]] = table_res.get("data", [])

        if not data_rows:
            return {
                "status": "error",
                "message": f"Table `{clean_dir}.{clean_tbl}` contains no records to export."
            }

        total_rows = len(data_rows)
        row_dicts: List[Dict[str, Any]] = [
            dict(zip(columns, row)) for row in data_rows
        ]

        if progress_callback:
            progress_callback(0.3, 1.0, f"Processing {total_rows} records...")

        if mode.lower() == "direct":
            # Direct Template Formatting without LLM
            sections = []
            header = f"# {clean_tbl.replace('_', ' ').title()} — Data Export\n\n"
            header += f"> **Domain:** `{clean_dir}` | **Table:** `{clean_tbl}` | **Total Records:** {total_rows} | **Generated:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n---\n\n"
            sections.append(header)

            for i, r in enumerate(row_dicts, 1):
                if progress_callback and total_rows > 10:
                    progress_callback(0.3 + (i / total_rows) * 0.5, 1.0, f"Formatting row {i}/{total_rows}...")
                row_str = cls.format_row_template(r, prompt_template)
                sections.append(f"## Record #{i}\n\n{row_str}\n\n---\n")

            desc = f"Direct template data export of {total_rows} records from {clean_dir}.{clean_tbl}"
            frontmatter = cls.build_yaml_frontmatter(
                title=f"{clean_tbl.replace('_', ' ').title()} — Data Export",
                description=desc,
                domain=clean_dir,
                table=clean_tbl,
                export_strategy="direct_template",
                provider="Direct (Template)",
                model="None",
                total_records=total_rows,
                system_prompt="",
                user_prompt=prompt_template
            )
            rendered_markdown = f"{frontmatter}{''.join(sections)}"
        else:
            # LLM Synthesis Mode
            context_blocks = []
            for i, r in enumerate(row_dicts, 1):
                block_lines = [f"### [Record {i}: {r.get('file_name', 'Unknown')}]"]
                for col in columns:
                    val = r.get(col)
                    if val is not None and str(val).strip():
                        str_val = str(val).strip()
                        if len(str_val) > 4000:
                            str_val = str_val[:4000] + " ... [truncated]"
                        block_lines.append(f"- **{col}:** {str_val}")
                context_blocks.append("\n".join(block_lines))

            table_context = "\n\n".join(context_blocks)

            user_prompt = prompt_template.replace("{domain}", clean_dir)
            user_prompt = user_prompt.replace("{table}", clean_tbl)
            user_prompt = user_prompt.replace("{total_rows}", str(total_rows))
            if "{table_context}" in user_prompt:
                user_prompt = user_prompt.replace("{table_context}", table_context)
            else:
                user_prompt = f"{user_prompt}\n\n---\n### Table Data Context:\n\n{table_context}"

            if progress_callback:
                progress_callback(0.5, 1.0, f"Synthesizing report via {provider} ({model or 'default'})...")

            target_model = model or ("gemini-3.7-flash" if provider.lower() == "gemini" else "llama3.2")
            try:
                llm_output = LLMService.generate(
                    provider=provider,
                    model=target_model,
                    prompt=user_prompt,
                    system=system_prompt
                )
                desc = f"AI synthesis report analyzing {total_rows} records from {clean_dir}.{clean_tbl}"
                frontmatter = cls.build_yaml_frontmatter(
                    title=f"{clean_tbl.replace('_', ' ').title()} — AI Synthesis Report",
                    description=desc,
                    domain=clean_dir,
                    table=clean_tbl,
                    export_strategy="single_synthesis",
                    provider=provider,
                    model=target_model,
                    total_records=total_rows,
                    system_prompt=system_prompt,
                    user_prompt=prompt_template
                )
                rendered_markdown = (
                    f"{frontmatter}"
                    f"# {clean_tbl.replace('_', ' ').title()} — AI Synthesis Report\n\n"
                    f"> **Generated via:** `{provider}` ({target_model}) | **Domain:** `{clean_dir}` | "
                    f"**Table:** `{clean_tbl}` | **Records Analyzed:** {total_rows} | **Date:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                    f"---\n\n"
                    f"{llm_output.strip()}\n"
                )
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"LLM synthesis failed: {str(e)}"
                }

        settings = get_settings()
        target_dir = Path(output_dir or settings.export_dir or "exports")
        target_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if custom_filename and custom_filename.strip():
            safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', custom_filename.strip())
            file_name = f"{safe_name}.md" if not safe_name.endswith(".md") else safe_name
        else:
            file_name = f"{clean_dir}_{clean_tbl}_report_{timestamp}.md"

        output_file_path = target_dir / file_name
        with open(output_file_path, "w", encoding="utf-8") as f:
            f.write(rendered_markdown)

        return {
            "status": "success",
            "file_path": str(output_file_path.resolve()),
            "file_name": file_name,
            "markdown_content": rendered_markdown,
            "row_count": total_rows,
            "mode": mode
        }

    @classmethod
    def generate_sidecar_exports(
        cls,
        domain: str,
        table_name: str,
        prompt_template: str,
        system_prompt: Optional[str] = None,
        provider: str = "Ollama",
        model: Optional[str] = None,
        max_rows: int = 50,
        output_dir: Optional[str] = None,
        progress_callback: Optional[Any] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Generate per-row sidecar files ({file_name}_meta.md) with live row-by-row streaming.
        Yields progress dict for each row processed.
        """
        clean_dir = (domain or "default").strip()
        clean_tbl = (table_name or "raw_assets").strip()

        table_res = DBManager.get_table_data(clean_dir, clean_tbl, limit=int(max_rows), lightweight=False)
        if table_res.get("error"):
            yield {
                "status": "error",
                "message": f"Failed to fetch table data: {table_res.get('error')}"
            }
            return

        columns: List[str] = table_res.get("columns", [])
        data_rows: List[List[Any]] = table_res.get("data", [])

        if not data_rows:
            yield {
                "status": "error",
                "message": f"Table `{clean_dir}.{clean_tbl}` contains no records to export."
            }
            return

        total_rows = len(data_rows)
        row_dicts: List[Dict[str, Any]] = [
            dict(zip(columns, row)) for row in data_rows
        ]

        settings = get_settings()
        target_dir = Path(output_dir or settings.export_dir or "exports")
        target_dir.mkdir(parents=True, exist_ok=True)

        target_model = model or ("gemini-3.7-flash" if provider.lower() == "gemini" else "llama3.2")
        saved_files: List[str] = []
        last_preview_md = ""

        for idx, row in enumerate(row_dicts, 1):
            file_name = str(row.get("file_name", f"record_{idx}"))
            file_path = str(row.get("file_path", ""))
            modality = str(row.get("modality", "")).lower()

            if progress_callback:
                try:
                    progress_callback(idx / total_rows, 1.0, f"Processing row {idx}/{total_rows}: {file_name}...")
                except Exception:
                    pass

            # Architecture Rule: We pass pure textual record metadata and file paths to the LLM
            # rather than uploading binary media buffers. This avoids multi-megabyte payloads and keeps latency low.
            # Media files are referenced via standard Markdown image embeds: `![Caption](file_path)`
            row_prompt = cls.format_row_template(row, prompt_template)
            row_prompt = row_prompt.replace("{domain}", clean_dir).replace("{table}", clean_tbl)

            # If template has no placeholders, automatically append record context
            has_placeholders = any(f"{{{k}}}" in prompt_template for k in row.keys())
            if not has_placeholders:
                row_context = "\n".join([f"- **{k}:** {v}" for k, v in row.items() if v and k != "media_preview"])
                row_prompt = f"{row_prompt}\n\n### Record Data:\n{row_context}"

            # Token Constraint Invariant: Enforce clean Markdown and forbid heavy raw HTML/inline SVG
            # to prevent the LLM from outputting 4,000+ tokens of code that cause 30+ second latency spikes.
            effective_sys = system_prompt.strip() if system_prompt and system_prompt.strip() else (
                "You are an AI synthesis assistant. Output clean, concise GitHub-flavored Markdown. "
                "Do not generate heavy raw HTML, inline CSS, or SVG code. "
                "Embed images using standard Markdown syntax: `![Caption](path)`."
            )

            try:
                llm_output = LLMService.generate(
                    provider=provider,
                    model=target_model,
                    prompt=row_prompt,
                    system=effective_sys
                )
            except (LLMQuotaExceededError, LLMAuthError, LLMServiceUnavailableError) as fatal_err:
                yield {
                    "status": "error",
                    "message": f"Sidecar batch export aborted at row {idx}/{total_rows}: {str(fatal_err)}"
                }
                return
            except Exception as e:
                err_str = str(e)
                if "RESOURCE_EXHAUSTED" in err_str or "429" in err_str:
                    yield {
                        "status": "error",
                        "message": f"Sidecar batch export halted at row {idx}/{total_rows} due to quota exhaustion (429): {err_str}"
                    }
                    return
                llm_output = f"> Warning: LLM generation failed for `{file_name}`: {err_str}"

            # Format sidecar content
            # Ensure the specific image/media is embedded if it's an image
            image_embed = ""
            if modality == "images" or file_name.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
                # Check if output already contains an image markdown link
                if not re.search(r'!\[.*?\]\(.*?\)', llm_output):
                    image_embed = f"![{file_name}]({file_path})\n\n"

            # Standardized clean YAML frontmatter
            extra_meta = {
                "source_file": file_name,
                "source_path": file_path,
                "row_index": idx,
                "modality": modality,
                "file_type": str(row.get("file_type", ""))
            }
            sidecar_desc = f"AI metadata sidecar for {file_name} from {clean_dir}.{clean_tbl}"
            frontmatter = cls.build_yaml_frontmatter(
                title=f"Metadata Sidecar: {file_name}",
                description=sidecar_desc,
                domain=clean_dir,
                table=clean_tbl,
                export_strategy="per_row_sidecar",
                provider=provider,
                model=target_model,
                total_records=total_rows,
                system_prompt=system_prompt,
                user_prompt=prompt_template,
                extra_fields=extra_meta
            )

            sidecar_md = f"{frontmatter}{image_embed}{llm_output.strip()}\n"

            # Derive sidecar filename: e.g. photo1.jpg -> photo1_meta.md
            stem = Path(file_name).stem if "." in file_name else file_name
            safe_stem = re.sub(r'[^a-zA-Z0-9_\-]', '_', stem)
            sidecar_name = f"{safe_stem}_meta.md"
            sidecar_path = target_dir / sidecar_name

            with open(sidecar_path, "w", encoding="utf-8") as f:
                f.write(sidecar_md)

            saved_files.append(str(sidecar_path.resolve()))
            last_preview_md = sidecar_md

            yield {
                "status": "progress" if idx < total_rows else "success",
                "current_index": idx,
                "total_rows": total_rows,
                "current_file": file_name,
                "sidecar_name": sidecar_name,
                "file_path": str(sidecar_path.resolve()),
                "saved_files": saved_files,
                "markdown_content": last_preview_md,
                "mode": "sidecar"
            }

    @classmethod
    def generate_report(
        cls,
        domain: str,
        table_name: str,
        prompt_template: str,
        system_prompt: Optional[str] = None,
        provider: str = "Ollama",
        model: Optional[str] = None,
        mode: str = "single",
        max_rows: int = 50,
        output_dir: Optional[str] = None,
        custom_filename: Optional[str] = None,
        progress_callback: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Dispatch report generation for single report or per-row sidecars."""
        is_sidecar = ("sidecar" in mode.lower() or "per-row" in mode.lower())

        if is_sidecar:
            last_res = {}
            for update in cls.generate_sidecar_exports(
                domain=domain,
                table_name=table_name,
                prompt_template=prompt_template,
                system_prompt=system_prompt,
                provider=provider,
                model=model,
                max_rows=max_rows,
                output_dir=output_dir,
                progress_callback=progress_callback
            ):
                last_res = update

            if last_res.get("status") in ["success", "progress"]:
                saved = last_res.get("saved_files", [])
                return {
                    "status": "success",
                    "file_path": saved[0] if saved else "",
                    "saved_files": saved,
                    "file_name": f"{len(saved)} Sidecars (_meta.md)",
                    "markdown_content": last_res.get("markdown_content", ""),
                    "row_count": len(saved),
                    "mode": "sidecar"
                }
            return last_res
        else:
            return cls.generate_single_report(
                domain=domain,
                table_name=table_name,
                prompt_template=prompt_template,
                system_prompt=system_prompt,
                provider=provider,
                model=model,
                mode=mode,
                max_rows=max_rows,
                output_dir=output_dir,
                custom_filename=custom_filename,
                progress_callback=progress_callback
            )
