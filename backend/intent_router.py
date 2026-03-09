"""
Semantic intent router powered by sentence-transformers.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HF_CACHE_DIR = PROJECT_ROOT / ".hf_cache"
HF_CACHE_DIR.mkdir(exist_ok=True)
os.environ.setdefault("HF_HOME", str(HF_CACHE_DIR))

from sentence_transformers import SentenceTransformer

from backend.intent_examples import TOOLS
from backend.intent_schema import IntentPlan, IntentStep
from backend.tool_registry import get_tool, resolve_tool_name

logger = logging.getLogger(__name__)


class IntentRouter:
    """Semantic intent router for PDFPilot."""

    MODEL_NAME = "all-MiniLM-L6-v2"
    UNKNOWN_THRESHOLD = 0.5
    CACHE_DIR = HF_CACHE_DIR
    _model: SentenceTransformer | None = None
    _example_embeddings: np.ndarray | None = None
    _example_items: list[tuple[str, str]] | None = None

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
        "delete",
        "remove",
        "drop",
        "rotate",
        "watermark",
        "stamp",
        "brand",
        "zip",
        "archive",
        "unzip",
        "unpack",
        "keep",
        "retain",
        "name",
        "rename",
        "call",
    )

    def __init__(self) -> None:
        self.model = self._load_model()
        self.example_items, self.example_embeddings = self._load_examples()

    def detect_intent(self, prompt: str, files: list[Path] | None = None) -> dict[str, Any]:
        plan = self.detect_plan(prompt, files=files or [])
        if not plan.intents:
            return {"intent": "unknown", "confidence": 0.0}
        if len(plan.intents) == 1:
            step = plan.intents[0]
            return {"intent": step.summary or step.intent, "confidence": step.confidence}
        return {
            "intent": [step.summary or step.intent for step in plan.intents],
            "confidence": plan.confidence,
        }

    def detect_plan(self, prompt: str, files: list[Path] | None = None, raw_text: str = "") -> IntentPlan:
        normalized = self._normalize(prompt)
        files = files or []
        if not normalized and raw_text.strip():
            return IntentPlan(
                intents=[
                    IntentStep(
                        intent="text_to_pdf",
                        confidence=0.7,
                        requires_files=False,
                        inputs={"text": raw_text},
                        summary="text_to_pdf",
                    )
                ],
                provider="semantic",
                mode="local",
                original_command=prompt,
            )

        clauses = self._split_pipeline_clauses(normalized)
        raw_steps: list[dict[str, Any]] = []
        for clause in clauses:
            candidate = self._detect_single_step(clause, files=files, previous_steps=raw_steps)
            if candidate["intent"] == "unknown":
                continue
            raw_steps.append(candidate)

        raw_steps = self._squash_redundant_steps(raw_steps, files=files)

        if not raw_steps:
            return IntentPlan(
                intents=[],
                provider="semantic",
                mode="local",
                original_command=prompt,
            )

        output_filename = self._extract_output_filename(normalized)
        steps: list[IntentStep] = []
        for index, raw_step in enumerate(raw_steps):
            inputs = dict(raw_step.get("inputs") or {})
            if output_filename and index == len(raw_steps) - 1:
                inputs["output_filename"] = output_filename

            resolved_intent = resolve_tool_name(raw_step["intent"])
            tool = get_tool(resolved_intent)
            steps.append(
                IntentStep(
                    intent=resolved_intent,
                    confidence=raw_step["confidence"],
                    requires_files=tool.requires_files,
                    inputs=inputs,
                    summary=raw_step["intent"],
                )
            )

        return IntentPlan(
            intents=steps,
            provider="semantic",
            mode="local",
            original_command=prompt,
        )

    @classmethod
    def _load_model(cls) -> SentenceTransformer:
        if cls._model is None:
            cls.CACHE_DIR.mkdir(exist_ok=True)
            os.environ.setdefault("HF_HOME", str(cls.CACHE_DIR))
            cls._model = SentenceTransformer(
                cls.MODEL_NAME,
                cache_folder=str(cls.CACHE_DIR),
                local_files_only=True,
            )
        return cls._model

    @classmethod
    def _load_examples(cls) -> tuple[list[tuple[str, str]], np.ndarray]:
        if cls._example_items is None or cls._example_embeddings is None:
            items = [(intent, example) for intent, examples in TOOLS.items() for example in examples]
            texts = [example for _, example in items]
            embeddings = cls._load_model().encode(texts, normalize_embeddings=True, show_progress_bar=False)
            cls._example_items = items
            cls._example_embeddings = np.asarray(embeddings, dtype="float32")
        return cls._example_items, cls._example_embeddings

    @staticmethod
    def _normalize(text: str) -> str:
        lowered = (text or "").strip().lower()
        return re.sub(r"\s+", " ", lowered)

    def _split_pipeline_clauses(self, text: str) -> list[str]:
        if not text:
            return []
        action_pattern = "|".join(self.ACTION_PREFIXES)
        separators = re.compile(
            rf"\b(?:and then|then|after that|afterwards|followed by|next)\b|"
            rf"\band\b(?=\s+(?:{action_pattern})\b)|"
            rf"\bafter\b(?=\s+(?:{action_pattern})\b)",
        )
        clauses = [part.strip(" ,.;") for part in separators.split(text) if part.strip(" ,.;")]
        return clauses or [text]

    def _detect_single_step(
        self,
        clause: str,
        *,
        files: list[Path],
        previous_steps: list[dict[str, Any]],
    ) -> dict[str, Any]:
        embedding = self.model.encode([clause], normalize_embeddings=True, show_progress_bar=False)
        similarities = np.dot(self.example_embeddings, np.asarray(embedding[0], dtype="float32"))

        per_tool: dict[str, list[float]] = {}
        for index, (intent, _) in enumerate(self.example_items):
            per_tool.setdefault(intent, []).append(float(similarities[index]))

        scored_tools = []
        for intent, scores in per_tool.items():
            score = max(scores)
            score = self._adjust_score(intent, score, clause=clause, files=files, previous_steps=previous_steps)
            scored_tools.append((intent, max(0.0, min(1.0, score))))

        scored_tools.sort(key=lambda item: item[1], reverse=True)
        best_intent, best_score = scored_tools[0]
        if best_score < self.UNKNOWN_THRESHOLD:
            return {"intent": "unknown", "confidence": round(best_score, 3), "inputs": {}}

        return {
            "intent": best_intent,
            "confidence": round(best_score, 3),
            "inputs": self._extract_inputs(best_intent, clause),
        }

    def _adjust_score(
        self,
        intent: str,
        score: float,
        *,
        clause: str,
        files: list[Path],
        previous_steps: list[dict[str, Any]],
    ) -> float:
        suffixes = [path.suffix.lower() for path in files]
        pdf_count = sum(1 for ext in suffixes if ext == ".pdf")
        image_count = sum(1 for ext in suffixes if ext in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".webp"})
        all_images = bool(suffixes) and image_count == len(suffixes)
        has_doc = any(ext in {".doc", ".docx", ".ppt", ".pptx", ".txt"} for ext in suffixes)

        if intent == "image_to_pdf" and all_images:
            score += 0.12
        if intent == "convert_to_pdf" and all_images:
            score -= 0.1
        if intent == "merge_pdf" and pdf_count >= 2:
            score += 0.12
        if intent == "convert_to_pdf" and has_doc:
            score += 0.1
        if intent in {"compress_pdf", "pdf_to_images", "delete_pages", "rotate_pdf", "add_watermark", "extract_text", "split_pdf"} and pdf_count == 1:
            score += 0.08
        if intent == "extract_pages" and self._is_page_request(clause):
            score += 0.15
        if intent == "pdf_to_images" and self._is_page_request(clause):
            score -= 0.12
        if intent == "split_pdf" and self._is_page_request(clause):
            score += 0.06
        if intent == "compress_pdf" and previous_steps:
            if previous_steps[-1]["intent"] in {"merge_pdf", "image_to_pdf", "convert_to_pdf", "extract_pages", "rotate_pdf", "add_watermark"}:
                score += 0.12
        if intent == "create_zip" and len(files) > 1 and "zip" in clause:
            score += 0.08
        return score

    @staticmethod
    def _squash_redundant_steps(raw_steps: list[dict[str, Any]], *, files: list[Path]) -> list[dict[str, Any]]:
        if not raw_steps:
            return raw_steps

        suffixes = [path.suffix.lower() for path in files]
        all_images = bool(suffixes) and all(ext in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".webp"} for ext in suffixes)
        squashed: list[dict[str, Any]] = []

        for step in raw_steps:
            if squashed and squashed[-1]["intent"] == step["intent"]:
                squashed[-1]["confidence"] = max(squashed[-1]["confidence"], step["confidence"])
                squashed[-1]["inputs"].update(step.get("inputs") or {})
                continue
            if (
                squashed
                and squashed[-1]["intent"] == "image_to_pdf"
                and step["intent"] == "convert_to_pdf"
                and all_images
            ):
                squashed[-1]["confidence"] = max(squashed[-1]["confidence"], step["confidence"])
                squashed[-1]["inputs"].update(step.get("inputs") or {})
                continue
            squashed.append(step)

        return squashed

    def _extract_inputs(self, intent: str, clause: str) -> dict[str, Any]:
        inputs: dict[str, Any] = {}
        if intent in {"delete_pages", "extract_pages", "split_pdf"} and self._is_page_request(clause):
            inputs["pages"] = self._extract_pages(clause)
        if intent == "extract_pages":
            inputs["output_type"] = "image" if self._wants_image_output(clause) else "pdf"
        if intent == "rotate_pdf":
            inputs["rotation"] = self._extract_rotation(clause)
        if intent == "add_watermark":
            inputs["watermark_text"] = self._extract_watermark(clause)
        if intent == "pdf_to_word":
            inputs["target_extension"] = ".doc" if " to doc" in clause and "docx" not in clause else ".docx"
        return inputs

    def _is_page_request(self, text: str) -> bool:
        has_numeric_pages = re.search(r"\d+(?:st|nd|rd|th)?(?:\s*(?:-|to|through)\s*\d+(?:st|nd|rd|th)?)?", text)
        has_word_pages = re.search(r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|last)\b", text)
        if not has_numeric_pages and not has_word_pages:
            return False
        return any(token in text for token in ("page", "pages", "keep only", "only", "just"))

    @staticmethod
    def _wants_image_output(text: str) -> bool:
        return any(token in text for token in ("image", "images", "png", "jpg", "jpeg", "picture", "pictures"))

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

    @staticmethod
    def _extract_output_filename(text: str) -> str:
        quoted_patterns = (
            r'(?:name|rename|call)\s+(?:it|this|the file|the output)?\s*(?:as|to)?\s*"([^"]+)"',
            r"(?:name|rename|call)\s+(?:it|this|the file|the output)?\s*(?:as|to)?\s*'([^']+)'",
            r'(?:named)\s+"([^"]+)"',
            r"(?:named)\s+'([^']+)'",
        )
        for pattern in quoted_patterns:
            if match := re.search(pattern, text):
                return match.group(1).strip()
        return ""
