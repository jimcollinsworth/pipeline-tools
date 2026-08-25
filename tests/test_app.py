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

if __name__ == "__main__":
    unittest.main()
