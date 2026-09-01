"""Vérification de sortie — version minimale Phase 4 (overview-v2 §7).

La Phase 7 remplace ceci par le pipeline complet
(PII -> safety -> clinical policy -> crisis consistency -> hallucination).
Ici : garde-fous strictement nécessaires pour ne pas livrer une réponse
générée dangereuse en attendant. Échec -> SAFE_FALLBACK, jamais la sortie brute.
"""
from __future__ import annotations

import re

from app.domain.safety.crisis import CrisisDecision
from app.domain.safety.policy import ResponseTemplates

# Revendications de diagnostic / de posture clinique interdites.
_FORBIDDEN = re.compile(
    r"\b(vous souffrez d[e']|vous (avez|présentez) un(e)? (trouble|dépression|maladie|pathologie)|"
    r"je (vous )?diagnostique|mon diagnostic|en tant que (psychologue|médecin|thérapeute)|"
    r"je suis (un|une|votre) (psychologue|médecin|thérapeute|humain))\b",
    re.IGNORECASE,
)


class OutputSafetyResult:
    __slots__ = ("reason", "replaced", "text")

    def __init__(self, text: str, replaced: bool, reason: str) -> None:
        self.text = text
        self.replaced = replaced
        self.reason = reason


def check(reply: str, *, decision: CrisisDecision, templates: ResponseTemplates) -> OutputSafetyResult:
    # Cohérence de crise : ce module ne doit être appelé que pour du GREEN. Si ce
    # n'est pas le cas, c'est un bug d'appelant — on refuse la sortie générée.
    if decision.level != "GREEN":
        return OutputSafetyResult(templates.orange, replaced=True, reason="called_on_non_green")

    stripped = (reply or "").strip()
    if not stripped:
        return OutputSafetyResult(templates.green_acknowledgments[0], replaced=True, reason="empty_reply")

    if _FORBIDDEN.search(stripped):
        return OutputSafetyResult(templates.green_acknowledgments[0], replaced=True, reason="diagnostic_claim")

    if len(stripped) > 2000:
        return OutputSafetyResult(stripped[:2000].rsplit(" ", 1)[0] + "…", replaced=True, reason="too_long")

    return OutputSafetyResult(stripped, replaced=False, reason="ok")
