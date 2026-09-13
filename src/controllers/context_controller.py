"""
Context Controller
==================
Decoupled controller for the Context View tab and Data Enhancement context activity.
Integrates domain system prompt persistence with IngestionContextManager.
"""

from typing import Dict, Any, Optional
from src.core.config import get_settings, update_last_entry, DEFAULT_SYSTEM_PROMPT
from src.core.ingestion_context import IngestionContextManager, IngestionContext


class ContextController:
    """Pure controller managing context wiki view, domain system prompts, and activity summaries."""

    @staticmethod
    def get_domain_system_prompt(domain: str) -> str:
        """Retrieve the configured system prompt for a given domain."""
        if not domain:
            domain = "default"
        clean_dir = domain.strip()
        settings = get_settings()
        prompts = settings.domain_system_prompts or {}
        return prompts.get(clean_dir, settings.last_system_prompt or DEFAULT_SYSTEM_PROMPT)

    @staticmethod
    def save_domain_system_prompt(domain: str, prompt: str) -> Dict[str, Any]:
        """Persist updated system prompt for the specified domain."""
        clean_dir = domain.strip() if domain else "default"
        clean_prompt = prompt.strip() if prompt else DEFAULT_SYSTEM_PROMPT
        settings = get_settings()
        prompts = dict(settings.domain_system_prompts or {})
        prompts[clean_dir] = clean_prompt
        update_last_entry(
            last_domain=clean_dir,
            last_system_prompt=clean_prompt,
            domain_system_prompts=prompts
        )
        return {
            "status": "success",
            "message": f"Saved system prompt for domain `{clean_dir}`.",
            "prompt": clean_prompt
        }

    @staticmethod
    def get_minimal_activity_summary(domain: str, table_name: str) -> str:
        """Format a compact 1-2 line summary of context state for the Data Enhancement accordion."""
        clean_dir = domain.strip() if domain else "default"
        clean_tbl = table_name.strip() if table_name else "raw_assets"

        ctx = IngestionContextManager.get_context(clean_dir, clean_tbl)
        entity_count = len(ctx.entities)
        alias_count = len(ctx.entity_aliases)
        theme_count = len(ctx.global_themes)
        tax_count = len(ctx.taxonomies)

        summary_lines = [
            f"🧠 **Entities Tracked:** `{entity_count}` | **Canonical Aliases:** `{alias_count}` | **Themes:** `{theme_count}` | **Taxonomies:** `{tax_count}`"
        ]

        if ctx.entities:
            sample_entities = list(ctx.entities.keys())[:5]
            summary_lines.append(f"🏷️ **Recent Entities:** {', '.join(f'`{e}`' for e in sample_entities)}")
        else:
            summary_lines.append("ℹ️ *No entities accumulated yet for this table. Run ingestion or batch enhancement to populate.*")

        return "\n\n".join(summary_lines)

    @staticmethod
    def load_context_state(domain: str, table_name: str) -> Dict[str, Any]:
        """Load structured context data for inspection and Markdown view."""
        clean_dir = domain.strip() if domain else "default"
        clean_tbl = table_name.strip() if table_name else "raw_assets"

        ctx = IngestionContextManager.get_context(clean_dir, clean_tbl)
        system_prompt = ContextController.get_domain_system_prompt(clean_dir)
        markdown_register = ctx.format_markdown_register()

        # Build entity table rows
        entity_rows = []
        for name, meta in ctx.entities.items():
            cat = meta.get("category", "entity")
            count = meta.get("occurrences", 1)
            docs = ", ".join(meta.get("referencing_documents", [])) or "—"
            entity_rows.append([name, cat, count, docs])

        return {
            "status": "success",
            "domain": clean_dir,
            "table": clean_tbl,
            "system_prompt": system_prompt,
            "markdown_register": markdown_register,
            "entity_rows": entity_rows,
            "entity_count": len(ctx.entities),
            "alias_count": len(ctx.entity_aliases)
        }

    @staticmethod
    def export_context_markdown(domain: str, table_name: str) -> Dict[str, Any]:
        """Export accumulated knowledge register to markdown file."""
        clean_dir = domain.strip() if domain else "default"
        clean_tbl = table_name.strip() if table_name else "raw_assets"

        ctx = IngestionContextManager.get_context(clean_dir, clean_tbl)
        exported_path = ctx.export_to_markdown()
        content = ctx.format_markdown_register()

        return {
            "status": "success",
            "message": f"Exported context knowledge register to `{exported_path}`.",
            "file_path": exported_path,
            "content": content
        }
