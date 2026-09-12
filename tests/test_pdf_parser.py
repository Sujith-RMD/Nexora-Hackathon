"""Unit tests for PDF parsing module."""

import os
import tempfile
import unittest
import fitz  # PyMuPDF
from src.pdf_parser import normalize_whitespace, parse_pdf, parse_pdf_with_metadata


class TestPDFParser(unittest.TestCase):
    def test_normalize_whitespace(self):
        text = "Hello    world \n\n\n\n  New paragraph  with \xa0 spaces  "
        normalized = normalize_whitespace(text)
        self.assertEqual(normalized, "Hello world\n\nNew paragraph with spaces")

    def test_parse_real_pdf(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            pdf_path = f.name

        try:
            # Create a 2-page sample PDF using PyMuPDF
            doc = fitz.open()
            page1 = doc.new_page()
            page1.insert_text((50, 50), "Page 1: Jane Doe\nSkills: Python, React")
            page2 = doc.new_page()
            page2.insert_text((50, 50), "Page 2: Experience\nBuilt backend services with Node.js")
            doc.save(pdf_path)
            doc.close()

            result = parse_pdf_with_metadata(pdf_path)
            self.assertEqual(result["page_count"], 2)
            self.assertEqual(len(result["warnings"]), 0)
            self.assertIn("Jane Doe", result["text"])
            self.assertIn("Node.js", result["text"])

            simple_text = parse_pdf(pdf_path)
            self.assertIn("Jane Doe", simple_text)
        finally:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)

    def test_parse_nonexistent_pdf(self):
        result = parse_pdf_with_metadata("non_existent_file_12345.pdf")
        self.assertEqual(result["text"], "")
        self.assertEqual(result["page_count"], 0)
        self.assertGreater(len(result["warnings"]), 0)


if __name__ == "__main__":
    unittest.main()
