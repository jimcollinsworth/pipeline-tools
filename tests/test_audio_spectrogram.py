import os
import sys
import unittest
import tempfile
import numpy as np
import soundfile as sf
from pathlib import Path
from PIL import Image

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.manager import DBManager
from src.audio.spectrogram import (
    compute_mel_spectrogram,
    render_mel_spectrogram_image,
    compute_mel_spectrogram_core,
    render_mel_spectrogram_image_core,
    attach_spectrogram_columns
)
from src.controllers.tables_controller import TablesController


class TestAudioMelSpectrogram(unittest.TestCase):
    """[Audio] Test-Driven Development suite for declarative Mel Spectrogram extraction."""

    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.TemporaryDirectory()
        cls.test_path = Path(cls.test_dir.name)

        # 1. Create a synthetic 1.0s 440 Hz audio tone WAV
        sample_rate = 22050
        duration = 1.0
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        audio_data = 0.5 * np.sin(2 * np.pi * 440.0 * t)
        
        cls.audio_file = cls.test_path / "test_tone.wav"
        sf.write(str(cls.audio_file), audio_data, sample_rate)

        # 2. Create a non-audio dummy text file for mixed-modality null testing
        cls.text_file = cls.test_path / "readme.txt"
        cls.text_file.write_text("This is not an audio file.", encoding="utf-8")

        # 3. Setup test database domain and table
        cls.domain = "test_audio_suite"
        cls.table = "audio_assets"
        import pixeltable as pxt
        pxt.create_dir(cls.domain, if_exists="ignore")

    @classmethod
    def tearDownClass(cls):
        try:
            DBManager.delete_table(cls.domain, cls.table)
        except Exception:
            pass
        cls.test_dir.cleanup()

    def test_01_compute_mel_spectrogram_direct(self):
        """[Audio] Verify compute_mel_spectrogram returns a 2D numpy array with 128 mel frequency bins."""
        spec = compute_mel_spectrogram_core(str(self.audio_file))
        self.assertIsNotNone(spec)
        self.assertIsInstance(spec, np.ndarray)
        self.assertEqual(len(spec.shape), 2)
        self.assertEqual(spec.shape[0], 128)  # 128 mel bins
        self.assertGreater(spec.shape[1], 10)  # Time frames

    def test_02_render_mel_spectrogram_image_direct(self):
        """[Audio] Verify render_mel_spectrogram_image returns a valid PIL.Image.Image with RGB mode."""
        img = render_mel_spectrogram_image_core(str(self.audio_file))
        self.assertIsNotNone(img)
        self.assertIsInstance(img, Image.Image)
        self.assertEqual(img.mode, "RGB")
        self.assertGreater(img.width, 100)
        self.assertGreater(img.height, 50)

    def test_03_null_safety_on_non_audio(self):
        """[Audio] Verify both UDFs return None cleanly when given None or a non-audio path."""
        self.assertIsNone(compute_mel_spectrogram_core(None))
        self.assertIsNone(render_mel_spectrogram_image_core(None))
        self.assertIsNone(compute_mel_spectrogram_core(str(self.text_file)))
        self.assertIsNone(render_mel_spectrogram_image_core(str(self.text_file)))

    def test_04_attach_spectrogram_columns_and_query(self):
        """[Audio] Verify declarative attach_spectrogram_columns adds computed columns to Pixeltable table."""
        import pixeltable as pxt

        full_table_path = f"{self.domain}.{self.table}"
        
        # Create base table schema if not exists
        schema = {
            "file_name": pxt.String,
            "modality": pxt.String,
            "audio": pxt.Audio,
        }
        tbl = pxt.create_table(full_table_path, schema=schema, if_exists="replace")

        # Insert 1 audio row and 1 non-audio row
        tbl.insert([
            {"file_name": "test_tone.wav", "modality": "audio", "audio": str(self.audio_file)},
            {"file_name": "readme.txt", "modality": "document", "audio": None}
        ])

        # Attach computed columns
        res = attach_spectrogram_columns(self.domain, self.table)
        self.assertEqual(res["status"], "success")
        self.assertIn("mel_spectrogram", res["columns"])
        self.assertIn("mel_spectrogram_img", res["columns"])

        # Fetch and verify data
        rows = tbl.select(tbl.file_name, tbl.mel_spectrogram, tbl.mel_spectrogram_img).collect()
        self.assertEqual(len(rows), 2)

        # Row 0 (audio)
        audio_row = [r for r in rows if r["file_name"] == "test_tone.wav"][0]
        self.assertIsNotNone(audio_row["mel_spectrogram"])
        self.assertIsInstance(audio_row["mel_spectrogram"], np.ndarray)
        self.assertEqual(audio_row["mel_spectrogram"].shape[0], 128)
        self.assertIsNotNone(audio_row["mel_spectrogram_img"])
        self.assertIsInstance(audio_row["mel_spectrogram_img"], Image.Image)

        # Row 1 (non-audio)
        doc_row = [r for r in rows if r["file_name"] == "readme.txt"][0]
        self.assertIsNone(doc_row["mel_spectrogram"])
        self.assertIsNone(doc_row["mel_spectrogram_img"])

    def test_05_media_inspector_detects_spectrogram_image(self):
        """[Audio] Verify TablesController detects mel_spectrogram_img in row inspection."""
        import pandas as pd
        df = pd.DataFrame([
            {
                "file_name": "test_tone.wav",
                "audio": str(self.audio_file),
                "mel_spectrogram_img": str(self.test_path / "spec_preview.png")
            }
        ])
        
        # Save a dummy image to test file resolution
        Image.new("RGB", (64, 64), color="blue").save(self.test_path / "spec_preview.png")

        insp = TablesController.handle_row_inspection(0, df, self.domain, self.table)
        self.assertTrue(insp.get("has_spectrogram", False))
        self.assertIsNotNone(insp.get("spectrogram_path"))

    def test_06_load_audio_pyav_direct(self):
        """[Audio] Verify load_audio_pyav decodes audio file into a 1D float32 mono array."""
        from src.audio.spectrogram import load_audio_pyav
        arr = load_audio_pyav(str(self.audio_file), target_sr=22050)
        self.assertIsNotNone(arr)
        self.assertIsInstance(arr, np.ndarray)
        self.assertEqual(arr.dtype, np.float32)
        self.assertGreater(len(arr), 1000)

    def test_07_udf_registry_matching_and_params(self):
        """[Audio] Verify UDFRegistry matches slash commands and natural language prompts with parameter overrides."""
        from src.core.udf_registry import UDFRegistry
        
        # 1. Slash command
        match_slash = UDFRegistry.match_prompt("/mel_spectrogram hop_length=256 colormap=viridis")
        self.assertIsNotNone(match_slash)
        udf_def, kwargs = match_slash
        self.assertEqual(udf_def.name, "mel_spectrogram")
        self.assertEqual(kwargs["hop_length"], 256)
        self.assertEqual(kwargs["colormap"], "viridis")

        # 2. Natural language prompt
        match_nl = UDFRegistry.match_prompt("please generate mel spectrograph of {file_name} n_mels=64")
        self.assertIsNotNone(match_nl)
        udf_def2, kwargs2 = match_nl
        self.assertEqual(udf_def2.name, "mel_spectrogram")
        self.assertEqual(kwargs2["n_mels"], 64)

        # 3. Non-UDF prompt returns None
        self.assertIsNone(UDFRegistry.match_prompt("Summarize the text in {content}"))

    def test_08_prompt_driven_udf_sample_and_batch(self):
        """[Audio] Verify PlaygroundController executes UDF sample tests and batch commits via prompt."""
        from src.controllers.playground_controller import PlaygroundController
        
        # Test sample flow with UDF prompt
        sample_res = PlaygroundController.test_sample_flow(
            domain=self.domain,
            table_name=self.table,
            provider="Ollama",
            model="llama3.2",
            prompt_template="/mel_spectrogram hop_length=256 colormap=plasma",
            sample_count=2
        )
        self.assertEqual(sample_res["status"], "success")
        self.assertIn("mel_spectrogram_img", sample_res["headers"])
        self.assertTrue(sample_res.get("is_udf", False))

        # Test batch commit with UDF prompt
        batch_res = PlaygroundController.commit_batch_flow(
            domain=self.domain,
            table_name=self.table,
            provider="Ollama",
            model="llama3.2",
            prompt_template="mel spectrogram of {file_name}"
        )
        self.assertEqual(batch_res["status"], "success")
        self.assertIn("mel_spectrogram", batch_res["columns_created"])
        self.assertIn("mel_spectrogram_img", batch_res["columns_created"])

    def test_09_db_manager_renders_pil_image_in_get_table_data(self):
        """[Audio] Verify DBManager.get_table_data renders PIL Images as HTML img tags with data URIs."""
        res = DBManager.get_table_data(self.domain, self.table, limit=5, lightweight=False)
        self.assertIn("mel_spectrogram_img", res["columns"])
        spec_idx = res["columns"].index("mel_spectrogram_img")
        self.assertEqual(res["datatypes"][spec_idx], "html")
        
        # Check that audio row has an HTML img tag with data URI
        audio_row = [r for r in res["data"] if r[res["columns"].index("file_name")] == "test_tone.wav"][0]
        img_cell = audio_row[spec_idx]
        self.assertTrue(img_cell.startswith("<img") and "data:image" in img_cell)

    def test_10_render_spectrogram_array_to_image(self):
        """[Audio] Verify render_spectrogram_array_to_image converts 2D numpy array to valid PIL Image."""
        from src.audio.spectrogram import render_spectrogram_array_to_image
        dummy_spec = np.random.randn(128, 40).astype(np.float32)
        img = render_spectrogram_array_to_image(dummy_spec, colormap="magma")
        self.assertIsNotNone(img)
        self.assertIsInstance(img, Image.Image)
        self.assertEqual(img.mode, "RGB")
        self.assertGreaterEqual(img.width, 256)

    def test_11_handle_row_inspection_with_numpy_array(self):
        """[Audio] Verify TablesController detects and renders 2D numpy array in row inspection."""
        import pandas as pd
        dummy_spec = np.random.randn(128, 40).astype(np.float32)
        df = pd.DataFrame([
            {
                "file_name": "test_tone.wav",
                "audio": str(self.audio_file),
                "mel_spectrogram": dummy_spec
            }
        ])
        insp = TablesController.handle_row_inspection(0, df, self.domain, self.table)
        self.assertTrue(insp.get("has_spectrogram", False))
        self.assertTrue(isinstance(insp.get("spectrogram_path"), (Image.Image, str)))


if __name__ == "__main__":
    unittest.main()
