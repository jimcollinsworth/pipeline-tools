import os
import re
import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from src.core.config import get_settings
from src.db.manager import DBManager
from src.core.llm_service import LLMService


class MarkdownExporter:
    """Engine for generating and exporting structured Markdown reports from Pixeltable tables."""

    PRESETS = {
        "Executive Synthesis Report": {
            "mode": "llm",
            "system_prompt": (
                "You are an executive research analyst. Synthesize the provided table records into a "
                "comprehensive, high-level Executive Markdown Report. Structure the output with an Executive Summary, "
                "Key Themes & Insights, Detailed Findings, and Strategic Next Steps. Use clean Markdown formatting."
            ),
            "prompt_template": (
                "Analyze the following {total_rows} records from dataset '{domain}.{table}':\n\n"
                "{table_context}\n\n"
                "Provide a cohesive, multi-section Markdown report synthesizing the core takeaways across all items."
            )
        },
        "Structured Asset Catalog": {
            "mode": "direct",
            "system_prompt": "",
            "prompt_template": (
                "### 📁 {file_name}\n"
                "- **Modality:** `{modality}`\n"
                "- **Path:** `{rel_path}`\n"
                "- **Size:** {file_size}\n"
                "- **Extracted Content / Summary:**\n"
                "> {content}\n"
            )
        },
        "Key Findings & Entities Summary": {
            "mode": "llm",
            "system_prompt": (
                "You are a structured data specialist. Extract, aggregate, and cross-reference key entities, "
                "topics, metrics, and actionable findings from the provided dataset into a clean Markdown briefing."
            ),
            "prompt_template": (
                "Review the following records from table '{domain}.{table}':\n\n"
                "{table_context}\n\n"
                "Generate a structured Markdown report featuring:\n"
                "1. High-Level Summary\n"
                "2. Consolidated Entities & Topics (Categorized)\n"
                "3. Cross-Document Findings & Patterns\n"
                "4. Data Quality & Coverage Notes"
            )
        }
    }

    @classmethod
    def format_row_template(cls, row_dict: Dict[str, Any], template: str) -> str:
        """Replace {column_name} placeholders in template with row values."""
        rendered = template
        for k, v in row_dict.items():
            val_str = "" if v is None else str(v)
            rendered = rendered.replace(f"{{{k}}}", val_str)
        return rendered

    @classmethod
    def generate_report(
        cls,
        domain: str,
        table_name: str,
        prompt_template: str,
        system_prompt: Optional[str] = None,
        provider: str = "Ollama",
        model: Optional[str] = None,
        mode: str = "llm",
        max_rows: int = 50,
        output_dir: Optional[str] = None,
        custom_filename: Optional[str] = None,
        progress_callback: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Generate a Markdown document from table records.

        Args:
            domain: Pixeltable domain name.
            table_name: Pixeltable table name.
            prompt_template: Custom user prompt or per-row template.
            system_prompt: System prompt for LLM synthesis.
            provider: 'Ollama' or 'Gemini'.
            model: Target model identifier.
            mode: 'llm' (synthesis) or 'direct' (template).
            max_rows: Maximum records to include.
            output_dir: Destination folder (defaults to settings.export_dir).
            custom_filename: Optional base filename.
            progress_callback: Optional progress reporter fn(current, total, message).

        Returns:
            Dict containing status, file_path, markdown_content, row_count, etc.
        """
        clean_dir = (domain or "default").strip()
        clean_tbl = (table_name or "raw_assets").strip()

        if progress_callback:
            progress_callback(0.1, 1.0, f"Fetching data from `{clean_dir}.{clean_tbl}`...")

        # Fetch table data (lightweight=False to get full text and computed columns)
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
            progress_callback(0.3, 1.0, f"Processing {total_rows} records ({mode.upper()} mode)...")

        rendered_markdown = ""

        if mode.lower() == "direct":
            # Direct Template Formatting
            sections = []
            header = f"# {clean_tbl.replace('_', ' ').title()} — Data Export\n\n"
            header += f"> **Domain:** `{clean_dir}` | **Table:** `{clean_tbl}` | **Total Records:** {total_rows} | **Generated:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n---\n\n"
            sections.append(header)

            for i, r in enumerate(row_dicts, 1):
                if progress_callback and total_rows > 10:
                    progress_callback(0.3 + (i / total_rows) * 0.5, 1.0, f"Formatting row {i}/{total_rows}...")
                row_str = cls.format_row_template(r, prompt_template)
                sections.append(f"## Record #{i}\n\n{row_str}\n\n---\n")

            rendered_markdown = "\n".join(sections)

        else:
            # LLM Synthesis Mode
            # Construct a rich text representation of table rows
            context_blocks = []
            for i, r in enumerate(row_dicts, 1):
                block_lines = [f"### [Record {i}]"]
                for col in columns:
                    val = r.get(col)
                    if val is not None and str(val).strip():
                        # Truncate ultra-long raw blobs for LLM context window safety
                        str_val = str(val).strip()
                        if len(str_val) > 4000:
                            str_val = str_val[:4000] + " ... [truncated]"
                        block_lines.append(f"- **{col}:** {str_val}")
                context_blocks.append("\n".join(block_lines))

            table_context = "\n\n".join(context_blocks)

            # Build full synthesis prompt
            user_prompt = prompt_template.replace("{domain}", clean_dir)
            user_prompt = user_prompt.replace("{table}", clean_tbl)
            user_prompt = user_prompt.replace("{total_rows}", str(total_rows))
            if "{table_context}" in user_prompt:
                user_prompt = user_prompt.replace("{table_context}", table_context)
            else:
                user_prompt = f"{user_prompt}\n\n---\n### Table Data Context:\n\n{table_context}"

            if progress_callback:
                progress_callback(0.5, 1.0, f"Synthesizing report via {provider} ({model or 'default'})...")

            target_model = model or ("gemini-3.6-flash" if provider.lower() == "gemini" else "llama3.2")
            try:
                llm_output = LLMService.generate(
                    provider=provider,
                    model=target_model,
                    prompt=user_prompt,
                    system=system_prompt
                )
                rendered_markdown = (
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

        # Determine output file path
        settings = get_settings()
        target_dir = Path(output_dir or settings.export_dir or "exports")
        target_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if custom_filename and custom_filename.strip():
            safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', custom_filename.strip())
            file_name = f"{safe_name}.md" if not safe_name.endswith(".md") else safe_name
        else:
            file_name = f"{clean_dir}_{clean_tbl}_report_{timestamp}.md"

        output_path = target_dir / file_name

        if progress_callback:
            progress_callback(0.9, 1.0, f"Saving report to {output_path.name}...")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(rendered_markdown)

        if progress_callback:
            progress_callback(1.0, 1.0, "Export completed successfully!")

        return {
            "status": "success",
            "file_path": str(output_path.resolve()),
            "file_name": file_name,
            "markdown_content": rendered_markdown,
            "row_count": total_rows,
            "columns": columns,
            "mode": mode,
            "provider": provider if mode == "llm" else "Direct Template",
            "model": model if mode == "llm" else "-"
        }
