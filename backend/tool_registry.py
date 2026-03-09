"""
Registry-backed tool execution for PDFPilot.
"""

from __future__ import annotations

import mimetypes
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fastapi import HTTPException

from backend.file_utils import (
    ARCHIVE_EXTENSIONS,
    EXTRACTABLE_EXTENSIONS,
    IMAGE_EXTENSIONS,
    PDF_EXTENSIONS,
    sanitize_filename,
)
from backend.services.archive_service import archive_files, extract_archive
from backend.services.compress_service import compress_pdf
from backend.services.convert_service import convert_pdf_to_word, convert_to_pdf, text_to_pdf
from backend.services.extract_service import extract_text
from backend.services.image_service import images_to_pdf, pdf_pages_to_images, pdf_to_images
from backend.services.merge_service import merge_pdfs
from backend.services.pdf_edit_service import add_watermark, remove_pages, rotate_pdf
from backend.services.preview_service import build_file_payload, build_operation_payload
from backend.services.split_service import extract_pages_to_pdf, split_pdf


@dataclass
class ToolExecutionContext:
    files: list[Path]
    original_names: list[str]
    raw_text: str = ""


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    handler: Callable[[ToolExecutionContext, dict], dict]
    requires_files: bool = True
    aliases: tuple[str, ...] = ()
    description: str = ""


def _build_context_name(context: ToolExecutionContext) -> str | None:
    return context.original_names[0] if len(context.original_names) == 1 else None


def _ensure_single_file(paths: list[Path], message: str = "Exactly one file is required") -> Path:
    if len(paths) != 1:
        raise HTTPException(status_code=400, detail=message)
    return paths[0]


def _ensure_pdf(path: Path) -> None:
    if path.suffix.lower() not in PDF_EXTENSIONS:
        raise HTTPException(status_code=400, detail="This operation requires a PDF file")


def _ensure_pdf_source(path: Path) -> Path:
    if path.suffix.lower() in PDF_EXTENSIONS:
        return path
    if path.suffix.lower() in {".doc", ".docx", ".ppt", ".pptx"}:
        return Path(convert_to_pdf(str(path)))
    raise HTTPException(status_code=400, detail="This operation requires a PDF, DOC, DOCX, PPT, or PPTX file")


def _ensure_images(paths: list[Path]) -> None:
    if not paths or any(path.suffix.lower() not in IMAGE_EXTENSIONS for path in paths):
        raise HTTPException(status_code=400, detail="This operation requires one or more image files")


def _single_output_payload(
    operation: str,
    output_path: Path,
    context: ToolExecutionContext,
    *,
    extra: dict | None = None,
) -> dict:
    return build_operation_payload(
        operation,
        [output_path],
        original_name=_build_context_name(context),
        extra=extra,
    )


def _text_to_pdf(context: ToolExecutionContext, inputs: dict) -> dict:
    content = (inputs.get("text") or context.raw_text or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="No text content was provided for text-to-PDF conversion")
    output_path = Path(text_to_pdf(content, title="PDFPilot Text"))
    return _single_output_payload("text_to_pdf", output_path, context)


def _convert_to_pdf(context: ToolExecutionContext, inputs: dict) -> dict:
    source = _ensure_single_file(context.files, "Convert-to-PDF requires one uploaded file")
    output_path = Path(convert_to_pdf(str(source)))
    return _single_output_payload("convert_to_pdf", output_path, context)


def _images_to_pdf(context: ToolExecutionContext, inputs: dict) -> dict:
    _ensure_images(context.files)
    output_path = Path(images_to_pdf([str(path) for path in context.files]))
    return _single_output_payload("images_to_pdf", output_path, context)


def _extract_images(context: ToolExecutionContext, inputs: dict) -> dict:
    source = _ensure_single_file(context.files, "PDF-to-images requires one uploaded PDF")
    _ensure_pdf(source)
    image_format = str(inputs.get("image_format") or "png").lower()
    image_paths, archive_path = pdf_to_images(str(source), image_format=image_format)
    return build_operation_payload(
        "extract_images",
        [Path(path) for path in image_paths],
        original_name=_build_context_name(context),
        archive=Path(archive_path),
        extra={"image_format": image_format},
    )


