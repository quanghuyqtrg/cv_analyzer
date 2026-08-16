"""Text extraction from PDF and DOCX files.

Handles two-column CV layouts (sidebar + main content) by detecting
column gaps and extracting each column separately to preserve reading order.
"""

import io
import os
import unicodedata
import re

import pdfplumber
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


class ExtractionError(Exception):
    """Base exception for extraction failures."""


class UnsupportedFormatError(ExtractionError):
    """Raised when file format is not PDF or DOCX."""


def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """Extract plain text from a PDF or DOCX file.

    Args:
        file_bytes: Raw file content (e.g. from UploadFile.read()).
        filename: Original filename, used to detect format by extension.

    Returns:
        Cleaned plain text. May be empty if the file contains no text.

    Raises:
        UnsupportedFormatError: If file extension is not .pdf or .docx.
        ExtractionError: If the file is empty, corrupt, or cannot be read.
    """
    if not file_bytes:
        raise ExtractionError("File is empty")

    ext = os.path.splitext(filename)[1].lower()

    if ext == ".pdf":
        raw = _extract_pdf(file_bytes)
    elif ext == ".docx":
        raw = _extract_docx(file_bytes)
    else:
        raise UnsupportedFormatError(
            f"Unsupported file format: '{ext}'. Only .pdf and .docx are supported."
        )

    return _clean_text(raw)


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def _extract_pdf(file_bytes: bytes) -> str:
    try:
        pdf = pdfplumber.open(io.BytesIO(file_bytes))
    except Exception as exc:
        raise ExtractionError(f"Cannot open PDF: {exc}") from exc

    with pdf:
        pages = pdf.pages
        if not pages:
            raise ExtractionError("PDF has no pages")

        parts: list[str] = []
        for page in pages:
            text = _extract_pdf_page(page)
            if text:
                parts.append(text)

        return "\n\n".join(parts)


def _extract_pdf_page(page: pdfplumber.page.Page) -> str:
    """Extract text from a single PDF page, handling two-column layouts."""
    words = page.extract_words(x_tolerance=3, y_tolerance=3)
    if not words:
        return page.extract_text() or ""

    boundary = _detect_column_boundary(words, page.width)

    if boundary is None:
        return page.extract_text(layout=True) or ""

    return _extract_two_columns(page, boundary)


def _detect_column_boundary(
    words: list[dict], page_width: float
) -> float | None:
    """Detect column split point via gap analysis on word x0 positions.

    Returns the midpoint of the largest gap in the middle region of the page,
    or None if no significant gap is found.
    """
    x0_values = [w["x0"] for w in words]
    if not x0_values:
        return None

    num_bins = 50
    bin_width = page_width / num_bins
    bins: list[int] = [0] * num_bins

    for x0 in x0_values:
        idx = min(int(x0 / bin_width), num_bins - 1)
        bins[idx] += 1

    # Only look for gaps in the middle 20%-80% of the page
    start_bin = int(num_bins * 0.2)
    end_bin = int(num_bins * 0.8)

    best_gap_start = -1
    best_gap_length = 0
    current_gap_start = -1
    current_gap_length = 0

    for i in range(start_bin, end_bin):
        if bins[i] == 0:
            if current_gap_start == -1:
                current_gap_start = i
                current_gap_length = 1
            else:
                current_gap_length += 1
        else:
            if current_gap_length > best_gap_length:
                best_gap_length = current_gap_length
                best_gap_start = current_gap_start
            current_gap_start = -1
            current_gap_length = 0

    # Check if the last run was the best
    if current_gap_length > best_gap_length:
        best_gap_length = current_gap_length
        best_gap_start = current_gap_start

    # Gap must be at least 5% of page width
    min_gap_bins = max(1, int(num_bins * 0.05))
    if best_gap_length < min_gap_bins:
        return None

    midpoint = (best_gap_start + best_gap_length / 2) * bin_width
    return midpoint


