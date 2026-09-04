"""
Tests for Decoupled Controllers
===============================
Direct unit tests for IngestController, PlaygroundController, and TablesController.
Verifies business logic, input validation, state transitions, and error handling
without requiring Gradio web server initialization.
"""

import os
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
from src.controllers.ingest_controller import IngestController
from src.controllers.playground_controller import PlaygroundController
from src.controllers.tables_controller import TablesController
from src.db.manager import DBManager, PIXELTABLE_AVAILABLE
from src.prompts.executor import PromptExecutor
from src.core.exceptions import (
    LLMQuotaExceededError,
    LLMAuthError,
    LLMServiceUnavailableError,
)
from src.core.gemini_client import GeminiClient
from src.core.ollama_client import OllamaClient

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
        self.assertFalse(insp["has_highlighted"])

    def test_tables_controller_entity_highlighting(self):
        """[Controller] Verify entity extraction and substring span highlighting for Gradio HighlightedText."""
        text = "Minutes of Muroc Building Corporation held in Chicago. Chairman Wm. M. Dewey presiding with Al Wagner."
        entities = [
            ("Muroc Building Corporation", "Organization"),
            ("Chicago", "Location"),
            ("Wm. M. Dewey", "Person"),
            ("Al Wagner", "Person")
        ]

        spans = TablesController.build_highlighted_spans(text, entities)
        self.assertIsInstance(spans, list)

        # Verify matched tokens have labels
        org_spans = [s for s, lbl in spans if lbl == "Organization"]
        self.assertIn("Muroc Building Corporation", org_spans)

        loc_spans = [s for s, lbl in spans if lbl == "Location"]
        self.assertIn("Chicago", loc_spans)

        person_spans = [s for s, lbl in spans if lbl == "Person"]
        self.assertIn("Wm. M. Dewey", person_spans)
        self.assertIn("Al Wagner", person_spans)

        # Test with row_dict containing entity columns
        row_dict = {
            "file_name": "minutes_1949.pdf",
            "content": text,
            "people": "Wm. M. Dewey, Al Wagner",
            "organizations": "Muroc Building Corporation",
            "locations": "Chicago"
        }
        extracted = TablesController.extract_entities_from_row_dict(row_dict)
        self.assertTrue(len(extracted) >= 4)

        insp = TablesController.handle_row_inspection(0, [row_dict], self.TEST_DOMAIN, "test")
        self.assertTrue(insp["has_highlighted"])
        self.assertTrue(len(insp["highlighted_spans"]) > 0)

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

    def test_gemini_client_error_classification(self):
        """[Controller] Verify GeminiClient maps 429 and auth errors to typed exceptions."""
        client = GeminiClient(api_key="fake-key")

        # 1. 429 RESOURCE_EXHAUSTED
        with patch.object(client, "get_client") as mock_get:
            mock_genai_client = MagicMock()
            mock_genai_client.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED: quota exceeded")
            mock_get.return_value = mock_genai_client

            with self.assertRaises(LLMQuotaExceededError):
                client.generate(model="gemini-3.6-flash", prompt="test")

        # 2. API Key Invalid
        with patch.object(client, "get_client") as mock_get:
            mock_genai_client = MagicMock()
            mock_genai_client.models.generate_content.side_effect = Exception("API_KEY_INVALID: bad key")
            mock_get.return_value = mock_genai_client

            with self.assertRaises(LLMAuthError):
                client.generate(model="gemini-3.6-flash", prompt="test")

    def test_quota_fail_fast_abort_in_sample_test(self):
        """[Controller] Verify PromptExecutor halts on quota error on row 1 without evaluating row 2+."""
        if PIXELTABLE_AVAILABLE:
            DBManager.get_or_create_table(self.TEST_DOMAIN, "quota_abort_test")
            # Ingest 3 dummy records
            dummy_files = [
                {"name": f"doc_{i}.txt", "abs_path": f"C:/fake_{i}.txt", "modality": "documents", "extension": ".txt"}
                for i in range(3)
            ]
            DBManager.ingest_files(self.TEST_DOMAIN, "quota_abort_test", dummy_files)

            call_count = 0

            def mock_generate(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                raise LLMQuotaExceededError("429 RESOURCE_EXHAUSTED")

            with patch("src.prompts.executor.LLMService.generate", side_effect=mock_generate):
                with self.assertRaises(LLMQuotaExceededError):
                    PromptExecutor.run_sample_test(
                        model="gemini-3.6-flash",
                        prompt_template="Summarize {file_name}",
                        system_prompt="",
                        table_dir=self.TEST_DOMAIN,
                        table_name="quota_abort_test",
                        provider="Gemini",
                        sample_count=3
                    )

            # Crucial verification: generate should have been called EXACTLY ONCE, not 3 times!
            self.assertEqual(call_count, 1)

    def test_batch_cancellation_flow(self):
        """[Controller] Verify PromptExecutor cancellation token halts batch processing early."""
        if PIXELTABLE_AVAILABLE:
            DBManager.get_or_create_table(self.TEST_DOMAIN, "cancel_batch_test")
            dummy_files = [
                {"name": f"img_{i}.png", "abs_path": f"C:/fake_{i}.png", "modality": "images", "extension": ".png"}
                for i in range(4)
            ]
            DBManager.ingest_files(self.TEST_DOMAIN, "cancel_batch_test", dummy_files)

            call_count = 0

            def mock_generate_with_cancel(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    PromptExecutor.cancel_execution()
                return '{"summary": "test scene"}'

            with patch("src.prompts.executor.LLMService.generate", side_effect=mock_generate_with_cancel):
                # Force fallback row loop to test iteration cancellation
                with patch("src.prompts.executor.pxt_generate_json", side_effect=Exception("force fallback")):
                    res = PromptExecutor.apply_prompt_to_table(
                        model="llama3.2",
                        prompt_template="Analyze {file_name}",
                        system_prompt="",
                        table_dir=self.TEST_DOMAIN,
                        table_name="cancel_batch_test",
                        provider="Ollama",
                        auto_split=True
                    )

            # Should have processed 2 rows before cancellation stopped it
            self.assertEqual(call_count, 2)
            self.assertEqual(res["status"], "warning")
            self.assertIn("halted", res["message"].lower())


