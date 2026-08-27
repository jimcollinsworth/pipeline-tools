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
from app import create_app

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


class CleanTestResult(unittest.TestResult):
    """Custom TestResult that captures noise and formats clean visual separators between tests."""

    def __init__(self, stream):
        super().__init__()
        self.stream = stream
        self.test_start_time = None
        self.test_count = 0
        self.successes = 0

    def startTest(self, test):
        self.test_count += 1
        self.test_start_time = time.time()
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
        self.stream.write(f"  [{self.test_count}/8] PASS ({elapsed:.3f}s)  {doc}\n")
        self.stream.write("  " + "-" * 72 + "\n")

    def addError(self, test, err):
        super().addError(test, err)
        elapsed = time.time() - (self.test_start_time or time.time())
        doc = test._testMethodDoc or test.id()
        self.stream.write(f"\n  [{self.test_count}/8] ERROR ({elapsed:.3f}s)  {doc}\n")
        self.stream.write("  " + "-" * 72 + "\n")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        elapsed = time.time() - (self.test_start_time or time.time())
        doc = test._testMethodDoc or test.id()
        self.stream.write(f"\n  [{self.test_count}/8] FAIL ({elapsed:.3f}s)  {doc}\n")
        self.stream.write("  " + "-" * 72 + "\n")


def run_tests():
    header = "=" * 76
    print("\n" + header)
    print("  PIPELINE TOOLS AUTOMATED TEST SUITE")
    print(header + "\n")
    
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPipelineTools)
    result = CleanTestResult(sys.stdout)
    
    # Silence stdout during suite execution so module imports don't print to console
    old_stdout = sys.stdout
    try:
        suite.run(result)
    finally:
        sys.stdout = old_stdout

    print("\n" + header)
    print(f"  SUMMARY: {result.successes} Passed, {len(result.failures)} Failed, {len(result.errors)} Errors")
    print(header + "\n")
    return len(result.failures) == 0 and len(result.errors) == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(not success)
