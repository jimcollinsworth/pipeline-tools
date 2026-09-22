"""
Unit & Integration Tests for Multimodal Segmentation & Chunking
================================================================
Tests SegmenterRegistry, prompt matching, parameter parsing, dry-run preview,
and declarative Pixeltable view creation for text, document, audio, and video.
"""

import unittest
import os
import sys
import shutil
from pathlib import Path
import numpy as np

# Suppress third-party warnings
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import get_settings, sanitize_identifier
from src.db.manager import DBManager, PIXELTABLE_AVAILABLE
from src.core.segmenter_registry import SegmenterRegistry, SegmenterDefinition
from src.controllers.segmentation_controller import SegmentationController

try:
    import pixeltable as pxt
except ImportError:
    pxt = None


class TestSegmentation(unittest.TestCase):
    """Test suite for declarative segmentation, prompt matching, preview, and view creation."""

    TEST_DOMAIN = "test_seg_isolated"

    @classmethod
    def setUpClass(cls):
        DBManager.heal_postgres_locks(force_purge_orphans=False)
        cls.test_dir = Path("tests/fixtures/test_seg_media")
        cls.test_dir.mkdir(parents=True, exist_ok=True)

        # Generate small synthetic test audio file (.wav, 3.0 seconds)
        cls.audio_file = cls.test_dir / "test_segment_audio.wav"
        sr = 16000
        t = np.linspace(0, 3.0, int(sr * 3.0))
        sine_wave = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        import soundfile as sf
        sf.write(str(cls.audio_file), sine_wave, sr)

        # Generate small synthetic test PDF file (2 pages)
        cls.pdf_file = cls.test_dir / "test_segment_doc.pdf"
        try:
            import fitz
            doc = fitz.open()
            p1 = doc.new_page()
            p1.insert_text((50, 72), "Page 1: Overview of multimodal pipelines.")
            p2 = doc.new_page()
            p2.insert_text((50, 72), "Page 2: Detailed segmentation and chunking.")
            doc.save(str(cls.pdf_file))
            doc.close()
        except Exception:
            pass

        # Generate small synthetic test video file (.mp4, 20 frames)
        cls.video_file = cls.test_dir / "test_segment_video.mp4"
        try:
            import av
            container = av.open(str(cls.video_file), mode='w')
            stream = container.add_stream('libx264', rate=10)
            stream.width = 64
            stream.height = 64
            stream.pix_fmt = 'yuv420p'
            for i in range(20):
                img = np.zeros((64, 64, 3), dtype=np.uint8)
                img[:, :, 0] = i * 12
                frame = av.VideoFrame.from_ndarray(img, format='rgb24')
                for packet in stream.encode(frame):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)
            container.close()
        except Exception:
            pass

        # Clean any leftover test directory
        if PIXELTABLE_AVAILABLE and pxt:
            try:
                DBManager.drop_dir(cls.TEST_DOMAIN, force=True)
            except Exception:
                pass

    @classmethod
    def tearDownClass(cls):
        if PIXELTABLE_AVAILABLE and pxt:
            try:
                DBManager.drop_dir(cls.TEST_DOMAIN, force=True)
            except Exception:
                pass
        if cls.test_dir.exists():
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_01_registry_discovery(self):
        """[Segmentation] Verify all 5 core segmenters are registered with valid schemas."""
        segmenters = SegmenterRegistry.list_segmenters()
        names = [s.name for s in segmenters]
        self.assertIn("split_pages", names)
        self.assertIn("split_paragraphs", names)
        self.assertIn("split_sentences", names)
        self.assertIn("split_audio", names)
        self.assertIn("extract_frames", names)

        for s in segmenters:
            self.assertTrue(len(s.aliases) > 0)
            self.assertTrue(len(s.description) > 0)
            self.assertIn(s.modality, ["document", "text", "audio", "video"])
            self.assertTrue(callable(s.create_iterator_fn))
            self.assertTrue(callable(s.preview_fn))

    def test_02_prompt_matching_slash_commands(self):
        """[Segmentation] Verify slash commands and parameter overrides are correctly parsed."""
        # Split pages
        match = SegmenterRegistry.match_prompt("/split_pages metadata=page elements=text image_dpi=150")
        self.assertIsNotNone(match)
        seg, kwargs = match
        self.assertEqual(seg.name, "split_pages")
        self.assertEqual(kwargs.get("metadata"), "page")
        self.assertEqual(kwargs.get("elements"), "text")
        self.assertEqual(kwargs.get("image_dpi"), 150)

        # Split audio
        match_audio = SegmenterRegistry.match_prompt("/split_audio duration=15.0 overlap=2.5 trim_leading_silence=true")
        self.assertIsNotNone(match_audio)
        seg_a, kwargs_a = match_audio
        self.assertEqual(seg_a.name, "split_audio")
        self.assertEqual(kwargs_a.get("duration"), 15.0)
        self.assertEqual(kwargs_a.get("overlap"), 2.5)
        self.assertTrue(kwargs_a.get("trim_leading_silence"))

        # Extract frames
        match_video = SegmenterRegistry.match_prompt("/extract_frames fps=0.5 keyframes_only=false")
        self.assertIsNotNone(match_video)
        seg_v, kwargs_v = match_video
        self.assertEqual(seg_v.name, "extract_frames")
        self.assertEqual(kwargs_v.get("fps"), 0.5)
        self.assertFalse(kwargs_v.get("keyframes_only"))

    def test_03_prompt_matching_natural_language(self):
        """[Segmentation] Verify natural language triggers match corresponding segmenters."""
        match_nl = SegmenterRegistry.match_prompt("split into paragraphs for this article")
        self.assertIsNotNone(match_nl)
        self.assertEqual(match_nl[0].name, "split_paragraphs")

        match_nl2 = SegmenterRegistry.match_prompt("audio segments of file")
        self.assertIsNotNone(match_nl2)
        self.assertEqual(match_nl2[0].name, "split_audio")

    def test_04_markdown_help_generation(self):
        """[Segmentation] Verify generated markdown help is formatted and documents all segmenters."""
        help_md = SegmenterRegistry.generate_markdown_help()
        self.assertIn("Registered Declarative Segmenters", help_md)
        self.assertIn("/split_pages", help_md)
        self.assertIn("/split_paragraphs", help_md)
        self.assertIn("/split_sentences", help_md)
        self.assertIn("/split_audio", help_md)
        self.assertIn("/extract_frames", help_md)

    def test_05_controller_suggest_view_name(self):
        """[Segmentation] Verify controller generates clean suggested view names."""
        v1 = SegmentationController.suggest_view_name("raw_assets", "/split_paragraphs")
        self.assertEqual(v1, "raw_assets_paragraphs")

        v2 = SegmentationController.suggest_view_name("documents", "/split_pages")
        self.assertEqual(v2, "documents_pages")

        v3 = SegmentationController.suggest_view_name("podcasts", "/split_audio duration=10.0")
        self.assertEqual(v3, "podcasts_audio")

    def test_06_controller_domain_and_table_change(self):
        """[Segmentation] Verify controller handles domain and table changes gracefully."""
        res_dom = SegmentationController.handle_domain_change("default", "/split_paragraphs")
        self.assertIn("tables", res_dom)
        self.assertIn("selected_table", res_dom)
        self.assertIn("suggested_view_name", res_dom)

        res_tbl = SegmentationController.handle_table_change("default", "my_table", "/split_sentences")
        self.assertEqual(res_tbl["suggested_view_name"], "my_table_sentences")

    def test_07_dry_run_preview_text(self):
        """[Segmentation] Verify dry-run preview generates sub-row chunks without database writes."""
        if not PIXELTABLE_AVAILABLE or not pxt:
            self.skipTest("Pixeltable not available")

        # Create isolated table with sample text
        tbl = DBManager.get_or_create_table(self.TEST_DOMAIN, "sample_text_tbl")
        self.assertIsNotNone(tbl)

        sample_content = (
            "Paragraph one is about machine learning. It covers deep neural networks.\n\n"
            "Paragraph two discusses declarative multimodal databases. Pixeltable provides automatic lineage.\n\n"
            "Paragraph three concludes the overview. Everything is declarative."
        )
        tbl.insert([{
            "file_name": "sample.txt",
            "content": sample_content,
            "modality": "docs"
        }])

        # Preview paragraphs
        res_para = SegmentationController.handle_preview_segmentation(
            domain=self.TEST_DOMAIN,
            table_name="sample_text_tbl",
            prompt_or_preset="/split_paragraphs",
            sample_rows=1
        )
        self.assertEqual(res_para["status"], "success")
        self.assertTrue(res_para["count"] >= 3)
        self.assertIn("Paragraph #", res_para["headers"])

        # Preview sentences
        res_sent = SegmentationController.handle_preview_segmentation(
            domain=self.TEST_DOMAIN,
            table_name="sample_text_tbl",
            prompt_or_preset="/split_sentences",
            sample_rows=1
        )
        self.assertEqual(res_sent["status"], "success")
        self.assertTrue(res_sent["count"] >= 5)
        self.assertIn("Sentence #", res_sent["headers"])

    def test_08_create_view_paragraphs(self):
        """[Segmentation] Verify creating a segmented view for paragraphs builds a native Pixeltable view."""
        if not PIXELTABLE_AVAILABLE or not pxt:
            self.skipTest("Pixeltable not available")

        res_create = SegmentationController.handle_create_view(
            domain=self.TEST_DOMAIN,
            source_table="sample_text_tbl",
            view_name="sample_text_paras",
            prompt_or_preset="/split_paragraphs"
        )
        self.assertEqual(res_create["status"], "success")
        self.assertTrue(res_create["count"] >= 3)
        self.assertIn("sample_text_paras", res_create["table_choices"])

        # Query the view directly
        full_view = f"{self.TEST_DOMAIN}.sample_text_paras"
        v = pxt.get_table(full_view)
        cols = [str(c) for c in v.columns()]
        self.assertIn("pos", cols)
        self.assertIn("text", cols)

        rows = v.select(v.pos, v.text).collect()
        self.assertTrue(len(rows) >= 3)

    def test_09_create_view_sentences(self):
        """[Segmentation] Verify creating a segmented view for sentences builds a native Pixeltable view."""
        if not PIXELTABLE_AVAILABLE or not pxt:
            self.skipTest("Pixeltable not available")

        res_create = SegmentationController.handle_create_view(
            domain=self.TEST_DOMAIN,
            source_table="sample_text_tbl",
            view_name="sample_text_sents",
            prompt_or_preset="/split_sentences"
        )
        self.assertEqual(res_create["status"], "success")
        self.assertTrue(res_create["count"] >= 5)

        full_view = f"{self.TEST_DOMAIN}.sample_text_sents"
        v = pxt.get_table(full_view)
        cols = [str(c) for c in v.columns()]
        self.assertIn("pos", cols)
        self.assertIn("text", cols)

    def test_10_create_view_audio(self):
        """[Segmentation] Verify creating a segmented audio view with audio_splitter."""
        if not PIXELTABLE_AVAILABLE or not pxt:
            self.skipTest("Pixeltable not available")

        aud_tbl = DBManager.get_or_create_table(self.TEST_DOMAIN, "sample_audio_tbl")
        aud_tbl.insert([{
            "file_name": "test_audio.wav",
            "file_path": str(self.audio_file.resolve()),
            "audio": str(self.audio_file.resolve()),
            "modality": "audio"
        }])

        res_create = SegmentationController.handle_create_view(
            domain=self.TEST_DOMAIN,
            source_table="sample_audio_tbl",
            view_name="sample_audio_segments",
            prompt_or_preset="/split_audio duration=1.0"
        )
        self.assertEqual(res_create["status"], "success")
        self.assertTrue(res_create["count"] >= 2)

        full_view = f"{self.TEST_DOMAIN}.sample_audio_segments"
        v = pxt.get_table(full_view)
        cols = [str(c) for c in v.columns()]
        self.assertIn("pos", cols)
        self.assertIn("segment_start", cols)
        self.assertIn("segment_end", cols)
        self.assertIn("audio_segment", cols)

    def test_11_create_view_split_pages(self):
        """[Segmentation] Verify creating a segmented view for PDF documents with split_pages."""
        if not PIXELTABLE_AVAILABLE or not pxt:
            self.skipTest("Pixeltable not available")
        if not hasattr(self, "pdf_file") or not self.pdf_file.exists():
            self.skipTest("PyMuPDF / PDF test fixture not available")

        doc_tbl = DBManager.get_or_create_table(self.TEST_DOMAIN, "sample_doc_tbl")
        doc_tbl.insert([{
            "file_name": "test_doc.pdf",
            "file_path": str(self.pdf_file.resolve()),
            "doc": str(self.pdf_file.resolve()),
            "modality": "docs"
        }])

        res_create = SegmentationController.handle_create_view(
            domain=self.TEST_DOMAIN,
            source_table="sample_doc_tbl",
            view_name="sample_doc_pages",
            prompt_or_preset="/split_pages"
        )
        self.assertEqual(res_create["status"], "success")
        self.assertEqual(res_create["count"], 2)

        full_view = f"{self.TEST_DOMAIN}.sample_doc_pages"
        v = pxt.get_table(full_view)
        cols = [str(c) for c in v.columns()]
        self.assertIn("pos", cols)
        self.assertIn("page", cols)
        self.assertIn("text", cols)

    def test_12_create_view_extract_frames(self):
        """[Segmentation] Verify creating a segmented video view with extract_frames."""
        if not PIXELTABLE_AVAILABLE or not pxt:
            self.skipTest("Pixeltable not available")
        if not hasattr(self, "video_file") or not self.video_file.exists():
            self.skipTest("PyAV / Video test fixture not available")

        vid_tbl = DBManager.get_or_create_table(self.TEST_DOMAIN, "sample_video_tbl")
        vid_tbl.insert([{
            "file_name": "test_video.mp4",
            "file_path": str(self.video_file.resolve()),
            "video": str(self.video_file.resolve()),
            "modality": "video"
        }])

        res_create = SegmentationController.handle_create_view(
            domain=self.TEST_DOMAIN,
            source_table="sample_video_tbl",
            view_name="sample_video_frames",
            prompt_or_preset="/extract_frames fps=2.0"
        )
        self.assertEqual(res_create["status"], "success")
        self.assertTrue(res_create["count"] >= 2)

        full_view = f"{self.TEST_DOMAIN}.sample_video_frames"
        v = pxt.get_table(full_view)
        cols = [str(c) for c in v.columns()]
        self.assertIn("pos", cols)
        self.assertIn("frame", cols)
        self.assertIn("frame_attrs", cols)

    def test_13_controller_invalid_view_name(self):
        """[Segmentation] Verify controller rejects empty, invalid, or duplicate view names."""
        # Empty view name
        res_empty = SegmentationController.handle_create_view(
            domain=self.TEST_DOMAIN,
            source_table="sample_text_tbl",
            view_name="",
            prompt_or_preset="/split_paragraphs"
        )
        self.assertEqual(res_empty["status"], "error")

        # Punctuation-only view name
        res_invalid = SegmentationController.handle_create_view(
            domain=self.TEST_DOMAIN,
            source_table="sample_text_tbl",
            view_name="???",
            prompt_or_preset="/split_paragraphs"
        )
        self.assertEqual(res_invalid["status"], "error")

        # View name identical to source table
        res_ident = SegmentationController.handle_create_view(
            domain=self.TEST_DOMAIN,
            source_table="sample_text_tbl",
            view_name="sample_text_tbl",
            prompt_or_preset="/split_paragraphs"
        )
        self.assertEqual(res_ident["status"], "error")

    def test_14_missing_column_error_handling(self):
        """[Segmentation] Verify graceful error when segmenting a table missing required column."""
        if not PIXELTABLE_AVAILABLE or not pxt:
            self.skipTest("Pixeltable not available")

        # Create table with only text/content (no audio column)
        pxt.create_table(f"{self.TEST_DOMAIN}.table_without_audio", {"content": pxt.String}, if_exists="ignore")

        # Attempt to split audio on a table with no audio column
        res = SegmentationController.handle_create_view(
            domain=self.TEST_DOMAIN,
            source_table="table_without_audio",
            view_name="invalid_audio_view",
            prompt_or_preset="/split_audio"
        )
        self.assertEqual(res["status"], "error")
        self.assertIn("audio", res["stats_text"].lower())

    def test_15_ui_create_segmentation_tab_settings(self):
        """[Segmentation] Verify create_segmentation_tab initializes cleanly with Settings object."""
        import gradio as gr
        from src.ui.segmentation_tab import create_segmentation_tab
        settings = get_settings()
        with gr.Blocks():
            comps = create_segmentation_tab(settings)
            self.assertIsInstance(comps, dict)
            self.assertIn("create_view_btn", comps)
            self.assertIn("domain_dropdown", comps)
            self.assertIn("source_table_dropdown", comps)
            self.assertIn("target_view_input", comps)


if __name__ == "__main__":
    unittest.main()
