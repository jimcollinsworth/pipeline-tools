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
    attach_spectrogram_columns,
    compute_mfcc_core,
    render_mfcc_image_core,
    compute_mfcc,
    render_mfcc_image,
    attach_mfcc_columns,
    compute_chroma_core,
    render_chroma_image_core,
    compute_chroma,
    render_chroma_image,
    attach_chroma_columns,
    compute_audio_stats_core,
    compute_audio_stats,
    attach_audio_stats_columns
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
        cls.domain = "pxt_tests"
        cls.table = "audio_assets"
        import pixeltable as pxt
        pxt.create_dir(cls.domain, if_exists="ignore")
        for tbl in [cls.table, "audio_custom_arrays"]:
            try:
                DBManager.drop_table(cls.domain, tbl)
            except Exception:
                pass

    @classmethod
    def tearDownClass(cls):
        try:
            DBManager.drop_table(cls.domain, cls.table)
        except Exception:
            pass
        try:
            DBManager.drop_table(cls.domain, "audio_custom_arrays")
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

    def test_12_compute_mfcc_direct(self):
        """[Audio] Verify compute_mfcc_core returns a 2D numpy array with n_mfcc coefficients."""
        mfcc = compute_mfcc_core(str(self.audio_file), n_mfcc=20)
        self.assertIsNotNone(mfcc)
        self.assertIsInstance(mfcc, np.ndarray)
        self.assertEqual(len(mfcc.shape), 2)
        self.assertEqual(mfcc.shape[0], 20)  # 20 coefficients
        self.assertGreater(mfcc.shape[1], 10)  # Time frames
        # Null safety
        self.assertIsNone(compute_mfcc_core(None))
        self.assertIsNone(compute_mfcc_core(str(self.text_file)))

    def test_13_render_mfcc_image_direct(self):
        """[Audio] Verify render_mfcc_image_core returns a valid PIL.Image with RGB mode."""
        img = render_mfcc_image_core(str(self.audio_file), colormap="plasma")
        self.assertIsNotNone(img)
        self.assertIsInstance(img, Image.Image)
        self.assertEqual(img.mode, "RGB")
        self.assertGreater(img.width, 100)
        self.assertGreater(img.height, 50)
        # Null safety
        self.assertIsNone(render_mfcc_image_core(None))
        self.assertIsNone(render_mfcc_image_core(str(self.text_file)))

    def test_14_compute_chroma_direct(self):
        """[Audio] Verify compute_chroma_core returns a 2D numpy array with 12 pitch classes."""
        chroma = compute_chroma_core(str(self.audio_file), n_chroma=12)
        self.assertIsNotNone(chroma)
        self.assertIsInstance(chroma, np.ndarray)
        self.assertEqual(len(chroma.shape), 2)
        self.assertEqual(chroma.shape[0], 12)  # 12 chroma bins
        self.assertGreater(chroma.shape[1], 10)
        # Null safety
        self.assertIsNone(compute_chroma_core(None))
        self.assertIsNone(compute_chroma_core(str(self.text_file)))

    def test_15_render_chroma_image_direct(self):
        """[Audio] Verify render_chroma_image_core returns a valid PIL.Image with RGB mode."""
        img = render_chroma_image_core(str(self.audio_file), colormap="coolwarm")
        self.assertIsNotNone(img)
        self.assertIsInstance(img, Image.Image)
        self.assertEqual(img.mode, "RGB")
        self.assertGreater(img.width, 100)
        self.assertGreater(img.height, 50)
        # Null safety
        self.assertIsNone(render_chroma_image_core(None))
        self.assertIsNone(render_chroma_image_core(str(self.text_file)))

    def test_16_compute_audio_stats_direct(self):
        """[Audio] Verify compute_audio_stats_core returns audio and noise summary metrics."""
        stats = compute_audio_stats_core(str(self.audio_file))
        self.assertIsNotNone(stats)
        self.assertIsInstance(stats, dict)
        self.assertIn("duration_sec", stats)
        self.assertAlmostEqual(stats["duration_sec"], 1.0, delta=0.1)
        self.assertEqual(stats["sample_rate"], 22050)
        self.assertIn("rms_mean", stats)
        self.assertIn("rms_std", stats)
        self.assertIn("zcr_mean", stats)
        self.assertIn("spectral_centroid_mean", stats)
        self.assertIn("spectral_rolloff_mean", stats)
        self.assertIn("silence_ratio", stats)
        self.assertGreater(stats["rms_mean"], 0.0)
        # Null safety
        self.assertIsNone(compute_audio_stats_core(None))
        self.assertIsNone(compute_audio_stats_core(str(self.text_file)))

    def test_17_attach_mfcc_chroma_stats_columns_and_query(self):
        """[Audio] Verify declarative attachment of MFCC, Chroma, and Audio Stats computed columns."""
        import pixeltable as pxt

        full_table_path = f"{self.domain}.{self.table}"
        tbl = pxt.get_table(full_table_path)

        res_mfcc = attach_mfcc_columns(self.domain, self.table)
        self.assertEqual(res_mfcc["status"], "success")
        self.assertIn("mfcc", res_mfcc["columns"])
        self.assertIn("mfcc_img", res_mfcc["columns"])

        res_chroma = attach_chroma_columns(self.domain, self.table)
        self.assertEqual(res_chroma["status"], "success")
        self.assertIn("chroma", res_chroma["columns"])
        self.assertIn("chroma_img", res_chroma["columns"])

        res_stats = attach_audio_stats_columns(self.domain, self.table)
        self.assertEqual(res_stats["status"], "success")
        self.assertIn("audio_stats", res_stats["columns"])

        # Fetch and verify data across rows
        rows = tbl.select(
            tbl.file_name, tbl.mfcc, tbl.mfcc_img, tbl.chroma, tbl.chroma_img, tbl.audio_stats
        ).collect()
        self.assertEqual(len(rows), 2)

        # Audio row
        audio_row = [r for r in rows if r["file_name"] == "test_tone.wav"][0]
        self.assertIsNotNone(audio_row["mfcc"])
        self.assertEqual(audio_row["mfcc"].shape[0], 20)
        self.assertIsNotNone(audio_row["mfcc_img"])
        self.assertIsInstance(audio_row["mfcc_img"], Image.Image)
        self.assertIsNotNone(audio_row["chroma"])
        self.assertEqual(audio_row["chroma"].shape[0], 12)
        self.assertIsNotNone(audio_row["chroma_img"])
        self.assertIsInstance(audio_row["chroma_img"], Image.Image)
        self.assertIsNotNone(audio_row["audio_stats"])
        self.assertIsInstance(audio_row["audio_stats"], dict)
        self.assertIn("duration_sec", audio_row["audio_stats"])

        # Non-audio row
        doc_row = [r for r in rows if r["file_name"] == "readme.txt"][0]
        self.assertIsNone(doc_row["mfcc"])
        self.assertIsNone(doc_row["mfcc_img"])
        self.assertIsNone(doc_row["chroma"])
        self.assertIsNone(doc_row["chroma_img"])
        self.assertIsNone(doc_row["audio_stats"])

    def test_18_udf_registry_matching_new_udfs(self):
        """[Audio] Verify UDFRegistry matches slash commands and natural language for mfcc, chroma, audio_stats."""
        from src.core.udf_registry import UDFRegistry

        # 1. MFCC slash command
        match_mfcc = UDFRegistry.match_prompt("/mfcc n_mfcc=13 colormap=viridis")
        self.assertIsNotNone(match_mfcc)
        udf_def, kwargs = match_mfcc
        self.assertEqual(udf_def.name, "mfcc")
        self.assertEqual(kwargs["n_mfcc"], 13)
        self.assertEqual(kwargs["colormap"], "viridis")

        # 2. Chroma natural language
        match_chroma = UDFRegistry.match_prompt("analyze pitch classes and chroma of {file_name}")
        self.assertIsNotNone(match_chroma)
        udf_def_c, kwargs_c = match_chroma
        self.assertEqual(udf_def_c.name, "chroma")
        self.assertEqual(kwargs_c["n_chroma"], 12)

        # 3. Audio stats slash command
        match_stats = UDFRegistry.match_prompt("/audio_stats hop_length=256")
        self.assertIsNotNone(match_stats)
        udf_def_s, kwargs_s = match_stats
        self.assertEqual(udf_def_s.name, "audio_stats")
        self.assertEqual(kwargs_s["hop_length"], 256)

    def test_19_udf_registry_generate_markdown_help(self):
        """[Audio] Verify UDFRegistry.generate_markdown_help contains all registered UDFs and parameters."""
        from src.core.udf_registry import UDFRegistry
        help_md = UDFRegistry.generate_markdown_help()
        self.assertIn("mel_spectrogram", help_md)
        self.assertIn("mfcc", help_md)
        self.assertIn("chroma", help_md)
        self.assertIn("audio_stats", help_md)
        self.assertIn("n_mfcc", help_md)
        self.assertIn("n_chroma", help_md)
        self.assertIn("duration", help_md.lower())
        self.assertIn("slash command", help_md.lower())

    def test_20_prompt_driven_mfcc_chroma_stats_sample_and_batch(self):
        """[Audio] Verify PlaygroundController executes sample tests and batch commits for MFCC, Chroma, Audio Stats."""
        from src.controllers.playground_controller import PlaygroundController

        # 1. Sample test with MFCC
        mfcc_sample = PlaygroundController.test_sample_flow(
            domain=self.domain,
            table_name=self.table,
            provider="Ollama",
            model="llama3.2",
            prompt_template="/mfcc n_mfcc=20 colormap=plasma",
            sample_count=2
        )
        self.assertEqual(mfcc_sample["status"], "success")
        self.assertIn("mfcc_img", mfcc_sample["headers"])
        self.assertTrue(mfcc_sample.get("is_udf", False))

        # 2. Sample test with Chroma
        chroma_sample = PlaygroundController.test_sample_flow(
            domain=self.domain,
            table_name=self.table,
            provider="Ollama",
            model="llama3.2",
            prompt_template="/chroma n_chroma=12 colormap=coolwarm",
            sample_count=2
        )
        self.assertEqual(chroma_sample["status"], "success")
        self.assertIn("chroma_img", chroma_sample["headers"])
        self.assertTrue(chroma_sample.get("is_udf", False))

        # 3. Sample test with Audio Stats
        stats_sample = PlaygroundController.test_sample_flow(
            domain=self.domain,
            table_name=self.table,
            provider="Ollama",
            model="llama3.2",
            prompt_template="/audio_stats",
            sample_count=2
        )
        self.assertEqual(stats_sample["status"], "success")
        self.assertIn("Duration (s)", stats_sample["headers"])
        self.assertTrue(stats_sample.get("is_udf", False))

    def test_21_isolated_row_inspection_with_arrays_and_labels(self):
        """[Audio] Verify handle_row_inspection safely processes 2D numpy arrays without crashing on boolean evaluation."""
        import pandas as pd
        dummy_spec = np.random.randn(128, 40).astype(np.float32)
        dummy_mfcc = np.random.randn(20, 40).astype(np.float32)
        dummy_chroma = np.random.randn(12, 40).astype(np.float32)

        # 1. Mel Spectrogram only (no _img column, nonexistent db to test pure DataFrame path)
        df_spec = pd.DataFrame([{"file_name": "test1.wav", "mel_spectrogram": dummy_spec}])
        insp_spec = TablesController.handle_row_inspection(0, df_spec, "isolated_domain", "isolated_table")
        self.assertTrue(insp_spec.get("has_spectrogram"))
        self.assertIn("Mel Spectrogram", insp_spec.get("spectrogram_label", ""))
        self.assertIsInstance(insp_spec.get("spectrogram_path"), Image.Image)

        # 2. MFCC only
        df_mfcc = pd.DataFrame([{"file_name": "test2.wav", "mfcc": dummy_mfcc}])
        insp_mfcc = TablesController.handle_row_inspection(0, df_mfcc, "isolated_domain", "isolated_table")
        self.assertTrue(insp_mfcc.get("has_spectrogram"))
        self.assertIn("MFCC", insp_mfcc.get("spectrogram_label", ""))
        self.assertIsInstance(insp_mfcc.get("spectrogram_path"), Image.Image)

        # 3. Chroma only
        df_chroma = pd.DataFrame([{"file_name": "test3.wav", "chroma": dummy_chroma}])
        insp_chroma = TablesController.handle_row_inspection(0, df_chroma, "isolated_domain", "isolated_table")
        self.assertTrue(insp_chroma.get("has_spectrogram"))
        self.assertIn("Chroma", insp_chroma.get("spectrogram_label", ""))
        self.assertIsInstance(insp_chroma.get("spectrogram_path"), Image.Image)

    def test_22_render_image_upscaling_and_colormap_fallback(self):
        """[Audio] Verify render_spectrogram_array_to_image upscales Chroma/MFCC height and falls back gracefully on invalid colormap."""
        from src.audio.spectrogram import render_spectrogram_array_to_image

        # 1. Chroma array: 12 rows, 300 time frames
        chroma_arr = np.random.randn(12, 300).astype(np.float32)
        img_chroma = render_spectrogram_array_to_image(chroma_arr, colormap="coolwarm")
        self.assertIsNotNone(img_chroma)
        self.assertGreaterEqual(img_chroma.height, 256)
        self.assertGreaterEqual(img_chroma.width, 300)

        # 2. MFCC array: 20 rows, 50 time frames
        mfcc_arr = np.random.randn(20, 50).astype(np.float32)
        img_mfcc = render_spectrogram_array_to_image(mfcc_arr, colormap="plasma")
        self.assertIsNotNone(img_mfcc)
        self.assertGreaterEqual(img_mfcc.height, 256)
        self.assertGreaterEqual(img_mfcc.width, 512)

        # 3. Invalid colormap fallback
        img_fallback = render_spectrogram_array_to_image(chroma_arr, colormap="invalid_colormap_name_123")
        self.assertIsNotNone(img_fallback)
        self.assertIsInstance(img_fallback, Image.Image)

    def test_23_dbmanager_custom_array_and_datatype_detection(self):
        """[Audio] Verify DBManager renders custom 2D array shapes and detects html datatypes for mfcc/chroma."""
        import pixeltable as pxt

        table_path = f"{self.domain}.audio_custom_arrays"
        schema = {
            "file_name": pxt.String,
            "mfcc_custom": pxt.Array,
            "chroma_custom": pxt.Array
        }
        tbl = pxt.create_table(table_path, schema=schema, if_exists="replace")

        # Insert 1 row with empty/non-audio values and 1 row with custom array shapes (25, 50)
        tbl.insert([
            {"file_name": "empty_row.txt", "mfcc_custom": None, "chroma_custom": None},
            {"file_name": "custom.wav", "mfcc_custom": np.random.randn(25, 50).astype(np.float32), "chroma_custom": np.random.randn(12, 50).astype(np.float32)}
        ])

        res = DBManager.get_table_data(self.domain, "audio_custom_arrays", limit=10, lightweight=False)
        cols = res["columns"]
        datatypes = res["datatypes"]
        data = res["data"]

        # Verify mfcc_custom and chroma_custom columns are detected as 'html' datatypes
        mfcc_idx = cols.index("mfcc_custom")
        chroma_idx = cols.index("chroma_custom")
        self.assertEqual(datatypes[mfcc_idx], "html")
        self.assertEqual(datatypes[chroma_idx], "html")

        # Verify row 1 contains rendered HTML <img>
        self.assertIn("<img", data[1][mfcc_idx])
        self.assertIn("<img", data[1][chroma_idx])

        # Cleanup
        try:
            DBManager.drop_table(self.domain, "audio_custom_arrays")
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main()
