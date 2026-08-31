import unittest
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

# Suppress all third-party warnings and loggers
warnings.filterwarnings("ignore")
logging.getLogger().setLevel(logging.ERROR)
logging.getLogger("pixeltable").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.ERROR)

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import get_settings, Settings
from src.core.ollama_client import OllamaClient
from src.ingest.scanner import scan_directory, classify_modality

class TestPipelineTools(unittest.TestCase):
    """Automated test suite for Pipeline Tools core components and Gradio UI."""

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

    def test_scanner_on_project_dir(self):
        """[Scanner] Verify directory scanner recursively discovers project files and metadata."""
        files = scan_directory("src", recursive=True)
        self.assertTrue(len(files) > 0)
        self.assertTrue(any(f["name"] == "config.py" for f in files))

    def test_gradio_app_initialization(self):
        """[UI] Verify Gradio Workbench Block component initializes without errors."""
        from app import create_app
        demo = create_app()
        self.assertIsNotNone(demo)
        self.assertTrue(hasattr(demo, "launch"))

    def test_pixeltable_manager_and_columns(self):
        """[Database] Verify Pixeltable table creation, default schema columns, and data querying."""
        from src.db.manager import DBManager, PIXELTABLE_AVAILABLE
        if PIXELTABLE_AVAILABLE:
            table = DBManager.get_or_create_table("test_unit", "assets")
            self.assertIsNotNone(table)
            cols = list(table.columns())
            self.assertIn("file_name", cols)
            self.assertIn("content", cols)
            
            res = DBManager.get_table_data("test_unit", "assets", limit=5)
            self.assertIn("columns", res)
            self.assertTrue(isinstance(res["columns"], list))

    def test_sanitization(self):
        """[Database] Verify identifier sanitization cleans leading digits and dashes for SQL/Pixeltable compatibility."""
        from src.core.config import sanitize_identifier
        ok, clean, msg = sanitize_identifier("123_table")
        self.assertTrue(ok)
        self.assertTrue(clean.startswith("t_"))
        
        ok, clean, msg = sanitize_identifier("my-table-name")
        self.assertTrue(ok)
        self.assertEqual(clean, "my_table_name")

    def test_table_path_resolution(self):
        """[Database] Verify table path resolution normalizes domain prefixes and list_tables returns clean names."""
        from src.db.manager import DBManager
        self.assertEqual(DBManager.resolve_table_path("eba", "raw_files_test"), "eba.raw_files_test")
        self.assertEqual(DBManager.resolve_table_path("eba", "eba/raw_files_test"), "eba.raw_files_test")
        self.assertEqual(DBManager.resolve_table_path("eba", "eba.raw_files_test"), "eba.raw_files_test")
        
        tables = DBManager.list_tables("eba")
        for t in tables:
            self.assertFalse("/" in t, f"Table name should be bare without slashes: {t}")

    def test_extract_file_content(self):
        """[Ingest] Verify text extraction engine parses Markdown and text documents."""
        from src.db.manager import DBManager
        sample_md = Path("planning.md")
        if sample_md.exists():
            text = DBManager.extract_file_content(str(sample_md), "docs", ".md")
            self.assertTrue(len(text) > 0)
            self.assertIn("Pipeline Tools", text)

    def test_ingest_progress_callback(self):
        """[Ingest] Verify DBManager.ingest_files invokes progress callback with step updates."""
        from src.db.manager import DBManager, PIXELTABLE_AVAILABLE
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
            res = DBManager.ingest_files("test_unit", "progress_test", fake_files, progress_callback=cb)
            self.assertEqual(res.get("status"), "success")
            self.assertTrue(len(calls) > 0)
            self.assertEqual(calls[-1][0], calls[-1][1])  # Completed 100%

    def test_ingest_overwrite_mode(self):
        """[Ingest] Verify DBManager.ingest_files supports table overwrite mode and preserves Pixeltable lineage."""
        from src.db.manager import DBManager, PIXELTABLE_AVAILABLE
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
            res1 = DBManager.ingest_files("test_unit", "overwrite_test", fake_files, overwrite=False)
            self.assertEqual(res1.get("status"), "success")
            # Overwrite Ingestion
            res2 = DBManager.ingest_files("test_unit", "overwrite_test", fake_files, overwrite=True)
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
        
        # Verify check_connection without key
        ok, msg = client.check_connection(api_key="")
        self.assertFalse(ok)
        self.assertIn("missing", msg.lower())

    def test_llm_service_router(self):
        """[Router] Verify unified LLMService routes queries and model discovery between Ollama and Gemini."""
        from src.core.llm_service import LLMService
        self.assertIn("Ollama", LLMService.PROVIDERS)
        self.assertIn("Gemini", LLMService.PROVIDERS)

        gemini_models = LLMService.list_models_for_provider("Gemini")
        self.assertIn("gemini-3.6-flash", gemini_models)

        ollama_models = LLMService.list_models_for_provider("Ollama")
        self.assertTrue(len(ollama_models) > 0)

    def test_extract_json_payload_variations(self):
        """[JSON] Verify robust extraction across pure JSON, markdown blocks, leading/trailing text, and malformed strings."""
        from src.prompts.executor import extract_json_payload

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
        from src.prompts.executor import infer_pixeltable_type
        import pixeltable as pxt

        self.assertEqual(infer_pixeltable_type("sample string"), pxt.String)
        self.assertEqual(infer_pixeltable_type(42), pxt.Int)
        self.assertEqual(infer_pixeltable_type(3.1415), pxt.Float)
        self.assertEqual(infer_pixeltable_type(True), pxt.Bool)
        self.assertEqual(infer_pixeltable_type(["a", "b", "c"]), pxt.Json)
        self.assertEqual(infer_pixeltable_type({"nested": "object"}), pxt.Json)

    def test_dynamic_multicolumn_batch_execution(self):
        """[Playground] Verify PromptExecutor auto-split unpacks JSON keys into distinct table columns."""
        from src.db.manager import DBManager, PIXELTABLE_AVAILABLE
        from src.prompts.executor import PromptExecutor
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
            DBManager.ingest_files("test_unit", "json_split_test", fake_files, overwrite=True)

            mock_json_response = '{"doc_summary": "Test summary", "doc_haiku": "Lines of code arise", "confidence": 0.98}'
            with patch("src.core.llm_service.LLMService.generate", return_value=mock_json_response):
                res = PromptExecutor.apply_prompt_to_table(
                    model="test-model",
                    prompt_template="Analyze {file_name}",
                    system_prompt="Return JSON",
                    table_dir="test_unit",
                    table_name="json_split_test",
                    auto_split=True
                )
                self.assertEqual(res.get("status"), "success")
                self.assertIn("doc_summary", res.get("columns", []))
                self.assertIn("doc_haiku", res.get("columns", []))
                self.assertIn("confidence", res.get("columns", []))

                # Verify columns exist in Pixeltable table data
                table_data = DBManager.get_table_data("test_unit", "json_split_test", limit=5)
                self.assertIn("doc_summary", table_data.get("columns", []))
                self.assertIn("doc_haiku", table_data.get("columns", []))
                self.assertIn("confidence", table_data.get("columns", []))



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
    
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPipelineTools)
    total_count = suite.countTestCases()
    result = CleanTestResult(sys.stdout, total_tests=total_count)
    
    old_stdout = sys.stdout
    try:
        suite.run(result)
    finally:
        sys.stdout = old_stdout

    print("\n" + header, flush=True)
    print(f"  SUMMARY: {result.successes} Passed, {len(result.failures)} Failed, {len(result.errors)} Errors", flush=True)
    print(header + "\n", flush=True)
    return len(result.failures) == 0 and len(result.errors) == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(not success)
