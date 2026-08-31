import os
import re
import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from src.core.config import get_settings
from src.db.manager import DBManager
from src.core.llm_service import LLMService


class MarkdownExporter:
    """Engine for generating and exporting structured Markdown reports from Pixeltable tables."""

    PRESETS = {
        "Entity & Keyword Intelligence": {
            "mode": "llm",
            "system_prompt": (
                "You are an information extraction system. Extract, aggregate, and structure all key entities, "
                "people, organizations, locations, and categorical keywords from the dataset into organized Markdown tables and lists."
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
            "mode": "llm",
            "system_prompt": (
                "You are a computer vision and media analyst. Analyze visual composition, color distributions, "
                "lighting conditions, and scene classifications across the provided dataset."
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
            "mode": "llm",
            "system_prompt": (
                "You are an executive intelligence analyst. Synthesize the dataset into a high-level narrative "
                "executive brief highlighting macro trends, recurring themes, notable anomalies, and strategic takeaways."
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
        "Direct Structured Catalog": {
            "mode": "direct",
            "system_prompt": "",
            "prompt_template": (
                "### 📄 {file_name}\n"
                "- **Modality:** `{modality}` | **Format:** `{file_type}` | **Size:** {file_size}\n"
                "- **Relative Path:** `{rel_path}`\n"
                "- **Content / Summary:**\n"
                "> {visual_summary}\n"
                "- **Tags / Entities:** `{object_tags}`\n"
                "- **Dominant Colors:** `{dominant_colors}`\n"
                "- **Scene Type:** `{scene_type}`"
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
            context_blocks = []
            for i, r in enumerate(row_dicts, 1):
                block_lines = [f"### [Record {i}]"]
                for col in columns:
                    val = r.get(col)
                    if val is not None and str(val).strip():
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