def _pdf_to_word(context: ToolExecutionContext, inputs: dict) -> dict:
    source = _ensure_single_file(context.files, "PDF-to-Word requires one uploaded PDF")
    _ensure_pdf(source)
    target_extension = str(inputs.get("target_extension") or ".docx").lower()
    output_path = Path(convert_pdf_to_word(str(source), target_extension))
    return _single_output_payload(
        "pdf_to_word",
        output_path,
        context,
        extra={"target_extension": target_extension},
    )


def _merge_pdf(context: ToolExecutionContext, inputs: dict) -> dict:
    if len(context.files) < 2:
        raise HTTPException(status_code=400, detail="Merge requires at least two PDF files")
    if any(path.suffix.lower() not in PDF_EXTENSIONS for path in context.files):
        raise HTTPException(status_code=400, detail="Merge only supports PDF files")
    output_path = Path(merge_pdfs([str(path) for path in context.files]))
    return _single_output_payload(
        "merge_pdf",
        output_path,
        context,
        extra={"merged_count": len(context.files)},
    )


def _split_pdf(context: ToolExecutionContext, inputs: dict) -> dict:
    source = _ensure_single_file(context.files, "Split requires one uploaded PDF")
    _ensure_pdf(source)
    page_selection = str(inputs.get("pages") or "all")
    output_paths = [Path(path) for path in split_pdf(str(source), page_selection)]
    return build_operation_payload(
        "split_pdf",
        output_paths,
        original_name=_build_context_name(context),
        extra={"parts": len(output_paths), "page_selection": page_selection},
    )


def _extract_pages(context: ToolExecutionContext, inputs: dict) -> dict:
    source = _ensure_single_file(context.files, "Page extraction requires one uploaded file")
    pdf_source = _ensure_pdf_source(source)
    page_selection = str(inputs.get("pages") or "all")
    output_type = str(inputs.get("output_type") or "pdf").lower()

    if output_type == "image":
        image_paths, archive_path = pdf_pages_to_images(str(pdf_source), page_selection)
        return build_operation_payload(
            "extract_pages",
            [Path(path) for path in image_paths],
            original_name=_build_context_name(context),
            archive=Path(archive_path),
            extra={"page_selection": page_selection, "output_type": output_type},
        )

    output_path = Path(extract_pages_to_pdf(str(pdf_source), page_selection))
    return _single_output_payload(
        "extract_pages",
        output_path,
        context,
        extra={"page_selection": page_selection, "output_type": output_type},
    )


def _compress_pdf(context: ToolExecutionContext, inputs: dict) -> dict:
    source = _ensure_single_file(context.files, "Compress requires one uploaded PDF")
    _ensure_pdf(source)
    original_size = source.stat().st_size
    output_path = Path(compress_pdf(str(source)))
    compressed_size = output_path.stat().st_size
    reduction_pct = round((1 - compressed_size / original_size) * 100, 1) if original_size else 0
    return _single_output_payload(
        "compress_pdf",
        output_path,
        context,
        extra={
            "original_size": original_size,
            "compressed_size": compressed_size,
            "reduction_pct": reduction_pct,
        },
    )


def _extract_text(context: ToolExecutionContext, inputs: dict) -> dict:
    source = _ensure_single_file(context.files, "Extract text requires one uploaded file")
    if source.suffix.lower() not in EXTRACTABLE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="This file type is not supported for text extraction")
    text, output_path = extract_text(str(source))
    return _single_output_payload(
        "extract_text",
        Path(output_path),
        context,
        extra={"text_preview": text, "extracted_text": text, "word_count": len(text.split())},
    )


def _rotate_pdf(context: ToolExecutionContext, inputs: dict) -> dict:
    source = _ensure_single_file(context.files, "Rotate requires one uploaded PDF")
    _ensure_pdf(source)
    rotation = int(inputs.get("rotation") or 90)
    output_path = Path(rotate_pdf(str(source), rotation))
    return _single_output_payload(
        "rotate_pdf",
        output_path,
        context,
        extra={"rotation": rotation},
    )


