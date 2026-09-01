"""Dialogue Policy — FAST vs DEEP + One-Question Policy (master prompt §15, §19).

Pur, sans I/O. La classification n'a lieu que pour un message déjà GREEN
(ORANGE/RED ne passent jamais par le moteur de conversation génératif).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.safety.crisis import CrisisDecision

_FAST_MAX_WORDS = 14
_DEEP_HISTORY_TURNS = 6


@dataclass(frozen=True)
class DialoguePlan:
    path: str          # "FAST" | "DEEP"
    one_question_only: bool
    reason: str


def _emotional_load(text: str, decision: CrisisDecision) -> bool:
    lowered = text.casefold()
    markers = ("je n'en peux plus", "épuisé", "epuise", "seul", "peur", "angoisse", "panique", "pleure")
    intensity = text.count("!") + text.count("...")
    return (
        any(m in lowered for m in markers)
        or intensity >= 2
        or "rule_concern_term" in decision.reasons
        or decision.confidence < 0.7
    )


def classify(text: str, *, recent_turns: int, decision: CrisisDecision) -> DialoguePlan:
    load = _emotional_load(text, decision)
    words = len(text.split())

    if words <= _FAST_MAX_WORDS and recent_turns <= _DEEP_HISTORY_TURNS and not load:
        return DialoguePlan(path="FAST", one_question_only=False, reason="short_simple_low_load")

    reason = "long_message" if words > _FAST_MAX_WORDS else ("long_history" if recent_turns > _DEEP_HISTORY_TURNS else "emotional_load")
    return DialoguePlan(path="DEEP", one_question_only=load, reason=reason)
