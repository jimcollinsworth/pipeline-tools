"""
Tests for Context Processing & Memory
=====================================
Unit tests for ContextManager and ContextController.
Verifies context path resolution, template generation, preset application,
file persistence, and clean index exporting.
"""

import os
import unittest
from pathlib import Path
from src.core.context_manager import ContextManager, CONTEXT_PRESETS
from src.controllers.context_controller import ContextController

class TestContextProcessing(unittest.TestCase):
    """Test suite for ContextManager and ContextController."""

    TEST_DOMAIN = "test_unit_ctx"
    TEST_TABLE = "sample_records"

    def tearDown(self):
        """Clean up any temporary test context or export files created during tests."""
        ctx_file = ContextManager.get_context_file_path(self.TEST_DOMAIN, self.TEST_TABLE)
        if ctx_file.exists():
            try:
                ctx_file.unlink()
            except Exception:
                pass

        index_file = Path("exports") / f"{self.TEST_DOMAIN}_{self.TEST_TABLE}_index.md"
        if index_file.exists():
            try:
                index_file.unlink()
            except Exception:
                pass

    def test_context_manager_path_resolution(self):
        """[Context] Verify standard context file path normalization under contexts/."""
        path = ContextManager.get_context_file_path("EBA-Domain", "Meeting_Minutes 1949")
        self.assertEqual(path.name, "eba_domain_meeting_minutes_1949_context.md")
        self.assertEqual(path.parent.name, "contexts")

    def test_context_manager_generate_template(self):
        """[Context] Verify starter template contains all required structural sections."""
        template = ContextManager.generate_default_template(self.TEST_DOMAIN, self.TEST_TABLE)
        self.assertIn("# Context & Memory:", template)
        self.assertIn("## 1. Context System Prompt & Governance", template)
        self.assertIn("## 2. Active Skills & Tool Directives", template)
        self.assertIn("## 3. Canonical Entity Register", template)
        self.assertIn("### People", template)
        self.assertIn("### Organizations", template)
        self.assertIn("### Locations", template)
        self.assertIn("### Topics & Things", template)
        self.assertIn("## 4. Thematic Dataset Summary & Timeline", template)
        self.assertIn("## 5. Execution History & Lessons Learned", template)

    def test_context_manager_save_and_load(self):
        """[Context] Verify context saving and round-trip reading from disk."""
        custom_content = "# Context & Memory: custom\n\n## 1. Context System Prompt & Governance\nCustom Rules."
        saved_path = ContextManager.save_context(self.TEST_DOMAIN, self.TEST_TABLE, custom_content)
        self.assertTrue(saved_path.exists())

        loaded = ContextManager.load_context(self.TEST_DOMAIN, self.TEST_TABLE)
        self.assertEqual(loaded, custom_content)

    def test_context_manager_preset_application(self):
        """[Context] Verify applying presets updates the governance prompt correctly."""
        starter = ContextManager.generate_default_template(self.TEST_DOMAIN, self.TEST_TABLE)
        updated = ContextManager.apply_preset("EBA Corporate Minutes & Historical Bylaws", starter)
        self.assertIn("EBA building and HOA archive", updated)
        self.assertIn("Entity Canonicalization", updated)

        # Test another preset
        lifelog = ContextManager.apply_preset("Personal Lifelog & Multimodal Inbox", updated)
        self.assertIn("!ideas! for novel concepts", lifelog)
        self.assertIn("?questions? for research follow-ups", lifelog)

    def test_context_manager_export_clean_index(self):
        """[Context] Verify clean entity register index document is exported to exports/."""
        starter = ContextManager.generate_default_template(self.TEST_DOMAIN, self.TEST_TABLE)
        export_path = ContextManager.export_clean_index(self.TEST_DOMAIN, self.TEST_TABLE, starter)
        self.assertTrue(export_path.exists())
        content = export_path.read_text(encoding="utf-8")
        self.assertIn("# Cross-Reference Index:", content)
        self.assertIn("## 3. Canonical Entity Register", content)
        self.assertNotIn("## 1. Context System Prompt", content)

    def test_context_controller_workflow(self):
        """[Controller] Verify ContextController load, save, preset, and index export workflows."""
        # 1. Load context
        content, status, file_info = ContextController.handle_load_context(self.TEST_DOMAIN, self.TEST_TABLE)
        self.assertTrue(len(content) > 0)
        self.assertIn("Initialized new context template", status)
        self.assertIn("contexts/", file_info)

        # 2. Apply preset
        updated_content, preset_status = ContextController.handle_apply_preset("EBA Corporate Minutes & Historical Bylaws", content)
        self.assertIn("Applied preset", preset_status)
        self.assertIn("EBA building and HOA archive", updated_content)

        # 3. Save modified context
        save_status, save_info = ContextController.handle_save_context(self.TEST_DOMAIN, self.TEST_TABLE, updated_content)
        self.assertIn("Successfully saved", save_status)
        self.assertIn("Saved to disk", save_info)

        # 4. Export index
        index_status, download_path = ContextController.handle_export_index(self.TEST_DOMAIN, self.TEST_TABLE, updated_content)
        self.assertIn("Clean cross-reference index exported", index_status)
        self.assertIsNotNone(download_path)
        self.assertTrue(Path(download_path).exists())

        # 5. Invalid save rejection
        err_status, err_info = ContextController.handle_save_context("", "", "")
        self.assertIn("Select both Domain and Table", err_status)
