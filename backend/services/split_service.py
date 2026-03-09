"""
PDF splitting helpers.
"""

import logging
import uuid
from pathlib import Path

from PyPDF2 import PdfReader, PdfWriter

from backend.file_utils import OUTPUT_DIR

logger = logging.getLogger(__name__)


def parse_page_ranges(pages_str: str, total_pages: int) -> list[int]:
    """
    Parse a page selection like "1-3,5" into 0-indexed page numbers.
    """
    if pages_str.strip().lower() == "all":
        return list(range(total_pages))

    def resolve_page_token(token: str, *, is_range_end: bool = False) -> int:
        normalized = token.strip().lower()
        if normalized == "last":
            return total_pages if is_range_end else total_pages - 1
        return int(normalized) if is_range_end else int(normalized) - 1

    page_numbers = []
    for part in pages_str.split(","):
        chunk = part.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start_text, end_text = chunk.split("-", 1)
            start = max(resolve_page_token(start_text), 0)
            end = min(resolve_page_token(end_text, is_range_end=True), total_pages)
            page_numbers.extend(range(start, end))
        else:
            page_number = resolve_page_token(chunk)
            if 0 <= page_number < total_pages:
                page_numbers.append(page_number)

    return sorted(set(page_numbers))


def split_pdf(input_path: str, pages: str = "all") -> list[str]:
    """
    Split a PDF into page-specific outputs.
    """
    source = Path(input_path)
    reader = PdfReader(source)
    total_pages = len(reader.pages)
    page_numbers = parse_page_ranges(pages, total_pages)

    logger.info("Splitting PDF (%s pages) -> pages %s", total_pages, page_numbers)
    if not page_numbers:
        raise ValueError("No valid pages were selected for splitting")

    output_paths: list[str] = []
    if pages.strip().lower() == "all":
        for page_index in range(total_pages):
            writer = PdfWriter()
            writer.add_page(reader.pages[page_index])
            output_path = OUTPUT_DIR / f"page_{page_index + 1}_{uuid.uuid4().hex[:6]}.pdf"
            with output_path.open("wb") as handle:
                writer.write(handle)
            output_paths.append(str(output_path))
    else:
        writer = PdfWriter()
        for page_number in page_numbers:
            writer.add_page(reader.pages[page_number])
        output_path = OUTPUT_DIR / f"split_{uuid.uuid4().hex[:8]}.pdf"
        with output_path.open("wb") as handle:
            writer.write(handle)
        output_paths.append(str(output_path))

    logger.info("Split complete: %s files created", len(output_paths))
    return output_paths


def extract_pages_to_pdf(input_path: str, pages: str) -> str:
    """
    Extract one or more selected pages into a single PDF.
    """
    source = Path(input_path)
    reader = PdfReader(source)
    total_pages = len(reader.pages)
    page_numbers = parse_page_ranges(pages, total_pages)

    logger.info("Extracting pages from PDF (%s pages) -> pages %s", total_pages, page_numbers)
    if not page_numbers:
        raise ValueError("No valid pages were selected")

    writer = PdfWriter()
    for page_number in page_numbers:
        writer.add_page(reader.pages[page_number])

    output_path = OUTPUT_DIR / f"pages_{uuid.uuid4().hex[:8]}.pdf"
    with output_path.open("wb") as handle:
        writer.write(handle)

    logger.info("Page extraction complete: %s", output_path)
    return str(output_path)
