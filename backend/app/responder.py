from __future__ import annotations

from .ai import LLMProvider
from .crisis import CrisisDecision
from .policy import ResponseTemplates


def compose_reply(
    decision: CrisisDecision, templates: ResponseTemplates, llm: LLMProvider, patient_text: str,
    context: dict | None = None,
) -> tuple[str, str]:
    """The LLM never decides how a crisis is framed (master prompt Section 7):
    ORANGE/RED replies come only from fixed, versioned, approval-gated templates.
    The LLM (or its dev placeholder) only ever runs for GREEN messages -- and
    `context` (display name, PHQ-9 trend, recent messages; see personalization.py)
    is only ever handed to it for that same GREEN case, never used to influence
    the ORANGE/RED path above."""
    if decision.level == "RED":
        return templates.red, f"template:{templates.version}"
    if decision.level == "ORANGE":
        return templates.orange, f"template:{templates.version}"
    return llm.generate(patient_text, context), llm.version
