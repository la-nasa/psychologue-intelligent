"""Robustesse de la détection de crise : faux négatifs (crise manquée) et faux
positifs (sur-escalade). Ce fichier est **honnête sur les limites** : le moteur
de règles est un appariement de sous-chaînes après normalisation (accents/casse).
Il attrape les variantes typographiques simples, pas l'obfuscation ni le contexte.
Le modèle de risque entraîné (Phase 8) et une revue clinique des règles réduiront
ces écarts ; ils sont documentés, pas masqués."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.ai.providers.keyword_risk import KeywordRiskModel
from app.domain.safety.crisis import CrisisDetector
from app.domain.safety.policy import load_crisis_policy, load_crisis_rules

_DIR = Path("config/policies")
_DET = CrisisDetector(load_crisis_policy(_DIR / "crisis-policy-v1.json"), load_crisis_rules(_DIR / "crisis-rules-v1.json"))


def _level(text: str) -> str:
    return _DET.evaluate(text, KeywordRiskModel()).level


# --- attrapé : variantes simples (le point fort du pipeline actuel) ---

@pytest.mark.parametrize(
    "text",
    [
        "J'AI UN PLAN SUICIDAIRE",          # casse
        "j'ai un plán suicidaire",          # accents
        "je pense au suicide",              # mot nu
        "je veux en finir ce soir",         # concern -> au moins ORANGE
    ],
)
def test_obvious_crisis_phrasings_are_caught(text) -> None:
    assert _level(text) in ("ORANGE", "RED")


# --- limite assumée : obfuscation NON attrapée par le seul moteur de règles ---

@pytest.mark.parametrize(
    "text",
    [
        "j'ai un pl4n suicid4ire",          # leetspeak
        "j'ai un p l a n s u i c i d a i r e",  # espacement caractère par caractère
        "jé vé me tüé",                     # phonétique
    ],
)
def test_known_gap_obfuscated_crisis_phrasings_are_not_caught_by_rules_alone(text) -> None:
    # documente l'écart : ces formulations passent aujourd'hui en GREEN.
    # NE PAS relâcher ce test en le supprimant — le corriger = améliorer le moteur.
    assert _level(text) == "GREEN"


# --- limite assumée : faux positif sur un contexte non-crise ---

def test_known_gap_crisis_word_in_a_clearly_non_crisis_context_over_escalates() -> None:
    # « j'ai lu un article sur le suicide » -> escalade aujourd'hui (sous-chaîne "suicide").
    assert _level("j'ai lu un article sur le suicide dans le journal ce matin") in ("ORANGE", "RED")


# --- ce qui NE régresse jamais : le fail-safe ---

def test_a_calm_message_stays_green() -> None:
    assert _level("j'ai passe une bonne journee, un peu de sport et de lecture") == "GREEN"
