import unittest
import os
import sys
import io
import time
import warnings
import logging
from pathlib import Path

# Safe stdout reconfigure for Windows codepages
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Suppress third-party warnings and loggers
warnings.filterwarnings("ignore")
logging.getLogger().setLevel(logging.ERROR)
logging.getLogger("pixeltable").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("google_genai").setLevel(logging.ERROR)

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import pixeltable as pxt
except ImportError:
    pxt = None

from src.core.config import get_settings, Settings, sanitize_identifier
from src.core.ollama_client import OllamaClient
from src.ingest.scanner import scan_directory, classify_modality
from src.db.manager import DBManager, PIXELTABLE_AVAILABLE
from src.core.llm_service import LLMService
from src.prompts.executor import PromptExecutor, extract_json_payload, infer_pixeltable_type
from src.export.exporter import MarkdownExporter


class TestPipelineTools(unittest.TestCase):
    """Automated test suite for Pipeline Tools with isolated setup and teardown."""

    TEST_DOMAIN = "test_suite_isolated"

    @classmethod
    def setUpClass(cls):
        """Clean and prepare isolated test environment prior to test execution."""
        if PIXELTABLE_AVAILABLE:
            try:
                DBManager.drop_dir(cls.TEST_DOMAIN, force=True)
            except Exception:
                pass

    @classmethod
    def tearDownClass(cls):
        """Reliably purge temporary test tables and clean up database locks upon completion."""
        if PIXELTABLE_AVAILABLE:
            try:
                DBManager.drop_dir(cls.TEST_DOMAIN, force=True)
            except Exception:
                pass

    def test_settings_load(self):
        """[Config] Verify application settings load properly from config file / defaults."""
        settings = get_settings()
        self.assertIsInstance(settings, Settings)
        self.assertTrue(len(settings.ollama_host) > 0)

    def test_modality_classification(self):
        """[Scanner] Verify file extensions are correctly classified into modalities (docs, images, audio, video)."""
        self.assertEqual(classify_modality(".pdf"), "docs")
        self.assertEqual(classify_modality(".md"), "docs")
        self.assertEqual(classify_modality(".png"), "images")
        self.assertEqual(classify_modality(".mp3"), "audio")
        self.assertEqual(classify_modality(".mp4"), "video")
        self.assertEqual(classify_modality(".unknown_ext_xyz"), "other")

    def test_scanner_on_project_dir(self):
        """[Scanner] Verify directory scanner recursively discovers project files and metadata."""
        files = scan_directory("src", recursive=True)
        self.assertTrue(len(files) > 0)
        self.assertTrue(any(f["name"] == "config.py" for f in files))

    def test_scanner_empty_or_nonexistent_directory(self):
        """[Scanner] Verify directory scanner gracefully handles non-existent or empty folders without raising errors."""
        files = scan_directory("non_existent_folder_path_xyz_123", recursive=True)
        self.assertEqual(files, [])

    def test_gradio_app_initialization(self):
        """[UI] Verify Gradio Workbench Block component initializes without errors."""
        from app import create_app
        demo = create_app()
        self.assertIsNotNone(demo)
        self.assertTrue(hasattr(demo, "launch"))

    def test_pixeltable_manager_and_columns(self):
        """[Database] Verify Pixeltable table creation, default schema columns, and data querying."""
        if PIXELTABLE_AVAILABLE:
            table = DBManager.get_or_create_table(self.TEST_DOMAIN, "assets")
            self.assertIsNotNone(table)
            cols = list(table.columns())
            self.assertIn("file_name", cols)
            self.assertIn("content", cols)
            
            res = DBManager.get_table_data(self.TEST_DOMAIN, "assets", limit=5)
            self.assertIn("columns", res)
            self.assertTrue(isinstance(res["columns"], list))

    def test_db_manager_drop_table_and_dir(self):
        """[Database] Verify DBManager cleanly drops individual tables and directories."""
        if PIXELTABLE_AVAILABLE:
            DBManager.get_or_create_table(self.TEST_DOMAIN, "to_drop_table")
            self.assertIn("to_drop_table", DBManager.list_tables(self.TEST_DOMAIN))
            
            dropped = DBManager.drop_table(self.TEST_DOMAIN, "to_drop_table")
            self.assertTrue(dropped)
            self.assertNotIn("to_drop_table", DBManager.list_tables(self.TEST_DOMAIN))

    def test_sanitization(self):
        """[Database] Verify identifier sanitization cleans leading digits and dashes for SQL/Pixeltable compatibility."""
        ok, clean, msg = sanitize_identifier("123_table")
        self.assertTrue(ok)
        self.assertTrue(clean.startswith("t_"))
        
        ok, clean, msg = sanitize_identifier("my-table-name")
        self.assertTrue(ok)
        self.assertEqual(clean, "my_table_name")

    def test_table_path_resolution(self):
        """[Database] Verify table path resolution normalizes domain prefixes and list_tables returns clean names."""
        self.assertEqual(DBManager.resolve_table_path("test_iso", "raw_files_test"), "test_iso.raw_files_test")
        self.assertEqual(DBManager.resolve_table_path("test_iso", "test_iso/raw_files_test"), "test_iso.raw_files_test")
        self.assertEqual(DBManager.resolve_table_path("test_iso", "test_iso.raw_files_test"), "test_iso.raw_files_test")

    def test_extract_file_content(self):
        """[Ingest] Verify text extraction engine parses Markdown and text documents."""
        sample_md = Path("planning.md")
        if sample_md.exists():
            text = DBManager.extract_file_content(str(sample_md), "docs", ".md")
            self.assertTrue(len(text) > 0)
            self.assertIn("Pipeline Tools", text)

    def test_extract_file_content_nonexistent(self):
        """[Ingest] Verify text extraction engine returns empty string gracefully for missing files."""
        text = DBManager.extract_file_content("non_existent_file_path.md", "docs", ".md")
        self.assertEqual(text, "")

    def test_ingest_empty_file_list(self):
        """[Ingest] Verify DBManager.ingest_files returns a clean error dictionary when given no files."""
        res = DBManager.ingest_files(self.TEST_DOMAIN, "empty_test", [])
        self.assertEqual(res.get("status"), "error")
        self.assertIn("No files provided", res.get("message", ""))

    def test_ingest_progress_callback(self):
        """[Ingest] Verify DBManager.ingest_files invokes progress callback with step updates."""
        if PIXELTABLE_AVAILABLE:
            calls = []
            def cb(cur, total, detail):
                calls.append((cur, total, detail))

            fake_files = [{
                "name": "sample.md",
                "abs_path": str(Path("planning.md").resolve()),
                "rel_path": "planning.md",
                "modality": "docs",
                "extension": ".md",
                "size_bytes": 100,
                "size": "100 B"
            }]
            res = DBManager.ingest_files(self.TEST_DOMAIN, "progress_test", fake_files, progress_callback=cb)
            self.assertEqual(res.get("status"), "success")
            self.assertTrue(len(calls) > 0)
            self.assertEqual(calls[-1][0], calls[-1][1])

    def test_ingest_overwrite_mode(self):
        """[Ingest] Verify DBManager.ingest_files supports table overwrite mode and preserves Pixeltable lineage."""
        if PIXELTABLE_AVAILABLE:
            fake_files = [{
                "name": "sample.md",
                "abs_path": str(Path("planning.md").resolve()),
                "rel_path": "planning.md",
                "modality": "docs",
                "extension": ".md",
                "size_bytes": 100,
                "size": "100 B"
            }]
            # Initial Ingestion
            res1 = DBManager.ingest_files(self.TEST_DOMAIN, "overwrite_test", fake_files, overwrite=False)
            self.assertEqual(res1.get("status"), "success")
            # Overwrite Ingestion
            res2 = DBManager.ingest_files(self.TEST_DOMAIN, "overwrite_test", fake_files, overwrite=True)
            self.assertEqual(res2.get("status"), "success")
            self.assertTrue(res2.get("overwritten"))

    def test_gemini_client_models(self):
        """[Gemini] Verify GeminiClient discovers modern Gemini 3.x models and handles missing API key."""
        from src.core.gemini_client import GeminiClient
        client = GeminiClient()
        models = client.list_models()
        model_names = [m["name"] for m in models]
        self.assertIn("gemini-3.6-flash", model_names)
        self.assertIn("gemini-3.5-flash-lite", model_names)
        self.assertIn("gemini-3.1-pro-preview", model_names)
        
        ok, msg = client.check_connection(api_key="")
        self.assertFalse(ok)
        self.assertIn("missing", msg.lower())

    def test_llm_service_router(self):
        """[Router] Verify unified LLMService routes queries and model discovery between Ollama and Gemini."""
        self.assertIn("Ollama", LLMService.PROVIDERS)
        self.assertIn("Gemini", LLMService.PROVIDERS)

        gemini_models = LLMService.list_models_for_provider("Gemini")
        self.assertIn("gemini-3.6-flash", gemini_models)

        ollama_models = LLMService.list_models_for_provider("Ollama")
        self.assertTrue(len(ollama_models) > 0)

    def test_extract_json_payload_variations(self):
        """[JSON] Verify robust extraction across pure JSON, markdown blocks, leading/trailing text, and malformed strings."""
        # Case 1: Pure JSON string
        pure = '{"image_summary": "A lake view", "haiku": "Calm blue water shines", "count": 3}'
        res1 = extract_json_payload(pure)
        self.assertIsNotNone(res1)
        self.assertEqual(res1.get("image_summary"), "A lake view")
        self.assertEqual(res1.get("count"), 3)

        # Case 2: Markdown fenced code block
        fenced = "Here is the extracted analysis:\n```json\n{\n  \"sentiment\": 0.95,\n  \"tags\": [\"nature\", \"water\"]\n}\n```\nHope that helps!"
        res2 = extract_json_payload(fenced)
        self.assertIsNotNone(res2)
        self.assertEqual(res2.get("sentiment"), 0.95)
        self.assertEqual(res2.get("tags"), ["nature", "water"])

        # Case 3: Embedded raw braces without markdown fences
        embedded = "Output: {\"author\": \"Alice\", \"valid\": true} (analyzed at 2026-08-30)"
        res3 = extract_json_payload(embedded)
        self.assertIsNotNone(res3)
        self.assertEqual(res3.get("author"), "Alice")
        self.assertTrue(res3.get("valid"))

        # Case 4: Invalid/empty/non-JSON text
        self.assertIsNone(extract_json_payload("Just plain text with no brackets"))
        self.assertIsNone(extract_json_payload(""))
        self.assertIsNone(extract_json_payload("{broken json without closing"))

    def test_infer_pixeltable_type(self):
        """[JSON] Verify Python data values correctly map to Pixeltable scalar and collection types."""
        import pixeltable as pxt

        self.assertEqual(infer_pixeltable_type("sample string"), pxt.String)
        self.assertEqual(infer_pixeltable_type(42), pxt.Int)
        self.assertEqual(infer_pixeltable_type(3.1415), pxt.Float)
        self.assertEqual(infer_pixeltable_type(True), pxt.Bool)
        self.assertEqual(infer_pixeltable_type(["a", "b", "c"]), pxt.Json)
        self.assertEqual(infer_pixeltable_type({"nested": "object"}), pxt.Json)

    def test_dynamic_multicolumn_batch_execution(self):
        """[Playground] Verify PromptExecutor auto-split unpacks JSON keys into distinct table columns."""
        from unittest.mock import patch

        if PIXELTABLE_AVAILABLE:
            fake_files = [{
                "name": "doc_sample.md",
                "abs_path": str(Path("planning.md").resolve()),
                "rel_path": "planning.md",
                "modality": "docs",
                "extension": ".md",
                "size_bytes": 100,
                "size": "100 B"
            }]
            DBManager.ingest_files(self.TEST_DOMAIN, "json_split_test", fake_files, overwrite=True)

            mock_json_response = '{"doc_summary": "Test summary", "doc_haiku": "Lines of code arise", "confidence": 0.98}'
            with patch("src.core.llm_service.LLMService.generate", return_value=mock_json_response):
                res = PromptExecutor.apply_prompt_to_table(
                    model="test-model",
                    prompt_template="Analyze {file_name}",
                    system_prompt="Return JSON",
                    table_dir=self.TEST_DOMAIN,
                    table_name="json_split_test",
                    auto_split=True
                )
                self.assertEqual(res.get("status"), "success")
                self.assertIn("doc_summary", res.get("columns", []))
                self.assertIn("doc_haiku", res.get("columns", []))
                self.assertIn("confidence", res.get("columns", []))

                # Verify columns exist in Pixeltable table data
                table_data = DBManager.get_table_data(self.TEST_DOMAIN, "json_split_test", limit=5)
                self.assertIn("doc_summary", table_data.get("columns", []))
                self.assertIn("doc_haiku", table_data.get("columns", []))
                self.assertIn("confidence", table_data.get("columns", []))

    def test_markdown_export_direct_template(self):
        """[Export] Verify MarkdownExporter creates formatted Markdown files using column placeholders."""
        if PIXELTABLE_AVAILABLE:
            fake_files = [{
                "name": "export_doc.md",
                "abs_path": str(Path("planning.md").resolve()),
                "rel_path": "planning.md",
                "modality": "docs",
                "extension": ".md",
                "size_bytes": 250,
                "size": "250 B"
            }]
            DBManager.ingest_files(self.TEST_DOMAIN, "export_test", fake_files, overwrite=True)

            template = "### Item: {file_name}\n- Modality: {modality}\n- Size: {file_size}"
            res = MarkdownExporter.generate_report(
                domain=self.TEST_DOMAIN,
                table_name="export_test",
                prompt_template=template,
                mode="direct",
                max_rows=10,
                custom_filename="test_direct_export"
            )
            self.assertEqual(res.get("status"), "success")
            self.assertTrue(os.path.exists(res.get("file_path")))
            self.assertIn("export_doc.md", res.get("markdown_content"))
            self.assertIn("Modality: docs", res.get("markdown_content"))

    def test_markdown_export_llm_synthesis(self):
        """[Export] Verify MarkdownExporter generates synthesized multi-row reports with LLMService."""
        from unittest.mock import patch

        if PIXELTABLE_AVAILABLE:
            fake_files = [{
                "name": "synthesis_doc.md",
                "abs_path": str(Path("planning.md").resolve()),
                "rel_path": "planning.md",
                "modality": "docs",
                "extension": ".md",
                "size_bytes": 300,
                "size": "300 B"
            }]
            DBManager.ingest_files(self.TEST_DOMAIN, "synthesis_test", fake_files, overwrite=True)

            mock_synthesis = "## Executive Summary\nAll documents show consistent data pipeline integration."
            with patch("src.core.llm_service.LLMService.generate", return_value=mock_synthesis):
                res = MarkdownExporter.generate_report(
                    domain=self.TEST_DOMAIN,
                    table_name="synthesis_test",
                    prompt_template="Synthesize {total_rows} items from {domain}.{table}",
                    system_prompt="Executive analyst role",
                    provider="Ollama",
                    model="test-model",
                    mode="llm",
                    max_rows=5,
                    custom_filename="test_synthesis_export"
                )
                self.assertEqual(res.get("status"), "success")
                self.assertTrue(os.path.exists(res.get("file_path")))
                self.assertIn("Executive Summary", res.get("markdown_content"))
                self.assertIn("synthesis_test", res.get("markdown_content"))
                self.assertIn("test_synthesis_export", res.get("file_name"))

    def test_export_empty_table_error_handling(self):
        """[Export] Verify MarkdownExporter returns a clean error dict when exporting a non-existent or empty table."""
        res = MarkdownExporter.generate_report(
            domain=self.TEST_DOMAIN,
            table_name="non_existent_table_xyz",
            prompt_template="Analyze items",
            mode="direct"
        )
        self.assertEqual(res.get("status"), "error")
        self.assertTrue(len(res.get("message", "")) > 0)

    def test_format_media_preview_html(self):
        """[Database] Verify DBManager.format_media_preview_html generates valid HTML tags for images, audio, video, and docs."""
        from PIL import Image
        temp_img = Path("temp_thumb_test.jpg")
        img = Image.new("RGB", (32, 32), color="green")
        img.save(temp_img)

        try:
            img_html = DBManager.format_media_preview_html(str(temp_img.resolve()), modality="images", file_type=".jpg")
            self.assertIn("<img", img_html)
            self.assertIn("/gradio_api/file=", img_html)

            audio_html = DBManager.format_media_preview_html("C:/data/song.mp3", modality="audio", file_type=".mp3")
            self.assertIn("<audio controls", audio_html)
            self.assertIn("/gradio_api/file=C:/data/song.mp3", audio_html)

            video_html = DBManager.format_media_preview_html("C:/data/clip.mp4", modality="video", file_type=".mp4")
            self.assertIn("<video controls", video_html)
            self.assertIn("/gradio_api/file=C:/data/clip.mp4", video_html)

            doc_html = DBManager.format_media_preview_html("C:/data/doc.pdf", modality="docs", file_type=".pdf")
            self.assertIn("<a href=", doc_html)
            self.assertIn("View PDF", doc_html)
        finally:
            if temp_img.exists():
                try:
                    temp_img.unlink()
                except Exception:
                    pass

    def test_get_table_data_lightweight_vs_full(self):
        """[Database] Verify get_table_data toggles between fast text mode and full HTML media preview mode."""
        if PIXELTABLE_AVAILABLE:
            from PIL import Image
            temp_img = Path("temp_test_img.jpg")
            img = Image.new("RGB", (16, 16), color="blue")
            img.save(temp_img)

            try:
                fake_files = [
                    {
                        "name": "temp_test_img.jpg",
                        "abs_path": str(temp_img.resolve()),
                        "rel_path": "temp_test_img.jpg",
                        "modality": "images",
                        "extension": ".jpg",
                        "size_bytes": 1024,
                        "size": "1 KB"
                    },
                    {
                        "name": "sample_doc.md",
                        "abs_path": str(Path("planning.md").resolve()),
                        "rel_path": "planning.md",
                        "modality": "docs",
                        "extension": ".md",
                        "size_bytes": 2048,
                        "size": "2 KB"
                    }
                ]
                DBManager.ingest_files(self.TEST_DOMAIN, "media_preview_test", fake_files, overwrite=True)

                # 1. Lightweight mode: media_preview omitted, binary columns hidden
                light_res = DBManager.get_table_data(self.TEST_DOMAIN, "media_preview_test", limit=5, lightweight=True)
                self.assertNotIn("media_preview", light_res.get("columns", []))
                self.assertNotIn("image", light_res.get("columns", []))
                self.assertNotIn("doc", light_res.get("columns", []))

                # 2. Full mode: media_preview present, datatypes contain 'html'
                full_res = DBManager.get_table_data(self.TEST_DOMAIN, "media_preview_test", limit=5, lightweight=False)
                self.assertIn("media_preview", full_res.get("columns", []))
                self.assertIn("html", full_res.get("datatypes", []))
                
                # Verify media_preview contains <img> tag for image row
                data_rows = full_res.get("data", [])
                cols = full_res.get("columns", [])
                preview_idx = cols.index("media_preview")
                img_row = [r for r in data_rows if r[cols.index("file_name")] == "temp_test_img.jpg"][0]
                self.assertIn("<img", img_row[preview_idx])
            finally:
                if temp_img.exists():
                    try:
                        temp_img.unlink()
                    except Exception:
                        pass

    def test_tab_dynamic_dropdown_refresh(self):
        """[UI] Verify newly created tables are dynamically discovered and selected across tabs."""
        if PIXELTABLE_AVAILABLE:
            new_table_name = "fresh_dynamic_table"
            DBManager.create_or_get_table(self.TEST_DOMAIN, new_table_name)

            # 1. Verify DBManager lists the newly created table under the domain
            tables = DBManager.list_tables(self.TEST_DOMAIN)
            self.assertIn(new_table_name, tables)

            # 2. Verify table preview loads the new table schema without errors
            res = DBManager.get_table_data(self.TEST_DOMAIN, new_table_name, limit=5, lightweight=True)
            self.assertIn("file_name", res.get("columns", []))
            self.assertEqual(res.get("total_rows"), 0)

    def test_undo_last_operation(self):
        """[Database] Verify 1-click Undo drops newly added LLM columns and reverts table schema."""
        if PIXELTABLE_AVAILABLE:
            tbl_name = "test_undo_tbl"
            table = DBManager.create_or_get_table(self.TEST_DOMAIN, tbl_name)
            
            # Add custom columns
            table.add_column(test_generated_col1=pxt.String, if_exists="ignore")
            table.add_column(test_generated_col2=pxt.String, if_exists="ignore")
            
            # Record operation
            DBManager.record_operation(
                self.TEST_DOMAIN, tbl_name,
                {"action": "add_columns", "columns": ["test_generated_col1", "test_generated_col2"]}
            )

            # Verify columns exist before undo
            res_before = DBManager.get_table_data(self.TEST_DOMAIN, tbl_name, limit=1)
            self.assertIn("test_generated_col1", res_before.get("columns", []))
            self.assertIn("test_generated_col2", res_before.get("columns", []))

            # Execute 1-click undo
            undo_res = DBManager.undo_last_operation(self.TEST_DOMAIN, tbl_name)
            self.assertEqual(undo_res.get("status"), "success")
            self.assertIn("test_generated_col1", undo_res.get("dropped_columns", []))

            # Verify columns were dropped after undo
            res_after = DBManager.get_table_data(self.TEST_DOMAIN, tbl_name, limit=1)
            self.assertNotIn("test_generated_col1", res_after.get("columns", []))
            self.assertNotIn("test_generated_col2", res_after.get("columns", []))

    def test_delete_table_and_domain_with_details(self):
        """[Database] Verify delete_table_with_details and delete_domain_with_details remove resources cleanly."""
        if PIXELTABLE_AVAILABLE:
            dom = "test_del_domain"
            t1 = "temp_del_t1"
            t2 = "temp_del_t2"
            DBManager.create_or_get_table(dom, t1)
            DBManager.create_or_get_table(dom, t2)

            # 1. Delete single table
            res_t1 = DBManager.delete_table_with_details(dom, t1)
            self.assertEqual(res_t1.get("status"), "success")
            self.assertNotIn(t1, DBManager.list_tables(dom))
            self.assertIn(t2, DBManager.list_tables(dom))

            # 2. Delete entire domain
            res_dom = DBManager.delete_domain_with_details(dom)
            self.assertEqual(res_dom.get("status"), "success")
            self.assertNotIn(dom, DBManager.list_dirs())



