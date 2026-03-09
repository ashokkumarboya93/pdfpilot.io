"""
PDFPilot — Merge Service
Merge multiple PDF files into a single document
"""

import logging
import uuid
from pathlib import Path

from PyPDF2 import PdfMerger

from backend.file_utils import OUTPUT_DIR

logger = logging.getLogger(__name__)


def merge_pdfs(file_paths: list[str]) -> str:
    """
    Merge multiple PDF files into one.
    
    Args:
        file_paths: List of paths to PDF files to merge
        
    Returns:
        Path to the merged PDF file
    """
    output_name = f"merged_{uuid.uuid4().hex[:8]}.pdf"
    output_path = OUTPUT_DIR / output_name

    logger.info(f"Merging {len(file_paths)} PDFs")

    merger = PdfMerger()
    try:
        for path in file_paths:
            if not Path(path).exists():
                raise FileNotFoundError(f"File not found: {path}")
            merger.append(path)
        
        merger.write(str(output_path))
        logger.info(f"Merge complete: {output_path}")
        return str(output_path)
    finally:
        merger.close()
