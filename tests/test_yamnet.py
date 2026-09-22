"""
Tests for YAMNet Audio Classification and Declarative Pixeltable UDFs
=====================================================================
Validates YAMNet asset management, waveform formatting, inference,
UDFRegistry integration, dry-run sample preview, and declarative batch attachment.
"""

import os
import unittest
import tempfile
import numpy as np
import soundfile as sf
from pathlib import Path
from PIL import Image

import pixeltable as pxt
from src.db.manager import DBManager
from src.audio.yamnet import (
    ensure_yamnet_assets,
    load_yamnet_classes,
    load_yamnet_waveform,
    classify_audio_yamnet_core,
    get_yamnet_primary_category_core,
    get_yamnet_sound_events_core,
    get_yamnet_scores_core,
    attach_yamnet_columns,
    yamnet_primary_category,
    yamnet_sound_events,
    yamnet_scores
)
from src.core.udf_registry import UDFRegistry
from src.controllers.playground_controller import PlaygroundController


class TestYAMNet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Initialize test audio fixtures and Pixeltable test domain."""
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.test_path = Path(cls.temp_dir.name)
        cls.domain = "pxt_tests"
        cls.table = "yamnet_audio_test"

        # 1. Generate 1.0s 440 Hz test tone at 16000 Hz
        cls.audio_file = cls.test_path / "test_tone_440hz.wav"
        sr = 16000
        t = np.linspace(0, 1.0, sr, endpoint=False)
        y = 0.5 * np.sin(2 * np.pi * 440 * t)
        sf.write(str(cls.audio_file), y, sr)

        # 2. Generate dummy text file for non-audio testing
        cls.text_file = cls.test_path / "readme.txt"
        cls.text_file.write_text("This is a plain text file, not audio.", encoding="utf-8")

        # 3. Create clean Pixeltable test table under pxt_tests
        pxt.create_dir(cls.domain, if_exists="ignore")
        full_table = f"{cls.domain}.{cls.table}"
        try:
            pxt.drop_table(full_table, force=True)
        except Exception:
            pass

        schema = {
            "file_name": pxt.String,
            "file_path": pxt.String,
            "modality": pxt.String,
            "audio": pxt.Audio
        }
        tbl = pxt.create_table(full_table, schema=schema, if_exists="replace")
        tbl.insert([
            {
                "file_name": "test_tone_440hz.wav",
                "file_path": str(cls.audio_file),
                "modality": "audio",
                "audio": str(cls.audio_file)
            },
            {
                "file_name": "readme.txt",
                "file_path": str(cls.text_file),
                "modality": "document",
                "audio": None
            }
        ])

    @classmethod
    def tearDownClass(cls):
        """Cleanup temporary directory and test table."""
        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass
        try:
            pxt.drop_table(f"{cls.domain}.{cls.table}", force=True)
        except Exception:
            pass

    def test_01_yamnet_assets_and_class_map(self):
        """[YAMNet] Verify ONNX model and 521-class taxonomy map are loaded and cached."""
        model_path, csv_path = ensure_yamnet_assets()
        self.assertTrue(model_path.exists())
        self.assertGreater(model_path.stat().st_size, 10_000_000)
        self.assertTrue(csv_path.exists())

        classes = load_yamnet_classes()
        self.assertEqual(len(classes), 521)
        self.assertEqual(classes[0], "Speech")

    def test_02_load_yamnet_waveform(self):
        """[YAMNet] Verify waveform loading resamples to 16 kHz mono float32 with normalization."""
        wave = load_yamnet_waveform(str(self.audio_file))
        self.assertIsNotNone(wave)
        self.assertIsInstance(wave, np.ndarray)
        self.assertEqual(wave.dtype, np.float32)
        self.assertEqual(wave.ndim, 1)
        self.assertGreaterEqual(len(wave), 16000)
        self.assertLessEqual(float(np.max(np.abs(wave))), 1.0)

        # Null safety
        self.assertIsNone(load_yamnet_waveform(None))
        self.assertIsNone(load_yamnet_waveform(str(self.text_file)))

    def test_03_classify_audio_yamnet_core(self):
        """[YAMNet] Verify inference classifies 440 Hz audio with confidence scores and top-k."""
        res = classify_audio_yamnet_core(str(self.audio_file), top_k=5)
        self.assertIsNotNone(res)
        self.assertIn("primary_category", res)
        self.assertIn("primary_confidence", res)
        self.assertIn("sound_events", res)
        self.assertIn("top_scores", res)
        self.assertGreater(res["primary_confidence"], 0.5)
        self.assertLessEqual(len(res["top_scores"]), 5)

        # Scalar extractors
        prim = get_yamnet_primary_category_core(str(self.audio_file))
        self.assertEqual(prim, res["primary_category"])

        events = get_yamnet_sound_events_core(str(self.audio_file), top_k=3)
        self.assertIn(prim, events)

        scores = get_yamnet_scores_core(str(self.audio_file), top_k=3)
        self.assertIsInstance(scores, dict)
        self.assertEqual(len(scores), 3)

    def test_04_udf_registry_matching_and_markdown_help(self):
        """[YAMNet] Verify UDFRegistry matches slash commands and natural language triggers for yamnet."""
        # Slash command
        match_slash = UDFRegistry.match_prompt("/yamnet top_k=3 min_confidence=0.1")
        self.assertIsNotNone(match_slash)
        udf_def, kwargs = match_slash
        self.assertEqual(udf_def.name, "yamnet")
        self.assertEqual(kwargs["top_k"], 3)
        self.assertEqual(kwargs["min_confidence"], 0.1)

        # Natural language trigger
        match_nl = UDFRegistry.match_prompt("classify audio events and sound scene in {file_name}")
        self.assertIsNotNone(match_nl)
        self.assertEqual(match_nl[0].name, "yamnet")

        # Documentation help contains yamnet
        help_md = UDFRegistry.generate_markdown_help()
        self.assertIn("yamnet", help_md)
        self.assertIn("sound_category", help_md)
        self.assertIn("sound_events", help_md)
        self.assertIn("sound_scores", help_md)

    def test_05_declarative_udf_functions(self):
        """[YAMNet] Verify declarative Pixeltable UDFs return valid types."""
        # Non-audio row returns None
        self.assertIsNone(get_yamnet_primary_category_core(None))
        self.assertIsNone(get_yamnet_sound_events_core(None))
        self.assertIsNone(get_yamnet_scores_core(None))

    def test_06_sample_flow_preview_and_no_shape_columns(self):
        """[YAMNet] Verify PlaygroundController test_sample_flow returns clean headers without shape columns."""
        res = PlaygroundController.test_sample_flow(
            domain=self.domain,
            table_name=self.table,
            provider="Ollama",
            model="llama3.2",
            prompt_template="/yamnet top_k=3",
            sample_count=2
        )
        self.assertEqual(res["status"], "success")
        headers = res["headers"]
        data = res["data"]
        datatypes = res["datatypes"]

        # Expected clean headers
        self.assertEqual(headers, ["Status", "Row ID", "File Name", "Primary Sound", "Top Sound Events"])
        self.assertEqual(len(headers), len(datatypes))

        # Guarantee NO shape columns exist
        for h in headers:
            self.assertFalse("shape" in h.lower(), f"Unexpected shape column in headers: {h}")

        # Uniform row lengths
        for row in data:
            self.assertEqual(len(row), len(headers))

        # Audio row contains detected sound
        audio_row = [r for r in data if r[2] == "test_tone_440hz.wav"][0]
        self.assertNotEqual(audio_row[3], "—")
        self.assertIn("%", audio_row[4])

    def test_07_attach_yamnet_columns_batch(self):
        """[YAMNet] Verify attach_yamnet_columns declaratively attaches sound_category, sound_events, and sound_scores."""
        res = attach_yamnet_columns(self.domain, self.table, top_k=3)
        self.assertEqual(res["status"], "success")
        cols = res.get("columns", [])
        self.assertIn("sound_category", cols)
        self.assertIn("sound_events", cols)
        self.assertIn("sound_scores", cols)

        # Verify table has computed columns
        full_table = f"{self.domain}.{self.table}"
        tbl = pxt.get_table(full_table)
        tbl_cols = list(tbl.columns()) if callable(tbl.columns) else list(tbl._schema.keys())
        self.assertIn("sound_category", tbl_cols)
        self.assertIn("sound_events", tbl_cols)
        self.assertIn("sound_scores", tbl_cols)

        # Verify queries over computed columns
        rows = tbl.select(tbl.file_name, tbl.sound_category, tbl.sound_events, tbl.sound_scores).collect()
        audio_r = [r for r in rows if r["file_name"] == "test_tone_440hz.wav"][0]
        self.assertIsNotNone(audio_r["sound_category"])
        self.assertIsNotNone(audio_r["sound_events"])
        self.assertIsInstance(audio_r["sound_scores"], dict)

        doc_r = [r for r in rows if r["file_name"] == "readme.txt"][0]
        self.assertIsNone(doc_r["sound_category"])
        self.assertIsNone(doc_r["sound_events"])
        self.assertIsNone(doc_r["sound_scores"])

    def test_08_multi_udf_sample_flow_with_yamnet_and_mel(self):
        """[YAMNet] Verify multi-UDF sample preview combines YAMNet and Mel Spectrogram with uniform rows and zero shape columns."""
        res = PlaygroundController.test_sample_flow(
            domain=self.domain,
            table_name=self.table,
            provider="Ollama",
            model="llama3.2",
            prompt_template="yamnet and mel_spectrogram for {file_name}",
            sample_count=2
        )
        self.assertEqual(res["status"], "success")
        headers = res["headers"]
        data = res["data"]
        datatypes = res["datatypes"]

        # Verify expected columns
        self.assertIn("Primary Sound", headers)
        self.assertIn("Top Sound Events", headers)
        self.assertIn("mel_spectrogram_img", headers)

        # Guarantee NO shape columns anywhere
        for h in headers:
            self.assertFalse("shape" in h.lower(), f"Unexpected shape column in multi-UDF headers: {h}")

        # Uniform row lengths
        self.assertEqual(len(headers), len(datatypes))
        for row in data:
            self.assertEqual(len(row), len(headers))


if __name__ == "__main__":
    unittest.main()
