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

    def test_tables_controller_export_single_and_sidecar(self):
        """[Controller] Verify TablesController handles single and per-row sidecar export workflows."""
        from unittest.mock import patch
        if PIXELTABLE_AVAILABLE:
            fake_files = [{
                "name": "photo_export_ctrl.jpg",
                "abs_path": str(Path("planning.md").resolve()),
                "rel_path": "planning.md",
                "modality": "images",
                "extension": ".jpg",
                "size_bytes": 1024,
                "size": "1 KB"
            }]
            DBManager.ingest_files(self.TEST_DOMAIN, "export_ctrl_tbl", fake_files, overwrite=True)

            mock_story = "# Frontpage Story\nA detailed newspaper feature on the captured scene."
            with patch("src.export.exporter.LLMService.generate", return_value=mock_story):
                # 1. Single report mode
                single_res = TablesController.handle_export_report(
                    domain=self.TEST_DOMAIN,
                    table_name="export_ctrl_tbl",
                    provider="Ollama",
                    model="test-model",
                    max_rows=5,
                    system_prompt="Journalist",
                    prompt_template="Write story on {file_name}",
                    mode="single"
                )
                self.assertEqual(single_res["status"], "success")
                self.assertIn("Single Unified Synthesis", single_res["message"])

                # 2. Sidecar mode
                sidecar_res = TablesController.handle_export_report(
                    domain=self.TEST_DOMAIN,
                    table_name="export_ctrl_tbl",
                    provider="Ollama",
                    model="test-model",
                    max_rows=5,
                    system_prompt="Journalist",
                    prompt_template="Write story on {file_name}",
                    mode="sidecar"
                )
                self.assertEqual(sidecar_res["status"], "success")
                self.assertIn("Per-Row Sidecars", sidecar_res["message"])
                self.assertTrue(len(sidecar_res.get("saved_files", [])) > 0)

    def test_ingest_controller_single_csv_rules(self):
        """[Controller] Verify IngestController validates and enforces the single-CSV ingestion rule."""
        import tempfile

        # 1. Multiple CSVs rejected
        fake_multiple_csvs = [
            {"name": "file1.csv", "abs_path": "C:/file1.csv", "modality": "csv", "extension": ".csv"},
            {"name": "file2.csv", "abs_path": "C:/file2.csv", "modality": "csv", "extension": ".csv"}
        ]
        res_multi = IngestController.ingest_files_flow(self.TEST_DOMAIN, "csv_multi_test", fake_multiple_csvs)
        self.assertEqual(res_multi["status"], "error")
        self.assertIn("Single CSV Ingestion Rule", res_multi["message"])

        # 2. Mixed CSV and media rejected
        fake_mixed = [
            {"name": "file1.csv", "abs_path": "C:/file1.csv", "modality": "csv", "extension": ".csv"},
            {"name": "photo.jpg", "abs_path": "C:/photo.jpg", "modality": "images", "extension": ".jpg"}
        ]
        res_mixed = IngestController.ingest_files_flow(self.TEST_DOMAIN, "csv_mixed_test", fake_mixed)
        self.assertEqual(res_mixed["status"], "error")
        self.assertIn("Mixed Ingestion Not Permitted", res_mixed["message"])

        # 3. Single valid CSV accepted
        if PIXELTABLE_AVAILABLE:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
                tmp_csv = f.name
                f.write("City,Population\nTokyo,37000000\nDelhi,32000000\n")

            try:
                single_csv = [{
                    "name": "cities.csv",
                    "abs_path": tmp_csv,
                    "rel_path": "cities.csv",
                    "modality": "csv",
                    "extension": ".csv"
                }]
                res_single = IngestController.ingest_files_flow(self.TEST_DOMAIN, "cities_tbl", single_csv, overwrite=True)
                self.assertEqual(res_single["status"], "success", f"Failed with message: {res_single.get('message')}")
                self.assertIn("Rows Inserted", res_single["message"])
            finally:
                try:
                    os.unlink(tmp_csv)
                except Exception:
                    pass

