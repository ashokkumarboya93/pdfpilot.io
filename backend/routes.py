"""
PDFPilot API routes.
"""

from __future__ import annotations

import logging
import mimetypes
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.ai_router import AICommandRouter
from backend.file_utils import (
    EXTRACTABLE_EXTENSIONS,
    OUTPUT_DIR,
    PDF_EXTENSIONS,
    resolve_existing_file,
    resolve_existing_files,
    save_upload,
)
from backend.services.compress_service import compress_pdf
from backend.services.convert_service import convert_to_pdf
from backend.services.extract_service import extract_text
from backend.services.merge_service import merge_pdfs
from backend.services.preview_service import OFFICE_PREVIEW_EXTENSIONS, build_file_payload, build_operation_payload
from backend.services.split_service import split_pdf
from backend.tool_registry import ToolExecutionContext, execute_tool, result_paths

logger = logging.getLogger(__name__)
router = APIRouter()
command_router = AICommandRouter()


class ProcessRequest(BaseModel):
    command: str
    files: list[str] = Field(default_factory=list)
    text: str = ""


def build_inline_response(filepath: Path, filename: str) -> FileResponse:
    media_type, _ = mimetypes.guess_type(filename)
    return FileResponse(
        filepath,
        filename=filename,
        media_type=media_type or "application/octet-stream",
        content_disposition_type="inline",
    )


def execute_plan(command: str, files: list[Path], original_names: list[str], raw_text: str = "") -> dict:
    plan = command_router.detect_intent(command=command, files=files, raw_text=raw_text)
    current_files = files
    current_names = original_names or [path.name for path in files]
    final_payload: dict = {}
    pipeline: list[dict] = []

    for step in plan.intents:
        result = execute_tool(
            step.intent,
            ToolExecutionContext(files=current_files, original_names=current_names, raw_text=raw_text),
            inputs=step.inputs,
        )
        outputs = [item.get("output", "") for item in result.get("outputs", [])]
        pipeline.append(
            {
                "intent": step.intent,
                "confidence": step.confidence,
                "summary": step.summary,
                "operation": result.get("operation"),
                "outputs": outputs,
            }
        )
        current_files = result_paths(result)
        current_names = [path.name for path in current_files]
        final_payload = result

    logger.info(
        "USER COMMAND: %s | INTENTS: %s | OUTPUT: %s",
        command,
        ", ".join(step["intent"] for step in pipeline),
        ", ".join(pipeline[-1]["outputs"]) if pipeline else "",
    )

    final_payload.update(
        {
            "intent": plan.primary_intent,
            "intents": [step.intent for step in plan.intents],
            "confidence": plan.confidence,
            "provider": plan.provider,
            "mode": plan.mode,
            "pipeline": pipeline,
        }
    )
    return final_payload