def _add_watermark(context: ToolExecutionContext, inputs: dict) -> dict:
    source = _ensure_single_file(context.files, "Add watermark requires one uploaded PDF")
    _ensure_pdf(source)
    watermark_text = str(inputs.get("watermark_text") or "PDFPilot")
    output_path = Path(add_watermark(str(source), watermark_text))
    return _single_output_payload(
        "add_watermark",
        output_path,
        context,
        extra={"watermark_text": watermark_text},
    )


def _remove_pages(context: ToolExecutionContext, inputs: dict) -> dict:
    source = _ensure_single_file(context.files, "Remove pages requires one uploaded file")
    pdf_source = _ensure_pdf_source(source)
    pages = str(inputs.get("pages") or "")
    output_path = Path(remove_pages(str(pdf_source), pages))
    return _single_output_payload(
        "remove_pages",
        output_path,
        context,
        extra={"removed_pages": pages},
    )


def _create_zip(context: ToolExecutionContext, inputs: dict) -> dict:
    if not context.files:
        raise HTTPException(status_code=400, detail="Attach one or more files to create a ZIP archive")
    if any(path.suffix.lower() in ARCHIVE_EXTENSIONS for path in context.files):
        raise HTTPException(status_code=400, detail="ZIP input is not supported for archive creation")
    output_path = Path(archive_files([str(path) for path in context.files]))
    payload = _single_output_payload(
        "create_zip",
        output_path,
        context,
        extra={"archived_count": len(context.files)},
    )
    payload["archive"] = payload["primary_output"]
    return payload


def _extract_zip(context: ToolExecutionContext, inputs: dict) -> dict:
    source = _ensure_single_file(context.files, "ZIP extraction requires one uploaded ZIP file")
    if source.suffix.lower() not in ARCHIVE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="This operation requires a ZIP file")
    output_paths = [Path(path) for path in extract_archive(str(source))]
    return build_operation_payload(
        "extract_zip",
        output_paths,
        original_name=_build_context_name(context),
        extra={"extracted_count": len(output_paths)},
    )


TOOL_REGISTRY: dict[str, ToolDefinition] = {
    "text_to_pdf": ToolDefinition(
        name="text_to_pdf",
        handler=_text_to_pdf,
        requires_files=False,
        description="Render raw text into a PDF.",
    ),
    "convert_to_pdf": ToolDefinition(
        name="convert_to_pdf",
        handler=_convert_to_pdf,
        description="Convert a supported file into PDF.",
    ),
    "images_to_pdf": ToolDefinition(
        name="images_to_pdf",
        handler=_images_to_pdf,
        aliases=("image_to_pdf",),
        description="Combine uploaded images into a PDF.",
    ),
    "extract_images": ToolDefinition(
        name="extract_images",
        handler=_extract_images,
        aliases=("pdf_to_images",),
        description="Export PDF pages as images.",
    ),
    "pdf_to_word": ToolDefinition(
        name="pdf_to_word",
        handler=_pdf_to_word,
        description="Convert PDF to DOCX or DOC.",
    ),
    "merge_pdf": ToolDefinition(
        name="merge_pdf",
        handler=_merge_pdf,
        aliases=("merge_pdfs",),
        description="Merge multiple PDFs into one file.",
    ),
    "split_pdf": ToolDefinition(
        name="split_pdf",
        handler=_split_pdf,
        description="Split a PDF into separate outputs.",
    ),
    "extract_pages": ToolDefinition(
        name="extract_pages",
        handler=_extract_pages,
        description="Extract selected pages to PDF or image output.",
    ),
    "compress_pdf": ToolDefinition(
        name="compress_pdf",
        handler=_compress_pdf,
        description="Compress a PDF.",
    ),
    "extract_text": ToolDefinition(
        name="extract_text",
        handler=_extract_text,
        description="Extract text from a supported document.",
    ),
    "rotate_pdf": ToolDefinition(
        name="rotate_pdf",
        handler=_rotate_pdf,
        description="Rotate every page in a PDF.",
    ),
    "add_watermark": ToolDefinition(
        name="add_watermark",
        handler=_add_watermark,
        description="Apply a text watermark to a PDF.",
    ),
    "remove_pages": ToolDefinition(
        name="remove_pages",
        handler=_remove_pages,
        aliases=("delete_pages",),
        description="Remove selected pages from a PDF.",
    ),
    "create_zip": ToolDefinition(
        name="create_zip",
        handler=_create_zip,
        aliases=("archive_files",),
        description="Bundle files into a ZIP archive.",
    ),
    "extract_zip": ToolDefinition(
        name="extract_zip",
        handler=_extract_zip,
        aliases=("extract_archive",),
        description="Extract a ZIP archive.",
    ),
}

