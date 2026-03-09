"""
PDFPilot — Merge Service
Merge multiple PDF files into a single document
"""

import os
import uuid
import logging
from PyPDF2 import PdfMerger

logger = logging.getLogger(__name__)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "outputs")


def merge_pdfs(file_paths: list[str]) -> str:
    """
    Merge multiple PDF files into one.
    
    Args:
        file_paths: List of paths to PDF files to merge
        
    Returns:
        Path to the merged PDF file
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_name = f"merged_{uuid.uuid4().hex[:8]}.pdf"
    output_path = os.path.join(OUTPUT_DIR, output_name)

    logger.info(f"Merging {len(file_paths)} PDFs")

    merger = PdfMerger()
    try:
        for path in file_paths:
            if not os.path.exists(path):
                raise FileNotFoundError(f"File not found: {path}")
            merger.append(path)
        
        merger.write(output_path)
        logger.info(f"Merge complete: {output_path}")
        return output_path
    finally:
        merger.close()
