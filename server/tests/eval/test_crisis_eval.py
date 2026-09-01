"""Métriques recall / precision de la détection de crise sur le corpus synthétique
(master prompt §46 : crisis recall, crisis precision, faux négatifs/positifs).

Seuils volontairement stricts sur le **recall** (une crise manquée est le pire
échec) et plus tolérants sur la **precision** (la sur-escalade est fail-safe).
Ces chiffres mesurent une tendance et bloquent les régressions ; ils ne
revendiquent aucune performance clinique.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.ai.providers.keyword_risk import KeywordRiskModel
from app.ai.providers.lexicon_risk import LexiconRiskModel
from app.domain.safety.crisis import CrisisDetector
from app.domain.safety.policy import load_crisis_policy, load_crisis_rules
from tests.eval.corpus import CRISIS_CORPUS

_DIR = Path("config/policies")
_DET = CrisisDetector(load_crisis_policy(_DIR / "crisis-policy-v1.json"), load_crisis_rules(_DIR / "crisis-rules-v1.json"))


def _metrics(model) -> dict[str, float]:
    tp = fp = tn = fn = 0
    for text, should_escalate in CRISIS_CORPUS:
        escalated = _DET.evaluate(text, model).level in ("ORANGE", "RED")
        if should_escalate and escalated:
            tp += 1
        elif should_escalate and not escalated:
            fn += 1
        elif not should_escalate and escalated:
            fp += 1
        else:
            tn += 1
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    return {"recall": recall, "precision": precision, "fn": fn, "fp": fp, "tp": tp, "tn": tn}


def test_lexicon_model_meets_recall_and_precision_floor() -> None:
    m = _metrics(LexiconRiskModel())
    assert m["recall"] >= 0.94, m       # au plus 1 crise manquée sur ~18
    assert m["precision"] >= 0.85, m


def test_rule_engine_alone_recall_is_a_documented_baseline() -> None:
    # Le moteur de règles seul (appariement de sous-chaînes sur une liste courte)
    # ne suffit PAS : ~0.67 de recall sur ce corpus. C'est précisément pourquoi
    # un modèle de risque existe. Ce seuil documente la ligne de base et bloque
    # une régression du moteur de règles, il ne prétend pas qu'elle soit bonne.
    m = _metrics(KeywordRiskModel())
    assert m["recall"] >= 0.60, m
    assert m["precision"] >= 0.9, m  # les règles sur-escaladent peu sur ce corpus


def test_lexicon_beats_keyword_on_recall() -> None:
    assert _metrics(LexiconRiskModel())["recall"] >= _metrics(KeywordRiskModel())["recall"]


@pytest.mark.parametrize("text,should_escalate", CRISIS_CORPUS)
def test_every_corpus_item_is_classified_without_error(text, should_escalate) -> None:
    # aucune entrée ne doit lever : le pipeline gère toute chaîne non vide.
    assert _DET.evaluate(text, LexiconRiskModel()).level in ("GREEN", "ORANGE", "RED")
