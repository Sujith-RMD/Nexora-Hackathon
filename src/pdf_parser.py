"""PDF parsing module using PyMuPDF (fitz).

Provides resilient multi-page text extraction with whitespace normalization
and per-document error isolation.
"""

import os
import re
from typing import Dict, List, Tuple, Union

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


def normalize_whitespace(text: str) -> str:
    """Normalize repeated whitespace while preserving paragraph breaks."""
    if not text:
        return ""
    # Replace non-breaking spaces and unusual whitespace characters
    text = text.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    # Collapse 3+ consecutive newlines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Collapse multiple horizontal whitespace characters into a single space
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def parse_pdf_with_metadata(path: str) -> Dict[str, Union[str, int, List[str]]]:
    """Extract text and metadata from a PDF file.

    Returns a dict with:
      - "text": Normalized extracted string.
      - "raw_text": Unmodified joined text.
      - "page_count": Total pages processed.
      - "warnings": List of any warnings encountered.
    """
    warnings: List[str] = []
    if not os.path.exists(path):
        return {
            "text": "",
            "raw_text": "",
            "page_count": 0,
            "warnings": [f"File not found: {path}"],
        }

    if fitz is None:
        return {
            "text": "",
            "raw_text": "",
            "page_count": 0,
            "warnings": ["PyMuPDF (fitz) is not installed in the active environment."],
        }

    raw_pages: List[str] = []
    try:
        doc = fitz.open(path)
        page_count = len(doc)
        if page_count == 0:
            warnings.append("Document has 0 pages.")

        for i, page in enumerate(doc):
            try:
                page_text = page.get_text("text")
                raw_pages.append(page_text)
            except Exception as e:
                warnings.append(f"Failed to read text on page {i + 1}: {str(e)}")

        doc.close()
    except Exception as e:
        warnings.append(f"Failed to open PDF {os.path.basename(path)}: {str(e)}")
        return {
            "text": "",
            "raw_text": "",
            "page_count": 0,
            "warnings": warnings,
        }

    raw_text = "\n\n".join(raw_pages)
    normalized = normalize_whitespace(raw_text)

    if not normalized and page_count > 0:
        warnings.append("Extracted text is empty. PDF might be scanned or image-only.")

    return {
        "text": normalized,
        "raw_text": raw_text,
        "page_count": page_count,
        "warnings": warnings,
    }


def parse_pdf(path: str) -> str:
    """Public interface per MASTER_CONTEXT.md.

    Returns the normalized extracted text. Does not raise fatal exceptions.
    """
    result = parse_pdf_with_metadata(path)
    return str(result["text"])
