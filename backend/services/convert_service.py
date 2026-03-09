"""
Document conversion helpers.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import uuid
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp"}
WORD_EXTENSIONS = {".doc", ".docx"}
PRESENTATION_EXTENSIONS = {".ppt", ".pptx"}


def convert_to_pdf(input_path: str) -> str:
    """
    Convert a supported file into PDF format.
    """
    source = Path(input_path)
    ext = source.suffix.lower()
    output_path = OUTPUT_DIR / f"{uuid.uuid4().hex}.pdf"

    logger.info("Converting %s to PDF", source)

    if ext in IMAGE_EXTENSIONS:
        return str(_convert_image_to_pdf(source, output_path))
    if ext == ".txt":
        return str(_convert_text_to_pdf(source, output_path))
    if ext in WORD_EXTENSIONS | PRESENTATION_EXTENSIONS:
        return str(_convert_office_to_pdf(source, output_path))
    if ext in {".html", ".htm"}:
        return str(_convert_html_to_pdf(source, output_path))
    if ext == ".pdf":
        shutil.copy2(source, output_path)
        return str(output_path)

    raise ValueError(f"Unsupported file format: {ext}")


def convert_pdf_to_word(input_path: str, target_extension: str = ".docx") -> str:
    """
    Convert a PDF into a Word document using Microsoft Word automation.
    """
    source = Path(input_path)
    ext = source.suffix.lower()
    target_extension = target_extension.lower()

    if ext != ".pdf":
        raise ValueError("PDF-to-Word conversion requires a PDF input file")
    if target_extension not in {".docx", ".doc"}:
        raise ValueError("PDF-to-Word conversion only supports .docx or .doc outputs")

    output_path = OUTPUT_DIR / f"{uuid.uuid4().hex}{target_extension}"
    return str(_convert_with_word_automation(source, output_path, target_extension))


def text_to_pdf(text: str, title: str | None = None) -> str:
    """
    Render raw text into a PDF document.
    """
    output_path = OUTPUT_DIR / f"{uuid.uuid4().hex}.pdf"
    _write_lines_to_pdf(text.splitlines() or [text], output_path, title=title or "Text to PDF")
    logger.info("Rendered raw text to PDF: %s", output_path)
    return str(output_path)


def _convert_image_to_pdf(source: Path, output_path: Path) -> Path:
    from PIL import Image

    image = Image.open(source)
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")
    image.save(output_path, "PDF")
    return output_path


def _convert_text_to_pdf(source: Path, output_path: Path) -> Path:
    text = source.read_text(encoding="utf-8", errors="ignore")
    _write_lines_to_pdf(text.splitlines(), output_path, title=source.name)
    return output_path


def _convert_office_to_pdf(source: Path, output_path: Path) -> Path:
    try:
        return _convert_with_word_automation(source, output_path, ".pdf")
    except RuntimeError as word_error:
        logger.info("Word automation unavailable for %s: %s", source, word_error)

    try:
        return _convert_with_libreoffice(source, output_path)
    except RuntimeError as libreoffice_error:
        raise RuntimeError(
            "High-fidelity Office conversion requires Microsoft Word or LibreOffice. "
            "Install one of them on this machine to convert DOC/DOCX/PPT/PPTX files without corruption."
        ) from libreoffice_error


def _convert_with_word_automation(source: Path, output_path: Path, target_extension: str) -> Path:
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise RuntimeError("Microsoft Word automation dependencies are not installed") from exc

    file_format_map = {
        ".pdf": 17,
        ".docx": 16,
        ".doc": 0,
    }
    if target_extension not in file_format_map:
        raise RuntimeError(f"Unsupported Word automation target: {target_extension}")

    word = None
    document = None
    pythoncom.CoInitialize()
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0

        document = word.Documents.Open(str(source), ReadOnly=False)
        document.SaveAs(str(output_path), FileFormat=file_format_map[target_extension])
    except Exception as exc:
        raise RuntimeError(
            "Microsoft Word automation is unavailable. Make sure Microsoft Word is installed and the app is running in a desktop session."
        ) from exc
    finally:
        if document is not None:
            try:
                document.Close(False)
            except Exception:
                pass
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()

    if not output_path.exists():
        raise RuntimeError("Word automation did not produce an output file")
    return output_path


def _convert_with_libreoffice(source: Path, output_path: Path) -> Path:
    office_binary = shutil.which("soffice") or shutil.which("libreoffice")
    if not office_binary:
        raise RuntimeError("LibreOffice/soffice is not installed")

    result = subprocess.run(
        [
            office_binary,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(OUTPUT_DIR),
            str(source),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "LibreOffice conversion failed")

    generated_path = OUTPUT_DIR / f"{source.stem}.pdf"
    if not generated_path.exists():
        raise RuntimeError("LibreOffice conversion did not produce an output PDF")
    if generated_path != output_path:
        generated_path.replace(output_path)
    return output_path


def _convert_html_to_pdf(source: Path, output_path: Path) -> Path:
    try:
        import pdfkit
    except ImportError as exc:
        raise RuntimeError("HTML conversion requires pdfkit and wkhtmltopdf") from exc

    pdfkit.from_file(str(source), str(output_path))
    return output_path


def _write_lines_to_pdf(lines: list[str], output_path: Path, title: str | None = None) -> None:
    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        spaceAfter=4,
    )
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        spaceAfter=12,
    )

    story = []
    if title:
        story.append(Paragraph(escape(title), title_style))
        story.append(Spacer(1, 4))

    for line in lines:
        if line.strip():
            story.append(Paragraph(escape(line), body_style))
        else:
            story.append(Spacer(1, 6))

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    doc.build(story)
