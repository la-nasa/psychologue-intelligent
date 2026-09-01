"""Robustesse de la détection de crise : faux négatifs (crise manquée) et faux
positifs (sur-escalade).

Phase 9 : la normalisation durcie (`domain/safety/normalize.harden`) + le modèle
lexical (`ai/providers/lexicon_risk.LexiconRiskModel`, le défaut en production)
ferment les écarts leetspeak / espacement / variante phonétique documentés en
Phase 7. Ce qui reste ouvert est **toujours documenté ici**, pas masqué — le
corriger = améliorer le moteur, jamais supprimer le test.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.ai.providers.keyword_risk import KeywordRiskModel
from app.ai.providers.lexicon_risk import LexiconRiskModel
from app.domain.safety.crisis import CrisisDetector
from app.domain.safety.policy import load_crisis_policy, load_crisis_rules

_DIR = Path("config/policies")
_DET = CrisisDetector(load_crisis_policy(_DIR / "crisis-policy-v1.json"), load_crisis_rules(_DIR / "crisis-rules-v1.json"))


def _level(text: str, model=None) -> str:
    return _DET.evaluate(text, model or LexiconRiskModel()).level


# --- variantes simples (règles seules) ---

@pytest.mark.parametrize(
    "text",
    [
        "J'AI UN PLAN SUICIDAIRE",
        "j'ai un plán suicidaire",
        "je pense au suicide",
        "je veux en finir ce soir",
    ],
)
def test_obvious_crisis_phrasings_are_caught_by_rules_alone(text) -> None:
    assert _DET.evaluate(text, KeywordRiskModel()).level in ("ORANGE", "RED")


# --- Phase 9 : obfuscation désormais attrapée ---

@pytest.mark.parametrize(
    "text",
    [
        "j'ai un pl4n suicid4ire",              # leetspeak -> normalisation durcie
        "j'ai un p l a n s u i c i d a i r e",  # espacement -> appariement despacé
        "j ai un plaaan suicidaaaire",          # allongement -> collapse
        "jé vé me tüé",                         # phonétique -> "me tue" dans le lexique
        "je vais me su1c1der",                  # leet + lexique
    ],
)
def test_obfuscated_crisis_phrasings_are_now_caught(text) -> None:
    assert _level(text) in ("ORANGE", "RED")


def test_reassurance_phrasing_stays_green() -> None:
    assert _level("je ne veux pas mourir, je voulais juste en parler") == "GREEN"


# --- écart résiduel documenté : faux positif sur un contexte non-crise ---

def test_known_gap_crisis_word_in_a_non_crisis_context_over_escalates() -> None:
    # « j'ai lu un article sur le suicide » -> escalade (sous-chaîne "suicide",
    # fail-safe assumé). Fermer cet écart demande une compréhension du contexte
    # (modèle entraîné, revue clinique des règles). NE PAS supprimer ce test.
    assert _level("j'ai lu un article sur le suicide dans le journal ce matin") in ("ORANGE", "RED")


# --- ce qui NE régresse jamais ---

def test_a_calm_message_stays_green() -> None:
    assert _level("j'ai passe une bonne journee, un peu de sport et de lecture") == "GREEN"


def test_model_failure_never_lowers_caution() -> None:
    class _Broken:
        version = "broken"

        def predict(self, text: str) -> tuple[float, float]:
            raise RuntimeError("down")

    # message concernant : reste au moins ORANGE même sans modèle
    assert _DET.evaluate("j'ai un plan suicidaire", _Broken()).level == "RED"
