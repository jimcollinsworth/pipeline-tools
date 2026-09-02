"""
Tests for Decoupled Controllers
===============================
Direct unit tests for IngestController, PlaygroundController, and TablesController.
Verifies business logic, input validation, state transitions, and error handling
without requiring Gradio web server initialization.
"""

import unittest
from pathlib import Path
from src.controllers.ingest_controller import IngestController
from src.controllers.playground_controller import PlaygroundController
from src.controllers.tables_controller import TablesController
from src.db.manager import DBManager, PIXELTABLE_AVAILABLE

class TestControllers(unittest.TestCase):
    """Automated unit test suite for Pipeline Tools controller layer."""

    TEST_DOMAIN = "test_controller_isolated"

    @classmethod
    def setUpClass(cls):
        if PIXELTABLE_AVAILABLE:
            try:
                DBManager.drop_dir(cls.TEST_DOMAIN, force=True)
            except Exception:
                pass

    @classmethod
    def tearDownClass(cls):
        if PIXELTABLE_AVAILABLE:
            try:
                DBManager.drop_dir(cls.TEST_DOMAIN, force=True)
            except Exception:
                pass

    def test_ingest_controller_directory_suggestions(self):
        """[Controller] Verify IngestController generates path suggestions including CWD and Home."""
        suggestions = IngestController.get_directory_suggestions()
        self.assertIsInstance(suggestions, list)
        self.assertTrue(len(suggestions) > 0)
        self.assertIn(str(Path.cwd()), suggestions)

    def test_ingest_controller_scan_validation(self):
        """[Controller] Verify IngestController handles invalid directory paths gracefully."""
        # 1. Empty path
        res_empty = IngestController.scan_directory_flow("")
        self.assertEqual(res_empty["status"], "error")

        # 2. Non-existent path
        res_nonexistent = IngestController.scan_directory_flow("non_existent_folder_xyz_123")
        self.assertEqual(res_nonexistent["status"], "error")
        self.assertIn("Path Not Found", res_nonexistent["summary"])

        # 3. File instead of directory
        res_file = IngestController.scan_directory_flow("pyproject.toml")
        self.assertEqual(res_file["status"], "error")
        self.assertIn("Not a Directory", res_file["summary"])

    def test_ingest_controller_scan_success(self):
        """[Controller] Verify IngestController scans project directories and aggregates modality counts."""
        res = IngestController.scan_directory_flow("src", recursive=True)
        self.assertEqual(res["status"], "success")
        self.assertTrue(len(res["files_table"]) > 0)
        self.assertTrue(len(res["scanned_files"]) > 0)
        self.assertIn("Total Files Discovered", res["summary"])

    def test_ingest_controller_ingest_flow_validation(self):
        """[Controller] Verify IngestController validates empty scanned files and target identifiers."""
        # 1. Empty scanned files list
        res = IngestController.ingest_files_flow(self.TEST_DOMAIN, "test_tbl", [])
        self.assertEqual(res["status"], "error")
        self.assertIn("No files scanned yet", res["message"])

    def test_playground_controller_provider_and_domain_change(self):
        """[Controller] Verify PlaygroundController discovers models and tables on selection change."""
        # Provider change
        prov_res = PlaygroundController.handle_provider_change("Ollama")
        self.assertIn("choices", prov_res)
        self.assertIn("value", prov_res)

        # Domain change
        dom_res = PlaygroundController.handle_domain_change("default")
        self.assertIn("choices", dom_res)
        self.assertIn("value", dom_res)

    def test_playground_controller_table_preview(self):
        """[Controller] Verify PlaygroundController loads preview stats, datatypes, and placeholders."""
        if PIXELTABLE_AVAILABLE:
            DBManager.get_or_create_table(self.TEST_DOMAIN, "preview_test")
            preview = PlaygroundController.load_table_preview(self.TEST_DOMAIN, "preview_test", lightweight=True)
            self.assertEqual(preview["status"], "success")
            self.assertIn("file_name", preview["columns"])
            self.assertIn("Available Column Placeholders", preview["placeholders_text"])

    def test_tables_controller_load_table_and_domain_change(self):
        """[Controller] Verify TablesController loads table data and formats stats summary."""
        if PIXELTABLE_AVAILABLE:
            DBManager.get_or_create_table(self.TEST_DOMAIN, "tables_ctrl_test")
            res = TablesController.handle_load_table(self.TEST_DOMAIN, "tables_ctrl_test", limit=5, is_lightweight=True)
            self.assertEqual(res["status"], "success")
            self.assertIn("file_name", res["columns"])
            self.assertIn("Table `test_controller_isolated.tables_ctrl_test`", res["stats_text"])

            dom_res = TablesController.handle_domain_change(self.TEST_DOMAIN)
            self.assertIn("tables_ctrl_test", dom_res["choices"])

    def test_tables_controller_row_inspection(self):
        """[Controller] Verify TablesController inspects row data, formats details, and detects media types."""
        fake_df = [
            {
                "file_name": "sample_photo.jpg",
                "file_path": str(Path("sample_photo.jpg").resolve()),
                "modality": "images",
                "file_type": ".jpg",
                "file_size": 4096,
                "content": "A beautiful scenic mountain landscape.",
                "llm_summary": "Mountain landscape under clear blue skies."
            }
        ]

        insp = TablesController.handle_row_inspection(0, fake_df, self.TEST_DOMAIN, "test")
        self.assertIn("sample_photo.jpg", insp["details_markdown"])
        self.assertIn("llm_summary", insp["details_markdown"])
        self.assertTrue(insp["has_content"])
        self.assertEqual(insp["content_text"], "A beautiful scenic mountain landscape.")

    def test_tables_controller_delete_table_and_domain(self):
        """[Controller] Verify TablesController executes safe table and domain deletion with updated choices."""
        if PIXELTABLE_AVAILABLE:
            # Create isolated tables
            DBManager.get_or_create_table(self.TEST_DOMAIN, "to_delete_tbl")
            self.assertIn("to_delete_tbl", DBManager.list_tables(self.TEST_DOMAIN))

            # Delete table
            del_tbl_res = TablesController.handle_delete_table(self.TEST_DOMAIN, "to_delete_tbl")
            self.assertEqual(del_tbl_res["status"], "success")
            self.assertNotIn("to_delete_tbl", del_tbl_res["table_choices"])

            # Delete domain
            del_dom_res = TablesController.handle_delete_domain(self.TEST_DOMAIN)
            self.assertEqual(del_dom_res["status"], "success")
            self.assertNotIn(self.TEST_DOMAIN, del_dom_res["domain_choices"])
