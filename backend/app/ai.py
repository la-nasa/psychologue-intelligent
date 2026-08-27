from __future__ import annotations

from typing import Protocol


class LLMProvider(Protocol):
    version: str
    def generate(self, text: str, context: dict | None = None) -> str: ...


class RiskModel(Protocol):
    version: str
    def predict(self, text: str) -> tuple[float, float]: ...


class TemplatedSupportiveResponder:
    """Dev-only, non-generative placeholder behind the LLMProvider port. It never
    reads or reasons about the message beyond picking a rotation index: it is not
    a conversational AI and must never be presented to a patient as one. It only
    ever runs for GREEN-level messages -- crisis-adjacent replies come from fixed,
    versioned, approval-gated templates instead (see backend/app/responder.py),
    so this class can never influence how a crisis is framed."""

    version = "templated-responder-dev-1"

    def __init__(self, acknowledgments: tuple[str, ...]):
        if not acknowledgments:
            raise ValueError("at least one acknowledgment template is required")
        self.acknowledgments = acknowledgments

    def generate(self, text: str, context: dict | None = None) -> str:
        # context (display name, PHQ-9 history, recent messages) is deliberately
        # ignored here: this class's entire contract is a fixed rotation, never
        # personalized text, so there is nothing safe to do with it.
        index = sum(text.encode("utf-8")) % len(self.acknowledgments)
        return self.acknowledgments[index]


class KeywordRiskModel:
    """Development-only deterministic adapter; never a clinical model.

    This is one interchangeable RiskModel implementation behind the port above.
    The crisis engine (backend/app/crisis.py) treats its output as one signal
    among several and never trusts it alone."""

    version = "keyword-risk-dev-1"
    high_risk_terms = ("plan suicidaire", "me tuer", "suicide", "acheter des medicaments")
    concern_terms = ("envie de mourir", "plus envie de vivre", "desespere")

    def predict(self, text: str) -> tuple[float, float]:
        normalized = text.casefold()
        if any(term in normalized for term in self.high_risk_terms):
            return 0.95, 0.70
        if any(term in normalized for term in self.concern_terms):
            return 0.60, 0.60
        # Finding no term is itself a fairly confident reading for a keyword
        # matcher (there is nothing ambiguous about it), not a low-confidence
        # guess. 0.50 here previously sat *below* the policy's default
        # orange_confidence_floor (0.65), which meant the "uncertain -> ORANGE"
        # fallback fired on every ordinary message, not just genuinely
        # ambiguous ones -- caught by manually exercising the chat feature,
        # where a plainly calm message came back with the ORANGE safety
        # template instead of a normal acknowledgment.
        return 0.05, 0.85
