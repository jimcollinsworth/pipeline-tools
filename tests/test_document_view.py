"""
Tests for Document View & Column Filtering
==========================================
Unit tests for TablesController document view formatting, row navigation,
and column visibility filtering (TDD).
"""

import unittest
from src.controllers.tables_controller import TablesController

class TestDocumentView(unittest.TestCase):
    """Test suite for Table vs. Document View Toggle and Column Filtering."""

    def test_filter_dataframe_columns(self):
        """[Document View] Verify filter_dataframe_columns projects only selected columns."""
        columns = ["file_name", "modality", "content", "summary"]
        data = [
            ["memo.pdf", "docs", "Full text content 1", "Summary 1"],
            ["photo.png", "images", "Full text content 2", "Summary 2"]
        ]
        selected = ["file_name", "summary"]

        filtered_data, filtered_cols = TablesController.filter_dataframe_columns(data, columns, selected)
        self.assertEqual(filtered_cols, ["file_name", "summary"])
        self.assertEqual(filtered_data, [
            ["memo.pdf", "Summary 1"],
            ["photo.png", "Summary 2"]
        ])

        # Test selecting all columns
        all_data, all_cols = TablesController.filter_dataframe_columns(data, columns, columns)
        self.assertEqual(all_cols, columns)
        self.assertEqual(all_data, data)

        # Test empty selected columns fallback
        empty_data, empty_cols = TablesController.filter_dataframe_columns(data, columns, [])
        self.assertEqual(empty_cols, columns)
        self.assertEqual(empty_data, data)

    def test_navigate_row(self):
        """[Document View] Verify navigate_row clamps index boundaries."""
        total = 5
        # Clamp at lower boundary
        self.assertEqual(TablesController.navigate_row(current_index=0, delta=-1, total_rows=total), 0)
        # Forward navigation
        self.assertEqual(TablesController.navigate_row(current_index=0, delta=1, total_rows=total), 1)
        self.assertEqual(TablesController.navigate_row(current_index=2, delta=2, total_rows=total), 4)
        # Clamp at upper boundary
        self.assertEqual(TablesController.navigate_row(current_index=4, delta=1, total_rows=total), 4)
        # Zero rows edge case
        self.assertEqual(TablesController.navigate_row(current_index=0, delta=1, total_rows=0), 0)

    def test_format_document_view(self):
        """[Document View] Verify format_document_view extracts title, entity spans, and attributes."""
        row_dict = {
            "file_name": "executive_minutes.pdf",
            "modality": "docs",
            "file_path": "C:/data/executive_minutes.pdf",
            "content": "Director Robert Oppenheimer presided over the Princeton council meeting.",
            "people": '["Robert Oppenheimer"]',
            "status": "Approved",
            "expenditure_usd": 15000
        }
        active_cols = ["file_name", "status", "expenditure_usd"]
        doc = TablesController.format_document_view(
            row_dict=row_dict,
            active_columns=active_cols,
            row_index=2,
            total_rows=10
        )

        self.assertEqual(doc["counter_text"], "Record 3 of 10")
        self.assertEqual(doc["title_text"], "executive_minutes.pdf")
        self.assertEqual(doc["modality"], "docs")
        self.assertEqual(doc["media_path"], "C:/data/executive_minutes.pdf")
        self.assertTrue(len(doc["highlighted_spans"]) > 0)
        # Check entity span contains Robert Oppenheimer
        spans_text = [span[0] for span in doc["highlighted_spans"] if span[1] is not None]
        self.assertIn("Robert Oppenheimer", spans_text)
        # Check attributes block contains active columns
        self.assertIn("Approved", doc["attributes_md"])
        self.assertIn("15000", doc["attributes_md"])