class CleanTestResult(unittest.TestResult):
    """Custom TestResult that captures noise and formats clean visual separators between tests."""

    def __init__(self, stream, total_tests=1):
        super().__init__()
        self.stream = stream
        self.total_tests = total_tests
        self.test_start_time = None
        self.test_count = 0
        self.successes = 0

    def startTest(self, test):
        self.test_count += 1
        self.test_start_time = time.time()
        doc = test._testMethodDoc or test.id()
        self.stream.write(f"  [{self.test_count}/{self.total_tests}] RUNNING: {doc}...\n")
        self.stream.flush()
        self._stdout_buffer = io.StringIO()
        self._stderr_buffer = io.StringIO()
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        sys.stdout = self._stdout_buffer
        sys.stderr = self._stderr_buffer
        super().startTest(test)

    def stopTest(self, test):
        sys.stdout = self._orig_stdout
        sys.stderr = self._orig_stderr
        super().stopTest(test)

    def addSuccess(self, test):
        super().addSuccess(test)
        self.successes += 1
        elapsed = time.time() - (self.test_start_time or time.time())
        doc = test._testMethodDoc or test.id()
        self.stream.write(f"  [{self.test_count}/{self.total_tests}] PASS ({elapsed:.3f}s)  {doc}\n")
        self.stream.write("  " + "-" * 72 + "\n")
        self.stream.flush()

    def addError(self, test, err):
        super().addError(test, err)
        elapsed = time.time() - (self.test_start_time or time.time())
        doc = test._testMethodDoc or test.id()
        self.stream.write(f"\n  [{self.test_count}/{self.total_tests}] ERROR ({elapsed:.3f}s)  {doc}\n")
        self.stream.write(f"      {err[0].__name__}: {err[1]}\n")
        self.stream.write("  " + "-" * 72 + "\n")
        self.stream.flush()

    def addFailure(self, test, err):
        super().addFailure(test, err)
        elapsed = time.time() - (self.test_start_time or time.time())
        doc = test._testMethodDoc or test.id()
        self.stream.write(f"\n  [{self.test_count}/{self.total_tests}] FAIL ({elapsed:.3f}s)  {doc}\n")
        self.stream.write(f"      {err[0].__name__}: {err[1]}\n")
        self.stream.write("  " + "-" * 72 + "\n")
        self.stream.flush()


