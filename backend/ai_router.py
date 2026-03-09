"""
AI-assisted intent routing with a local NLP fallback.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

from backend.command_parser import LocalCommandParser
from backend.intent_schema import IntentPlan, IntentStep
from backend.tool_registry import list_tool_names, resolve_tool_name

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from backend.intent_router import IntentRouter


class AICommandRouter:
    """
    Routing layer that can call a hosted model, with a local NLP fallback.
    """

    def __init__(self) -> None:
        self.mode = os.getenv("PDFPILOT_ROUTER_MODE", "local").lower()
        self.model = os.getenv("PDFPILOT_AI_ROUTER_MODEL", "")
        self.endpoint = os.getenv("PDFPILOT_AI_ROUTER_URL", "").strip()
        self.api_key = os.getenv("PDFPILOT_AI_ROUTER_API_KEY", "").strip()
        self.semantic_router: IntentRouter | None = self._build_semantic_router()
        self.local_parser = LocalCommandParser()

    def detect_intent(self, command: str, files: list[Path], raw_text: str = "") -> IntentPlan:
        if self.mode != "local":
            remote_plan = self._detect_with_hosted_model(command=command, files=files, raw_text=raw_text)
            if remote_plan is not None:
                return remote_plan

        if self.semantic_router is not None:
            semantic_plan = self.semantic_router.detect_plan(prompt=command, files=files, raw_text=raw_text)
            if semantic_plan.intents:
                semantic_plan.provider = "semantic"
                semantic_plan.mode = self.mode
                semantic_plan.original_command = command
                return semantic_plan.require_steps()

        plan = self.local_parser.parse(command=command, files=files, raw_text=raw_text)
        plan.provider = "local"
        plan.mode = self.mode
        plan.original_command = command
        return plan.require_steps()

    def route(self, command: str, files: list[Path], raw_text: str = "") -> dict[str, Any]:
        plan = self.detect_intent(command=command, files=files, raw_text=raw_text)
        return {
            "provider": plan.provider,
            "mode": plan.mode,
            "confidence": plan.confidence,
            "intents": [step.model_dump() for step in plan.intents],
            "intent": plan.primary_intent,
        }

    def _detect_with_hosted_model(self, command: str, files: list[Path], raw_text: str) -> IntentPlan | None:
        if not self.endpoint or not self.model:
            logger.info(
                "PDFPILOT_ROUTER_MODE=%s requested, but PDFPILOT_AI_ROUTER_URL/PDFPILOT_AI_ROUTER_MODEL is not configured. Using local NLP.",
                self.mode,
            )
            return None

        try:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self._build_system_prompt()},
                    {
                        "role": "user",
                        "content": self._build_user_prompt(command=command, files=files, raw_text=raw_text),
                    },
                ],
                "temperature": 0,
            }
            request = urllib.request.Request(
                self.endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers=self._headers(),
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read().decode("utf-8")
        except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            logger.warning("Hosted router request failed. Falling back to local NLP: %s", exc)
            return None

        try:
            parsed_body = json.loads(body)
            content = parsed_body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("Hosted router returned an unexpected payload. Falling back to local NLP: %s", exc)
            return None

        try:
            remote_json = json.loads(content)
        except json.JSONDecodeError as exc:
            logger.warning("Hosted router did not return valid JSON. Falling back to local NLP: %s", exc)
            return None

        try:
            plan = self._coerce_remote_plan(remote_json, command=command)
        except ValueError as exc:
            logger.warning("Hosted router returned an unsupported intent. Falling back to local NLP: %s", exc)
            return None

        plan.provider = "hosted"
        plan.mode = self.mode
        plan.original_command = command
        return plan.require_steps()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @staticmethod
    def _build_semantic_router() -> IntentRouter | None:
        try:
            from backend.intent_router import IntentRouter

            return IntentRouter()
        except Exception as exc:
            logger.warning("Semantic router is unavailable. Falling back to local parser: %s", exc)
            return None

    def _build_system_prompt(self) -> str:
        available_tools = "\n".join(f"- {tool}" for tool in list_tool_names())
        return (
            "You are a routing system for a document automation platform.\n\n"
            "Determine which backend tool or tools should execute the user's request.\n"
            "Use only these tools:\n"
            f"{available_tools}\n\n"
            "Return JSON only in this shape:\n"
            '{"intents":[{"intent":"tool_name","confidence":0.0,"requires_files":true,"inputs":{}}]}\n'
            "If the request is single-step, still return one item in the intents array.\n"
            "Do not include explanations."
        )

    @staticmethod
    def _build_user_prompt(command: str, files: list[Path], raw_text: str) -> str:
        file_summary = ", ".join(path.suffix.lower() or "noext" for path in files) if files else "no files attached"
        text_summary = "raw_text_provided" if raw_text.strip() else "no_raw_text"
        return (
            f"User command: {command}\n"
            f"Attached files: {file_summary}\n"
            f"Raw text: {text_summary}"
        )

    def _coerce_remote_plan(self, payload: dict[str, Any], *, command: str) -> IntentPlan:
        raw_intents = payload.get("intents")
        if raw_intents is None and payload.get("intent"):
            raw_intents = [{"intent": payload["intent"]}]

        if isinstance(raw_intents, list) and raw_intents and isinstance(raw_intents[0], str):
            raw_intents = [{"intent": value} for value in raw_intents]

        if not isinstance(raw_intents, list) or not raw_intents:
            raise ValueError("No intents returned")

        steps: list[IntentStep] = []
        for item in raw_intents:
            if not isinstance(item, dict) or "intent" not in item:
                raise ValueError("Invalid intent step")
            resolved = resolve_tool_name(str(item["intent"]))
            steps.append(
                IntentStep(
                    intent=resolved,
                    confidence=float(item.get("confidence", 0.9)),
                    requires_files=bool(item.get("requires_files", True)),
                    inputs=item.get("inputs") or {},
                    summary=str(item.get("summary") or ""),
                )
            )

        return IntentPlan(
            intents=steps,
            original_command=command,
        )