def _extract_two_columns(page: pdfplumber.page.Page, boundary: float) -> str:
    """Crop page into two columns and extract text from each."""
    height = page.height
    width = page.width

    left_crop = page.crop((0, 0, boundary, height))
    right_crop = page.crop((boundary, 0, width, height))

    left_text = left_crop.extract_text() or ""
    right_text = right_crop.extract_text() or ""

    parts = [t for t in (left_text, right_text) if t.strip()]
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# DOCX extraction
# ---------------------------------------------------------------------------

_WPML_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_WPML_TABLE_TAG = f"{{{_WPML_NS}}}tbl"
_WPML_PARA_TAG = f"{{{_WPML_NS}}}p"


def _extract_docx(file_bytes: bytes) -> str:
    try:
        doc = Document(io.BytesIO(file_bytes))
    except Exception as exc:
        raise ExtractionError(f"Cannot open DOCX: {exc}") from exc

    parts: list[str] = []

    # Walk body children in document order to preserve paragraph/table interleaving
    for child in doc.element.body:
        tag = child.tag
        if tag == _WPML_PARA_TAG:
            para = Paragraph(child, doc.element.body)
            text = para.text.strip()
            if text:
                parts.append(text)
        elif tag == _WPML_TABLE_TAG:
            table = Table(child, doc.element.body)
            table_text = _extract_docx_table(table)
            if table_text:
                parts.append(table_text)

    # Extract text boxes (floating content not in body flow)
    textbox_text = _extract_docx_textboxes(doc)
    if textbox_text:
        parts.append(textbox_text)

    return "\n".join(parts)


def _extract_docx_table(table: Table) -> str:
    rows: list[str] = []
    for row in table.rows:
        cells = [cell.text.strip() for cell in row.cells]
        row_text = " | ".join(cells)
        if row_text.replace("|", "").strip():
            rows.append(row_text)
    return "\n".join(rows)


def _extract_docx_textboxes(doc: Document) -> str:
    """Extract text from Word text boxes (w:txbxContent).

    Text boxes appear in both mc:Choice and mc:Fallback with identical content,
    so we deduplicate by keeping only unique text fragments.
    """
    nsmap = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
        "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
        "v": "urn:schemas-microsoft-com:vml",
    }

    # Find all txbxContent elements
    txbx_elements = doc.element.body.findall(".//wps:txbxContent", nsmap)
    # Also check VML fallback path
    txbx_elements += doc.element.body.findall(".//v:textbox/w:txbxContent", nsmap)

    seen: set[str] = set()
    parts: list[str] = []

    for txbx in txbx_elements:
        runs = txbx.findall(".//w:r/w:t", nsmap)
        text = "".join(r.text or "" for r in runs).strip()
        if text and text not in seen:
            seen.add(text)
            parts.append(text)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

_REPLACEMENTS = {
    "\u2018": "'",   # left single quote
    "\u2019": "'",   # right single quote
    "\u201c": '"',   # left double quote
    "\u201d": '"',   # right double quote
    "\u2014": "-",   # em dash
    "\u2013": "-",   # en dash
    "\u2022": "-",   # bullet
    "\u00a0": " ",   # non-breaking space
}

_REPLACE_PATTERN = re.compile(
    "[" + re.escape("".join(_REPLACEMENTS.keys())) + "]"
)


def _clean_text(text: str) -> str:
    """Normalize and clean extracted text."""
    # 1. Unicode NFC normalize
    text = unicodedata.normalize("NFC", text)

    # 2. Replace smart quotes, dashes, bullets, NBSP
    text = _REPLACE_PATTERN.sub(lambda m: _REPLACEMENTS[m.group()], text)

    # 3. Collapse multiple spaces (preserve newlines)
    text = re.sub(r"[^\S\n]+", " ", text)

    # 4. Collapse 3+ consecutive newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 5. Strip each line and strip the whole string
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(lines)
    text = text.strip()

    return text
