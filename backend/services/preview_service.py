"""
Helpers for preview/download payloads returned by the API.
"""

import mimetypes
from pathlib import Path

OFFICE_PREVIEW_EXTENSIONS = {".doc", ".docx", ".ppt", ".pptx"}


def infer_result_type(path: Path) -> str:
    media_type, _ = mimetypes.guess_type(path.name)
    if media_type:
        if media_type.startswith("image/"):
            return "image"
        if media_type.startswith("text/"):
            return "text"
        if media_type == "application/pdf":
            return "pdf"
        if media_type in {"application/zip", "application/x-zip-compressed"}:
            return "archive"
    if path.suffix.lower() == ".pdf":
        return "pdf"
    if path.suffix.lower() == ".zip":
        return "archive"
    if path.suffix.lower() in OFFICE_PREVIEW_EXTENSIONS:
        return "office"
    return "file"


def infer_preview_type(path: Path) -> tuple[str, str]:
    if path.suffix.lower() in OFFICE_PREVIEW_EXTENSIONS:
        return "pdf", "application/pdf"

    media_type, _ = mimetypes.guess_type(path.name)
    if media_type:
        if media_type.startswith("image/"):
            return "image", media_type
        if media_type.startswith("text/"):
            return "text", media_type
        if media_type == "application/pdf":
            return "pdf", media_type
        if media_type in {"application/zip", "application/x-zip-compressed"}:
            return "archive", media_type

    if path.suffix.lower() == ".pdf":
        return "pdf", "application/pdf"
    if path.suffix.lower() == ".zip":
        return "archive", "application/zip"
    return infer_result_type(path), media_type or "application/octet-stream"


def build_file_payload(output_path: Path, original_name: str | None = None) -> dict:
    """Build the standard preview/download metadata for a file."""
    media_type, _ = mimetypes.guess_type(output_path.name)
    preview_result_type, preview_media_type = infer_preview_type(output_path)
    return {
        "original": original_name,
        "output": output_path.name,
        "preview_url": f"/api/preview/{output_path.name}",
        "download_url": f"/api/download/{output_path.name}",
        "output_url": f"/outputs/{output_path.name}",
        "media_type": media_type or "application/octet-stream",
        "result_type": infer_result_type(output_path),
        "preview_result_type": preview_result_type,
        "preview_media_type": preview_media_type,
        "size": output_path.stat().st_size,
    }


def build_operation_payload(
    operation: str,
    outputs: list[Path],
    original_name: str | None = None,
    archive: Path | None = None,
    extra: dict | None = None,
) -> dict:
    """Build a consistent response payload for single or multi-file operations."""
    file_payloads = [build_file_payload(path, original_name) for path in outputs]
    payload = {
        "success": True,
        "operation": operation,
        "outputs": file_payloads,
        "primary_output": file_payloads[0] if file_payloads else None,
        "result_type": (
            "image_gallery"
            if file_payloads and all(item["result_type"] == "image" for item in file_payloads)
            else (file_payloads[0]["result_type"] if len(file_payloads) == 1 else "multi_file")
        ),
    }
    if archive:
        payload["archive"] = build_file_payload(archive, original_name)
    if extra:
        payload.update(extra)
    return payload
