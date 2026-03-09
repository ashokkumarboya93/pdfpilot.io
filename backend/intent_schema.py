"""
Structured intent schema used by the routing layer.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class IntentStep(BaseModel):
    """A single routed tool invocation."""

    intent: str
    confidence: float = 0.0
    requires_files: bool = True
    inputs: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))


class IntentPlan(BaseModel):
    """A command plan that may contain one or more tool steps."""

    intents: list[IntentStep] = Field(default_factory=list)
    provider: str = "local"
    mode: str = "local"
    original_command: str = ""

    @property
    def primary_intent(self) -> str | None:
        return self.intents[0].intent if self.intents else None

    @property
    def confidence(self) -> float:
        if not self.intents:
            return 0.0
        return round(sum(step.confidence for step in self.intents) / len(self.intents), 3)

    def require_steps(self) -> "IntentPlan":
        if not self.intents:
            raise ValueError("Could not determine intent")
        return self
