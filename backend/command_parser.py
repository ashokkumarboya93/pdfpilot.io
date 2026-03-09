"""
Local natural-language command parsing for PDFPilot.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.intent_schema import IntentPlan, IntentStep


class LocalCommandParser:
    """A lightweight NLP parser used when no hosted router is configured."""

    PAGE_WORDS = {
        "first": "1",
        "second": "2",
        "third": "3",
        "fourth": "4",
        "fifth": "5",
        "sixth": "6",
        "seventh": "7",
        "eighth": "8",
        "ninth": "9",
        "tenth": "10",
        "last": "last",
    }

    ACTION_PREFIXES = (
        "merge",
        "combine",
        "join",
        "put",
        "convert",
        "turn",
        "export",
        "save",
        "make",
        "create",
        "split",
        "separate",
        "break",
        "extract",
        "get",
        "read",
        "compress",
        "reduce",
        "shrink",
        "optimize",
        "rotate",
        "watermark",
        "stamp",
        "brand",
        "remove",
        "delete",
        "drop",
        "omit",
        "zip",
        "archive",
        "unzip",
        "unpack",
        "open",
        "keep",
        "retain",
        "name",
        "rename",
        "call",
    )

    def parse(self, command: str, files: list[Path], raw_text: str = "") -> IntentPlan:
        normalized = self._normalize(command)
        if not normalized and raw_text.strip():
            return IntentPlan(
                intents=[
                    IntentStep(
                        intent="text_to_pdf",
                        confidence=0.7,
                        requires_files=False,
                        inputs={"text": raw_text},
                        summary="No command provided, treating the supplied text as PDF content.",
                    )
                ],
                original_command=command,
            )

        clauses = self._split_pipeline_clauses(normalized)
        steps: list[IntentStep] = []
        for clause in clauses:
            step = self._parse_single_clause(clause, files=files, raw_text=raw_text, prior_steps=steps)
            if not step:
                if len(clauses) == 1:
                    raise ValueError("Could not determine intent")
                continue
            if steps and steps[-1].intent == step.intent and steps[-1].inputs == step.inputs:
                continue
            steps.append(step)

        if not steps:
            raise ValueError("Could not determine intent")

        output_filename = self._extract_output_filename(normalized)
        if output_filename:
            steps[-1].inputs["output_filename"] = output_filename

        return IntentPlan(intents=steps, original_command=command)

    @staticmethod
    def _normalize(text: str) -> str:
        lowered = (text or "").strip().lower()
        return re.sub(r"\s+", " ", lowered)

    def _split_pipeline_clauses(self, text: str) -> list[str]:
        if not text:
            return []

        action_pattern = "|".join(self.ACTION_PREFIXES)
        separators = re.compile(
            rf"\b(?:and then|then|after that|afterwards|followed by|next|also)\b|"
            rf"\band\b(?=\s+(?:{action_pattern})\b)",
        )
        clauses = [
            part.strip(" ,.;")
            for part in separators.split(text)
            if part and part.strip(" ,.;")
        ]
        return clauses or [text]

    def _parse_single_clause(
        self,
        text: str,
        *,
        files: list[Path],
        raw_text: str,
        prior_steps: list[IntentStep],
    ) -> IntentStep | None:
        suffixes = [path.suffix.lower() for path in files]
        has_pdf = any(ext == ".pdf" for ext in suffixes)
        pdf_count = sum(1 for ext in suffixes if ext == ".pdf")
        has_images = any(ext in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".webp"} for ext in suffixes)
        images_only = bool(suffixes) and all(ext in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".webp"} for ext in suffixes)
        has_text = any(ext == ".txt" for ext in suffixes)
        has_doc = any(ext in {".doc", ".docx"} for ext in suffixes)
        has_slide = any(ext in {".ppt", ".pptx"} for ext in suffixes)
        has_archive = any(ext == ".zip" for ext in suffixes)
        single_document = len(files) == 1 and (has_pdf or has_doc or has_slide)

        if has_archive and self._matches(text, "extract zip", "extract this zip", "extract archive", "unzip", "unpack", "open zip", "decompress zip"):
            return self._step("extract_zip", 0.98, summary="Detected a ZIP extraction request.")

        if self._is_zip_create_request(text):
            return self._step("create_zip", 0.96, summary="Detected a ZIP creation request.")

        if self._wants_pdf_output(text):
            if raw_text.strip() and not files:
                return self._step(
                    "text_to_pdf",
                    0.96,
                    requires_files=False,
                    inputs={"text": raw_text},
                    summary="Detected a request to render supplied text into a PDF.",
                )
            if has_images and images_only:
                return self._step("images_to_pdf", 0.95, summary="Detected an image-to-PDF request.")
            if has_text or has_doc or has_slide or has_images or has_pdf:
                return self._step("convert_to_pdf", 0.92, summary="Detected a file-to-PDF conversion request.")

        if self._is_merge_request(text, pdf_count):
            return self._step("merge_pdf", 0.97, summary="Detected a PDF merge request.")

        if has_pdf and self._wants_word_output(text):
            target_extension = ".doc" if " to doc" in text and "docx" not in text else ".docx"
            return self._step(
                "pdf_to_word",
                0.94,
                inputs={"target_extension": target_extension},
                summary="Detected a PDF-to-Word conversion request.",
            )

        if self._matches(text, "rotate", "turn around", "change orientation", "rotate clockwise", "rotate anticlockwise", "rotate counterclockwise"):
            return self._step(
                "rotate_pdf",
                0.9,
                inputs={"rotation": self._extract_rotation(text)},
                summary="Detected a PDF rotation request.",
            )

        if self._matches(text, "watermark", "stamp", "brand", "mark as", "mark this as", "add logo", "confidential"):
            return self._step(
                "add_watermark",
                0.89,
                inputs={"watermark_text": self._extract_watermark(text)},
                summary="Detected a watermark request.",
            )

        if self._is_remove_pages_request(text):
            return self._step(
                "remove_pages",
                0.95,
                inputs={"pages": self._extract_pages(text)},
                summary="Detected a page removal request.",
            )

        if single_document and self._is_extract_pages_request(text):
            output_type = "image" if self._wants_image_output(text) else "pdf"
            return self._step(
                "extract_pages",
                0.95,
                inputs={"pages": self._extract_pages(text), "output_type": output_type},
                summary="Detected a specific-page extraction request.",
            )

        if has_pdf and self._wants_image_output(text):
            return self._step("extract_images", 0.93, summary="Detected a PDF-to-images request.")

        if self._is_split_request(text):
            return self._step(
                "split_pdf",
                0.94,
                inputs={"pages": self._extract_pages(text)},
                summary="Detected a PDF split request.",
            )

        if self._matches(text, "compress", "make smaller", "reduce size", "reduce file size", "shrink", "optimize"):
            if prior_steps and prior_steps[-1].intent in {
                "merge_pdf",
                "convert_to_pdf",
                "text_to_pdf",
                "images_to_pdf",
                "extract_pages",
                "rotate_pdf",
                "add_watermark",
                "remove_pages",
            }:
                return self._step("compress_pdf", 0.92, summary="Detected a follow-up PDF compression request.")
            if len(files) == 1 and has_pdf:
                return self._step("compress_pdf", 0.92, summary="Detected a PDF compression request.")
            if len(files) > 1:
                return self._step("create_zip", 0.86, summary="Detected a multi-file compression request best served by ZIP.")

        if self._matches(text, "extract text", "get text", "pull text", "read text", "read this", "ocr", "what does this say", "text from", "grab text"):
            return self._step("extract_text", 0.93, summary="Detected a text extraction request.")

        if raw_text.strip() and not files:
            return self._step(
                "text_to_pdf",
                0.7,
                requires_files=False,
                inputs={"text": raw_text},
                summary="No file attached, treating the provided text as PDF content.",
            )

        return None

    def _step(
        self,
        intent: str,
        confidence: float,
        *,
        requires_files: bool = True,
        inputs: dict | None = None,
        summary: str = "",
    ) -> IntentStep:
        return IntentStep(
            intent=intent,
            confidence=confidence,
            requires_files=requires_files,
            inputs=inputs or {},
            summary=summary,
        )

    @staticmethod
    def _matches(text: str, *phrases: str) -> bool:
        return any(phrase in text for phrase in phrases)

    def _wants_pdf_output(self, text: str) -> bool:
        return self._matches(
            text,
            "to pdf",
            "into pdf",
            "into a pdf",
            "turn into pdf",
            "convert to pdf",
            "save as pdf",
            "export as pdf",
            "export to pdf",
            "make pdf",
            "make a pdf",
            "create pdf",
            "generate pdf",
        )

    def _wants_image_output(self, text: str) -> bool:
        return self._matches(
            text,
            "pdf to image",
            "pdf to images",
            "to image",
            "to images",
            "save as image",
            "save as images",
            "as image",
            "as images",
            "image",
            "images",
            "png",
            "jpg",
            "jpeg",
            "picture",
            "pictures",
            "extract images",
        )

    def _wants_word_output(self, text: str) -> bool:
        return self._matches(
            text,
            "to docx",
            "to doc",
            "to word",
            "word document",
            "convert to word",
            "save as word",
            "export to word",
            "into doc",
        )

    def _is_merge_request(self, text: str, pdf_count: int) -> bool:
        if pdf_count < 2:
            return False
        if self._matches(
            text,
            "merge",
            "combine",
            "join",
            "put these together",
            "put these files together",
            "stitch together",
            "one pdf",
            "single pdf",
            "into one",
        ):
            return True
        references_files = self._matches(text, "these files", "these pdfs", "these documents", "all pdfs", "all documents")
        return references_files and self._matches(text, "together", "one file", "single file")

    @staticmethod
    def _extract_output_filename(text: str) -> str:
        quoted_patterns = (
            r'(?:name|rename|call)\s+(?:it|this|the file|the output)?\s*(?:as|to)?\s*"([^"]+)"',
            r"(?:name|rename|call)\s+(?:it|this|the file|the output)?\s*(?:as|to)?\s*'([^']+)'",
        )
        for pattern in quoted_patterns:
            if match := re.search(pattern, text):
                return match.group(1).strip()

        plain_patterns = (
            r"(?:name|rename|call)\s+(?:it|this|the file|the output)?\s*(?:as|to)\s+([a-z0-9._ -]+\.[a-z0-9]{2,5})",
            r"(?:named)\s+([a-z0-9._ -]+\.[a-z0-9]{2,5})",
        )
        for pattern in plain_patterns:
            if match := re.search(pattern, text):
                return match.group(1).strip()

        return ""

    def _is_zip_create_request(self, text: str) -> bool:
        if re.search(r"\bzip\b", text) and not self._matches(text, "unzip", "extract zip", "open zip"):
            return True
        return self._matches(
            text,
            "archive this",
            "archive these",
            "archive files",
            "create archive",
            "make archive",
            "package these files",
            "download as archive",
        )

    def _is_remove_pages_request(self, text: str) -> bool:
        return self._matches(text, "remove", "delete", "drop", "omit", "exclude") and self._is_page_request(text)

    def _is_extract_pages_request(self, text: str) -> bool:
        if not self._is_page_request(text):
            return False
        return self._matches(
            text,
            "extract",
            "keep only",
            "retain only",
            "just page",
            "only page",
            "give me page",
            "take page",
            "page",
            "pages",
        )

    def _is_split_request(self, text: str) -> bool:
        return self._matches(
            text,
            "split",
            "separate pages",
            "break this document into pages",
            "break this pdf into pages",
            "one page per file",
            "divide into pages",
            "slice",
        )

    def _is_page_request(self, text: str) -> bool:
        has_numeric_pages = re.search(r"\d+(?:st|nd|rd|th)?(?:\s*(?:-|to|through)\s*\d+(?:st|nd|rd|th)?)?", text)
        has_word_pages = re.search(r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|last)\b", text)
        if not has_numeric_pages and not has_word_pages:
            return False
        return self._matches(text, "page", "pages", "page number", "page no", "range", "keep only", "only", "just")

    def _extract_pages(self, text: str) -> str:
        if numeric_range_match := re.search(r"\b(\d+)\b\s*(?:to|-|through)\s*\b(\d+|last)\b", text):
            return f"{numeric_range_match.group(1)}-{numeric_range_match.group(2)}"

        if match := re.search(r"(\d+(?:\s*-\s*\d+)?(?:\s*,\s*\d+(?:\s*-\s*\d+)?)*)", text):
            return match.group(1).replace(" ", "")

        if range_match := re.search(
            r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|last)\b\s*(?:to|-|through)\s*\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|last)\b",
            text,
        ):
            start = self.PAGE_WORDS[range_match.group(1)]
            end = self.PAGE_WORDS[range_match.group(2)]
            return f"{start}-{end}"

        for word, value in self.PAGE_WORDS.items():
            if re.search(rf"\b{word}\b", text):
                return value

        return "all"

    @staticmethod
    def _extract_rotation(text: str) -> int:
        if match := re.search(r"(90|180|270)", text):
            return int(match.group(1))
        if "left" in text or "counterclockwise" in text or "anticlockwise" in text:
            return 270
        if "upside down" in text:
            return 180
        return 90

    @staticmethod
    def _extract_watermark(text: str) -> str:
        if quoted := re.search(r'"([^"]+)"', text):
            return quoted.group(1)
        if "confidential" in text:
            return "CONFIDENTIAL"
        parts = text.split("watermark", 1)
        candidate = parts[1].strip() if len(parts) > 1 else ""
        return candidate or "PDFPilot"
