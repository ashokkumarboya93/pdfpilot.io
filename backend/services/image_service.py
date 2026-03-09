"""
Image and PDF-to-image helpers.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)


def pdf_to_images(input_path: str, image_format: str = "png") -> tuple[list[str], str]:
    """
    Convert each page of a PDF into an image and return a zip archive.
    """
    source = Path(input_path)
    image_dir = OUTPUT_DIR / f"images_{uuid.uuid4().hex[:10]}"
    image_dir.mkdir(exist_ok=True)

    output_paths = _render_with_pdfium(source, image_dir, image_format)
    if not output_paths:
        output_paths = _render_with_pdf2image(source, image_dir, image_format)

    archive_path = OUTPUT_DIR / f"{image_dir.name}.zip"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in output_paths:
            archive.write(path, arcname=Path(path).name)

    logger.info("PDF-to-image conversion complete: %s pages", len(output_paths))
    return output_paths, str(archive_path)


def images_to_pdf(input_paths: list[str]) -> str:
    """
    Combine one or more images into a single PDF file.
    """
    from PIL import Image

    if not input_paths:
        raise ValueError("At least one image is required to create a PDF")

    images = []
    for path in input_paths:
        image = Image.open(path)
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")
        images.append(image)

    output_path = OUTPUT_DIR / f"images_{uuid.uuid4().hex[:8]}.pdf"
    head, *tail = images
    head.save(output_path, "PDF", save_all=True, append_images=tail)
    logger.info("Images-to-PDF conversion complete: %s", output_path)
    return str(output_path)


def pdf_pages_to_images(input_path: str, pages: str, image_format: str = "png") -> tuple[list[str], str]:
    """
    Convert selected pages of a PDF into images and return a zip archive.
    """
    from backend.services.split_service import extract_pages_to_pdf

    extracted_pdf = extract_pages_to_pdf(input_path, pages)
    return pdf_to_images(extracted_pdf, image_format=image_format)


def _render_with_pdfium(source: Path, image_dir: Path, image_format: str) -> list[str]:
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return []

    pdf = pdfium.PdfDocument(str(source))
    output_paths: list[str] = []
    try:
        for index in range(len(pdf)):
            page = pdf[index]
            try:
                bitmap = page.render(scale=2.0)
                pil_image = bitmap.to_pil()
                output_path = image_dir / f"{source.stem}_{index + 1}.{image_format}"
                pil_image.save(output_path, image_format.upper())
                output_paths.append(str(output_path))
            finally:
                page.close()
    finally:
        pdf.close()

    return output_paths


def _render_with_pdf2image(source: Path, image_dir: Path, image_format: str) -> list[str]:
    try:
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise RuntimeError(
            "PDF-to-image conversion requires pypdfium2 or pdf2image to be installed"
        ) from exc

    try:
        pages = convert_from_path(str(source), fmt=image_format)
    except Exception as exc:
        raise RuntimeError(
            "PDF-to-image conversion failed. Install Poppler if pdf2image is being used."
        ) from exc

    output_paths: list[str] = []
    for index, page in enumerate(pages, start=1):
        output_path = image_dir / f"{source.stem}_{index}.{image_format}"
        page.save(output_path, image_format.upper())
        output_paths.append(str(output_path))
    return output_paths
