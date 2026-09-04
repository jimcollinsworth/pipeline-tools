"""
Context Controller
==================
Decoupled controller for the Context & Memory tab.
Coordinates loading, editing, saving, preset application, and clean index exporting
for table-level context files.
"""

import os
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import gradio as gr
from src.core.config import get_settings, update_last_entry
from src.core.context_manager import ContextManager, CONTEXT_PRESETS
from src.db.manager import DBManager

class ContextController:
    """Pure controller for table context and evolving memory operations."""

    @staticmethod
    def get_domains() -> list[str]:
        """Fetch available database domains/directories."""
        try:
            return DBManager.list_domains()
        except Exception:
            return ["default"]

    @staticmethod
    def get_tables(domain: str) -> list[str]:
        """Fetch available tables for a specific domain."""
        if not domain:
            return []
        try:
            return DBManager.list_tables(domain.strip())
        except Exception:
            return []

    @classmethod
    def handle_domain_change(cls, domain: str) -> Tuple[Any, str, str, str]:
        """
        When domain changes, refresh tables list and load context for the first table.
        Returns: (tables_dropdown_update, markdown_content, status_message, file_info_text)
        """
        clean_domain = domain.strip() if domain else "default"
        tables = cls.get_tables(clean_domain)
        selected_table = tables[0] if tables else ""
        
        if selected_table:
            content, status, file_info = cls.handle_load_context(clean_domain, selected_table)
        else:
            content = ""
            status = f"ℹ️ Domain '{clean_domain}' selected. No tables found."
            file_info = "*No table selected*"

        dropdown_update = gr.update(choices=tables, value=selected_table)
        return dropdown_update, content, status, file_info

    @classmethod
    def handle_load_context(cls, domain: str, table: str) -> Tuple[str, str, str]:
        """
        Load context file for a domain/table.
        Returns: (markdown_content, status_message, file_info_text)
        """
        if not domain or not table:
            return "", "⚠️ Select both Domain and Table to load context.", "*No table selected*"

        clean_domain = domain.strip()
        clean_table = table.strip()
        update_last_entry(last_domain=clean_domain, last_table=clean_table)

        file_path = ContextManager.get_context_file_path(clean_domain, clean_table)
        already_existed = file_path.exists()
        content = ContextManager.load_context(clean_domain, clean_table)

        size_kb = file_path.stat().st_size / 1024.0 if file_path.exists() else 0.0
        if already_existed:
            file_info = f"📁 **File**: `{file_path.as_posix()}` &bull; **Size**: {size_kb:.1f} KB &bull; **Git Tracked**: Yes"
            status = f"✅ Loaded context for `{clean_domain}.{clean_table}` ({size_kb:.1f} KB)."
        else:
            file_info = f"📁 **File**: `{file_path.as_posix()}` &bull; **Size**: {size_kb:.1f} KB &bull; **Status**: Initialized new template"
            status = f"✨ Initialized new context template for `{clean_domain}.{clean_table}`."

        return content, status, file_info

    @classmethod
    def handle_save_context(cls, domain: str, table: str, content: str) -> Tuple[str, str]:
        """
        Save edited context markdown to disk.
        Returns: (status_message, file_info_text)
        """
        if not domain or not table:
            return "⚠️ Select both Domain and Table before saving.", "*No table selected*"

        clean_domain = domain.strip()
        clean_table = table.strip()

        if not content or not content.strip():
            return "⚠️ Cannot save empty context content.", "*Empty content*"

        try:
            saved_path = ContextManager.save_context(clean_domain, clean_table, content)
            size_kb = saved_path.stat().st_size / 1024.0
            file_info = f"📁 **File**: `{saved_path.as_posix()}` &bull; **Size**: {size_kb:.1f} KB &bull; **Status**: Saved to disk"
            status = f"💾 Successfully saved context for `{clean_domain}.{clean_table}` ({size_kb:.1f} KB)."
            return status, file_info
        except Exception as e:
            return f"❌ Failed to save context: {e}", "*Save error*"

    @classmethod
    def handle_apply_preset(cls, preset_name: str, current_content: str) -> Tuple[str, str]:
        """
        Apply a preset strategy to the active context content.
        Returns: (updated_content, status_message)
        """
        if not preset_name or preset_name not in CONTEXT_PRESETS:
            return current_content, "⚠️ Please select a valid preset from the dropdown."

        updated = ContextManager.apply_preset(preset_name, current_content)
        preset_info = CONTEXT_PRESETS[preset_name]["description"]
        status = f"✨ Applied preset **{preset_name}** ({preset_info}). Review changes and click Save to persist."
        return updated, status

    @classmethod
    def handle_export_index(cls, domain: str, table: str, content: str) -> Tuple[str, Optional[str]]:
        """
        Export clean entity cross-reference index to exports/.
        Returns: (status_message, download_file_path)
        """
        if not domain or not table:
            return "⚠️ Select Domain and Table before exporting index.", None

        clean_domain = domain.strip()
        clean_table = table.strip()

        try:
            export_path = ContextManager.export_clean_index(clean_domain, clean_table, content)
            status = f"📑 Clean cross-reference index exported to `{export_path.as_posix()}`."
            return status, str(export_path)
        except Exception as e:
            return f"❌ Failed to export index: {e}", None