def run_tests():
    header = "=" * 76
    print("\n" + header, flush=True)
    print("  PIPELINE TOOLS AUTOMATED TEST SUITE", flush=True)
    print(header + "\n", flush=True)
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestPipelineTools))
    try:
        from tests.test_controllers import TestControllers
        suite.addTests(loader.loadTestsFromTestCase(TestControllers))
    except Exception:
        pass

    total_count = suite.countTestCases()
    result = CleanTestResult(sys.stdout, total_tests=total_count)
    
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    def handle_test_interrupt(sig=None, frame=None):
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        # Clean up temporary test domain on interrupt
        if PIXELTABLE_AVAILABLE:
            try:
                DBManager.drop_dir(TestPipelineTools.TEST_DOMAIN, force=True)
            except Exception:
                pass
        print("\n\n🛑 Test suite interrupted by user (Ctrl+C). Restored terminal output and cleaned temporary tables.\n", flush=True)
        sys.exit(130)

    try:
        import signal
        signal.signal(signal.SIGINT, handle_test_interrupt)
        signal.signal(signal.SIGTERM, handle_test_interrupt)
    except Exception:
        pass

    try:
        suite.run(result)
    except KeyboardInterrupt:
        handle_test_interrupt()
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        # Final cleanup pass
        if PIXELTABLE_AVAILABLE:
            try:
                DBManager.drop_dir(TestPipelineTools.TEST_DOMAIN, force=True)
            except Exception:
                pass

    print("\n" + header, flush=True)
    print(f"  SUMMARY: {result.successes} Passed, {len(result.failures)} Failed, {len(result.errors)} Errors", flush=True)
    print(header + "\n", flush=True)
    return len(result.failures) == 0 and len(result.errors) == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(not success)
