"""
End-to-End OCR Test Suite
=========================
Validates RapidOCR integration across PIL images, scanned image-only PDFs,
DBManager automatic fallback during ingestion, prompt-driven UDF matching,
and Pixeltable declarative computed column attachment.
"""

import os
import sys
import unittest
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw

# Ensure repo root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.ocr import (
    ocr_image,
    ocr_pdf_pages,
    ocr_document_core,
    attach_ocr_columns,
    PIXELTABLE_AVAILABLE
)
from src.core.udf_registry import UDFRegistry, _eval_ocr_sample
from src.db.manager import DBManager


class TestOCR(unittest.TestCase):
    """Integration and regression test suite for OCR document processing."""

    @classmethod
    def setUpClass(cls):
        """Set up synthetic test assets: PIL image and image-only PDF."""
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.dir_path = Path(cls.temp_dir.name)

        # 1. Create a clear high-contrast synthetic scanned document image
        cls.img_path = cls.dir_path / "scanned_invoice.png"
        img = Image.new("RGB", (600, 300), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        # Draw standard invoice text lines
        draw.text((30, 30), "INVOICE NUMBER: INV-98234", fill=(0, 0, 0))
        draw.text((30, 80), "VENDOR: Acme Industrial Tools", fill=(0, 0, 0))
        draw.text((30, 130), "TOTAL AMOUNT DUE: $450.00", fill=(0, 0, 0))
        draw.text((30, 180), "STATUS: PAYMENT APPROVED", fill=(0, 0, 0))
        img.save(cls.img_path)

        # 2. Save the same synthetic image as an image-only PDF (no digital text stream)
        cls.pdf_path = cls.dir_path / "scanned_invoice.pdf"
        img.save(cls.pdf_path, "PDF", resolution=150.0)

    @classmethod
    def tearDownClass(cls):
        """Clean up temporary directory and test tables."""
        cls.temp_dir.cleanup()
        if PIXELTABLE_AVAILABLE:
            try:
                import pixeltable as pxt
                pxt.drop_table("test_ocr_domain.test_scanned_docs", if_not_exists="ignore")
                pxt.drop_dir("test_ocr_domain", if_not_exists="ignore")
            except Exception:
                pass

    def test_01_ocr_image_extraction(self):
        """[OCR] Verify RapidOCR extracts text from PIL Image and direct image file path."""
        # Test direct file path
        text_from_path = ocr_image(self.img_path)
        self.assertIn("INVOICE", text_from_path.upper())
        self.assertIn("98234", text_from_path)
        self.assertIn("ACME", text_from_path.upper())

        # Test PIL Image object
        with Image.open(self.img_path) as img:
            text_from_img = ocr_image(img)
            self.assertIn("INVOICE", text_from_img.upper())
            self.assertIn("450.00", text_from_img)

    def test_02_scanned_pdf_rendering_and_ocr(self):
        """[OCR] Verify pypdfium2 rendering and OCR extraction on an image-only PDF."""
        # Verify that digital text extraction finds NO text streams in this image PDF
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(self.pdf_path) as pdf:
            page = pdf.get_page(0)
            tp = page.get_textpage()
            raw_text = tp.get_text_range()
            tp.close()
            page.close()
        self.assertEqual(raw_text.strip(), "", "Synthetic image PDF should have 0 digital text streams.")

        # Now verify ocr_pdf_pages extracts the text via image rendering + OCR
        ocr_text = ocr_pdf_pages(self.pdf_path, max_pages=2)
        self.assertTrue(len(ocr_text) > 0)
        self.assertIn("Page 1", ocr_text)
        self.assertIn("98234", ocr_text)
        self.assertIn("ACME", ocr_text.upper())

    def test_03_dbmanager_extract_file_content_fallback(self):
        """[OCR] Verify DBManager.extract_file_content automatically invokes OCR on image-only PDFs."""
        content = DBManager.extract_file_content(str(self.pdf_path), modality="documents", file_type=".pdf")
        
        # Must NOT return the old placeholder "[Scanned/Image PDF - no extractable text found]"
        self.assertNotEqual(content, "[Scanned/Image PDF - no extractable text found]")
        self.assertIn("INVOICE", content.upper())
        self.assertIn("98234", content)

    def test_04_udf_registry_matching_and_help(self):
        """[OCR] Verify UDFRegistry matches slash commands and natural language triggers for OCR."""
        # Slash command with arguments
        match_slash = UDFRegistry.match_prompt("/ocr max_pages=3 column_name=custom_ocr")
        self.assertIsNotNone(match_slash)
        udf_def, kwargs = match_slash
        self.assertEqual(udf_def.name, "ocr")
        self.assertEqual(kwargs.get("max_pages"), 3)
        self.assertEqual(kwargs.get("column_name"), "custom_ocr")

        # Natural language trigger
        match_nl = UDFRegistry.match_prompt("please extract scanned text using pdf ocr for {file_name}")
        self.assertIsNotNone(match_nl)
        udf_def, kwargs = match_nl
        self.assertEqual(udf_def.name, "ocr")

        # Dynamic markdown help
        help_md = UDFRegistry.generate_markdown_help()
        self.assertIn("/ocr", help_md)
        self.assertIn("RapidOCR", help_md)

    def test_05_declarative_table_sample_and_batch_attachment(self):
        """[OCR] Verify dry-run sample evaluation and declarative Pixeltable computed column attachment."""
        if not PIXELTABLE_AVAILABLE:
            self.skipTest("Pixeltable not installed in environment.")

        import pixeltable as pxt
        domain = "test_ocr_domain"
        table_name = "test_scanned_docs"

        # Ingest the test PDF into a Pixeltable table
        files_info = [{
            "name": self.pdf_path.name,
            "abs_path": str(self.pdf_path),
            "rel_path": self.pdf_path.name,
            "extension": ".pdf",
            "size_bytes": os.path.getsize(self.pdf_path),
            "size": "50 KB",
            "modality": "documents"
        }]

        ingest_res = DBManager.ingest_files(domain, table_name, files_info, overwrite=True)
        self.assertEqual(ingest_res.get("status"), "success")

        # 1. Test dry-run sample evaluation
        sample_res = _eval_ocr_sample(domain, table_name, sample_count=1, max_pages=2)
        self.assertEqual(sample_res.get("status"), "success")
        self.assertEqual(sample_res.get("count"), 1)
        preview_text = sample_res["data"][0][3]
        self.assertIn("98234", preview_text)

        # 2. Test declarative computed column attachment
        attach_res = attach_ocr_columns(domain, table_name, max_pages=2, column_name="ocr_text")
        self.assertEqual(attach_res.get("status"), "success")

        # 3. Query Pixeltable table data to verify computed column evaluation
        data_res = DBManager.get_table_data(domain, table_name, limit=5, lightweight=False)
        cols = data_res.get("columns", [])
        self.assertIn("ocr_text", cols)
        
        row_dict = dict(zip(cols, data_res["data"][0]))
        extracted_column_val = str(row_dict.get("ocr_text", ""))
        self.assertIn("INVOICE", extracted_column_val.upper())
        self.assertIn("98234", extracted_column_val)


if __name__ == "__main__":
    unittest.main()