TOOL_ALIASES = {
    alias: name
    for name, definition in TOOL_REGISTRY.items()
    for alias in definition.aliases
}


def resolve_tool_name(name: str) -> str:
    normalized = (name or "").strip().lower()
    if normalized in TOOL_REGISTRY:
        return normalized
    if normalized in TOOL_ALIASES:
        return TOOL_ALIASES[normalized]
    raise KeyError(f"Unsupported tool: {name}")


def get_tool(name: str) -> ToolDefinition:
    return TOOL_REGISTRY[resolve_tool_name(name)]


def list_tool_names() -> list[str]:
    return sorted(TOOL_REGISTRY.keys())


def _apply_requested_output_name(payload: dict, requested_name: str | None) -> dict:
    if not requested_name:
        return payload

    outputs = payload.get("outputs") or []
    if len(outputs) != 1:
        return payload

    current = outputs[0]
    current_name = current.get("output")
    if not current_name:
        return payload

    current_path = Path(__file__).resolve().parent.parent / "outputs" / Path(current_name).name
    if not current_path.exists():
        return payload

    desired = Path(sanitize_filename(requested_name))
    desired_stem = desired.stem or current_path.stem
    desired_ext = desired.suffix.lower()
    actual_ext = current_path.suffix.lower()
    target_path = current_path.with_name(f"{desired_stem}{actual_ext if desired_ext != actual_ext else desired_ext}")

    if target_path != current_path and target_path.exists():
        suffix = actual_ext if desired_ext != actual_ext else desired_ext
        target_path = current_path.with_name(f"{desired_stem}_{uuid.uuid4().hex[:8]}{suffix}")

    if target_path != current_path:
        current_path.replace(target_path)

    renamed_payload = build_file_payload(target_path, current.get("original"))
    payload["outputs"] = [renamed_payload]
    payload["primary_output"] = renamed_payload
    payload["result_type"] = renamed_payload["result_type"]

    archive = payload.get("archive")
    if isinstance(archive, dict) and archive.get("output") == current_name:
        payload["archive"] = renamed_payload

    return payload


def execute_tool(name: str, context: ToolExecutionContext, inputs: dict | None = None) -> dict:
    definition = get_tool(name)
    if definition.requires_files and not context.files:
        raise HTTPException(status_code=400, detail=f"{definition.name} requires one or more files")
    input_values = inputs or {}
    payload = definition.handler(context, input_values)
    payload["operation"] = definition.name
    payload = _apply_requested_output_name(payload, input_values.get("output_filename"))
    payload["status"] = "success"
    return payload


def result_paths(payload: dict) -> list[Path]:
    outputs = payload.get("outputs") or []
    paths: list[Path] = []
    for item in outputs:
        output_name = item.get("output")
        if output_name:
            paths.append(Path(__file__).resolve().parent.parent / "outputs" / Path(output_name).name)
    return [path for path in paths if path.exists()]


def preview_kind_for_path(path: Path) -> tuple[str, str]:
    media_type, _ = mimetypes.guess_type(path.name)
    return media_type or "application/octet-stream", path.suffix.lower()
