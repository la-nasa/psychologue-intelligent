"""Composition de la réponse — porté de v1 `backend/app/responder.py`.

INVARIANT (ADR-004/007, master prompt §7, overview-v2 §15 invariant 1) :
le LLM ne décide jamais comment une crise est formulée. ORANGE/RED renvoient
uniquement des gabarits fixes, versionnés, soumis à approbation. Le LLM (ou son
substitut de dev) ne s'exécute que pour les messages GREEN, et `context` ne lui
est transmis que dans ce cas.
"""
from __future__ import annotations

from app.ai.providers.base import LLMProvider
from app.domain.safety.crisis import CrisisDecision
from app.domain.safety.policy import ResponseTemplates


def compose_reply(
    decision: CrisisDecision,
    templates: ResponseTemplates,
    llm: LLMProvider,
    patient_text: str,
    context: dict | None = None,
) -> tuple[str, str]:
    if decision.level == "RED":
        return templates.red, f"template:{templates.version}"
    if decision.level == "ORANGE":
        return templates.orange, f"template:{templates.version}"
    return llm.generate(patient_text, context), llm.version