async def parse_process_request(request: Request) -> tuple[str, list[Path], list[str], str]:
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        body = ProcessRequest.model_validate(await request.json())
        files = resolve_existing_files(body.files) if body.files else []
        original_names = [Path(name).name for name in body.files] if body.files else []
        return body.command.strip(), files, original_names, body.text.strip()

    form = await request.form()
    command = str(form.get("command", "")).strip()
    raw_text = str(form.get("text", "") or form.get("raw_text", "")).strip()

    filenames_field = form.get("filenames")
    resolved_named_files = []
    original_names: list[str] = []
    if filenames_field:
        names = [part.strip() for part in str(filenames_field).split(",") if part.strip()]
        resolved_named_files = resolve_existing_files(names)
        original_names.extend([Path(name).name for name in names])

    uploads = []
    if "file" in form:
        file_item = form.get("file")
        if hasattr(file_item, "filename") and hasattr(file_item, "file"):
            uploads.append(file_item)
    uploads.extend(
        item for item in form.getlist("files") if hasattr(item, "filename") and hasattr(item, "file")
    )

    uploaded_paths: list[Path] = []
    for upload in uploads:
        saved_path = save_upload(upload)
        uploaded_paths.append(saved_path)
        original_names.append(upload.filename or saved_path.name)

    return command, resolved_named_files + uploaded_paths, original_names, raw_text


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "PDFPilot",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "router_mode": command_router.mode,
    }


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> dict:
    try:
        filepath = save_upload(file)
        return {
            "success": True,
            "filename": file.filename,
            "server_filename": filepath.name,
            "size": filepath.stat().st_size,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/convert")
async def api_convert(file: UploadFile = File(...)) -> dict:
    try:
        filepath = save_upload(file)
        output_path = Path(convert_to_pdf(str(filepath)))
        return {"success": True, **build_file_payload(output_path, file.filename)}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Convert failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/merge")
async def api_merge(files: list[UploadFile] = File(...)) -> dict:
    try:
        uploaded = [save_upload(file, allowed_extensions=PDF_EXTENSIONS) for file in files]
        if len(uploaded) < 2:
            raise HTTPException(status_code=400, detail="Merge requires at least two PDF files")
        output_path = Path(merge_pdfs([str(path) for path in uploaded]))
        return {
            "success": True,
            "merged_count": len(uploaded),
            **build_file_payload(output_path),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Merge failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/split")
async def api_split(file: UploadFile = File(...), pages: str = Form("all")) -> dict:
    try:
        filepath = save_upload(file, allowed_extensions=PDF_EXTENSIONS)
        output_paths = [Path(path) for path in split_pdf(str(filepath), pages)]
        return build_operation_payload(
            "split_pdf",
            output_paths,
            original_name=file.filename,
            extra={"parts": len(output_paths), "page_selection": pages},
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Split failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/compress")
async def api_compress(file: UploadFile = File(...)) -> dict:
    try:
        filepath = save_upload(file, allowed_extensions=PDF_EXTENSIONS)
        original_size = filepath.stat().st_size
        output_path = Path(compress_pdf(str(filepath)))
        compressed_size = output_path.stat().st_size
        reduction_pct = round((1 - compressed_size / original_size) * 100, 1) if original_size else 0
        return {
            "success": True,
            "original_size": original_size,
            "compressed_size": compressed_size,
            "reduction_pct": reduction_pct,
            **build_file_payload(output_path, file.filename),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Compress failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/extract")
async def api_extract(file: UploadFile = File(...)) -> dict:
    try:
        filepath = save_upload(file, allowed_extensions=EXTRACTABLE_EXTENSIONS)
        text, output_path = extract_text(str(filepath))
        return {
            "success": True,
            "word_count": len(text.split()),
            "text_preview": text,
            "extracted_text": text,
            **build_file_payload(Path(output_path), file.filename),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Extract failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/process")
async def api_process(request: Request) -> dict:
    try:
        command, files, original_names, raw_text = await parse_process_request(request)
        if not command:
            raise HTTPException(status_code=400, detail="A command is required")
        if not files and not raw_text.strip():
            raise HTTPException(status_code=400, detail="Attach file(s) or provide text content to process")
        return execute_plan(command=command, files=files, original_names=original_names, raw_text=raw_text)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "Could not determine intent") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Process command failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/preview/{filename}")
async def preview_file(filename: str) -> FileResponse:
    filepath = resolve_existing_file(filename)
    if not filepath:
        raise HTTPException(status_code=404, detail="Preview not found")
    if filepath.suffix.lower() in OFFICE_PREVIEW_EXTENSIONS:
        try:
            preview_path = Path(convert_to_pdf(str(filepath)))
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return build_inline_response(preview_path, preview_path.name)
    return build_inline_response(filepath, Path(filename).name)


@router.get("/download/{filename}")
async def download_file(filename: str) -> FileResponse:
    filepath = OUTPUT_DIR / Path(filename).name
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    media_type, _ = mimetypes.guess_type(filepath.name)
    return FileResponse(
        filepath,
        filename=filepath.name,
        media_type=media_type or "application/octet-stream",
    )


@router.get("/history")
async def file_history() -> dict:
    files = []
    for filepath in sorted(OUTPUT_DIR.glob("*"), key=lambda path: path.stat().st_ctime, reverse=True):
        if not filepath.is_file():
            continue
        stat = filepath.stat()
        item = build_file_payload(filepath)
        item["created"] = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat()
        files.append(item)
    return {"files": files, "total": len(files)}
