import unittest
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import get_settings, Settings
from src.core.ollama_client import OllamaClient
from src.ingest.scanner import scan_directory, classify_modality
from app import create_app

class TestAppLoad(unittest.TestCase):
    def test_settings_load(self):
        settings = get_settings()
        self.assertIsInstance(settings, Settings)
        self.assertTrue(len(settings.ollama_host) > 0)

    def test_modality_classification(self):
        self.assertEqual(classify_modality(".pdf"), "docs")
        self.assertEqual(classify_modality(".md"), "docs")
        self.assertEqual(classify_modality(".png"), "images")
        self.assertEqual(classify_modality(".mp3"), "audio")
        self.assertEqual(classify_modality(".mp4"), "video")

    def test_scanner_on_project_dir(self):
        # Scan src folder
        files = scan_directory("src", recursive=True)
        self.assertTrue(len(files) > 0)
        self.assertTrue(any(f["name"] == "config.py" for f in files))

    def test_gradio_app_initialization(self):
        demo = create_app()
        self.assertIsNotNone(demo)
        self.assertTrue(hasattr(demo, "launch"))

    def test_pixeltable_manager_and_columns(self):
        from src.db.manager import DBManager, PIXELTABLE_AVAILABLE
        if PIXELTABLE_AVAILABLE:
            table = DBManager.get_or_create_table("test_unit", "assets")
            self.assertIsNotNone(table)
            cols = list(table.columns())
            self.assertIn("file_name", cols)
            self.assertIn("content", cols)
            
            # Test getting data
            res = DBManager.get_table_data("test_unit", "assets", limit=5)
            self.assertIn("columns", res)
            self.assertTrue(isinstance(res["columns"], list))

    def test_sanitization(self):
        from src.core.config import sanitize_identifier
        # Test leading digit
        ok, clean, msg = sanitize_identifier("123_table")
        self.assertTrue(ok)
        self.assertTrue(clean.startswith("t_"))
        
        # Test dashes
        ok, clean, msg = sanitize_identifier("my-table-name")
        self.assertTrue(ok)
        self.assertEqual(clean, "my_table_name")

    def test_table_path_resolution(self):
        from src.db.manager import DBManager
        # Test bare table name
        self.assertEqual(DBManager.resolve_table_path("eba", "raw_files_test"), "eba.raw_files_test")
        # Test prefixed table name like 'eba/raw_files_test' or 'eba.raw_files_test'
        self.assertEqual(DBManager.resolve_table_path("eba", "eba/raw_files_test"), "eba.raw_files_test")
        self.assertEqual(DBManager.resolve_table_path("eba", "eba.raw_files_test"), "eba.raw_files_test")
        # Test list_tables returns bare names
        tables = DBManager.list_tables("eba")
        for t in tables:
            self.assertFalse("/" in t, f"Table name should be bare without slashes: {t}")

    def test_extract_file_content(self):
        from src.db.manager import DBManager
        # Test markdown text extraction
        sample_md = Path("planning.md")
        if sample_md.exists():
            text = DBManager.extract_file_content(str(sample_md), "docs", ".md")
            self.assertTrue(len(text) > 0)
            self.assertIn("Pipeline Tools", text)

if __name__ == "__main__":
    unittest.main()




