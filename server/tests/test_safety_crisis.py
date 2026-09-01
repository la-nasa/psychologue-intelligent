"""Invariants du moteur de crise (overview-v2 §15 invariants 1 & 4).
Porté de v1 `tests/test_crisis_pipeline.py::CrisisDetectorFailSafeTests` +
`tests/test_generative_responder.py` (routage ORANGE/RED)."""
from __future__ import annotations

from pathlib import Path

from app.ai.providers.keyword_risk import KeywordRiskModel
from app.ai.providers.templated import TemplatedSupportiveResponder
from app.domain.safety.crisis import CrisisDetector
from app.domain.safety.policy import load_crisis_policy, load_crisis_rules, load_response_templates
from app.domain.safety.responder import compose_reply

_DIR = Path("config/policies")
POLICY = load_crisis_policy(_DIR / "crisis-policy-v1.json")
RULES = load_crisis_rules(_DIR / "crisis-rules-v1.json")
TEMPLATES = load_response_templates(_DIR / "response-templates-v1.json")


class _BrokenModel:
    version = "broken-dev-1"

    def predict(self, text: str) -> tuple[float, float]:
        raise RuntimeError("model backend unavailable")


class _OverconfidentSafeModel:
    version = "overconfident-dev-1"

    def predict(self, text: str) -> tuple[float, float]:
        return 0.0, 1.0


def test_model_failure_falls_back_conservatively_never_crashes() -> None:
    decision = CrisisDetector(POLICY, RULES).evaluate("Une journee plutot calme", _BrokenModel())
    assert decision.model_available is False
    assert "model_unavailable" in decision.reasons
    assert decision.level == "ORANGE"  # confiance dégradée => prudence, jamais GREEN


def test_rule_engine_cannot_be_overridden_by_an_overconfident_model() -> None:
    decision = CrisisDetector(POLICY, RULES).evaluate("J'ai un plan suicidaire", _OverconfidentSafeModel())
    assert decision.level == "RED"
    assert decision.model_available is True


def test_accented_and_case_variants_are_still_detected() -> None:
    decision = CrisisDetector(POLICY, RULES).evaluate("Je suis DESESPERE", KeywordRiskModel())
    assert decision.level in ("ORANGE", "RED")


def test_confident_safe_text_with_available_model_is_green() -> None:
    decision = CrisisDetector(POLICY, RULES).evaluate("Ma seance de sport s'est bien passee", _OverconfidentSafeModel())
    assert decision.level == "GREEN"


def test_decision_always_carries_policy_rules_and_model_versions() -> None:
    decision = CrisisDetector(POLICY, RULES).evaluate("Bonjour", KeywordRiskModel())
    assert decision.policy_version == POLICY.version
    assert decision.rules_version == RULES.version
    assert decision.model_version == KeywordRiskModel.version


class _SpyLLM:
    version = "spy-1"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate(self, text: str, context: dict | None = None) -> str:
        self.calls.append(text)
        return "generated"


def _decision(level: str):
    from app.domain.safety.crisis import CrisisDecision

    return CrisisDecision(level, 0.9, 0.9, "m", True, RULES.version, POLICY.version, ("r",))


def test_red_and_orange_never_reach_the_llm() -> None:
    spy = _SpyLLM()
    for level in ("RED", "ORANGE"):
        reply, version = compose_reply(_decision(level), TEMPLATES, spy, "je veux en finir")
        assert version == f"template:{TEMPLATES.version}"
        assert reply == (TEMPLATES.red if level == "RED" else TEMPLATES.orange)
    assert spy.calls == []  # le moteur espion n'a jamais été appelé


def test_green_is_the_only_level_that_reaches_the_llm() -> None:
    spy = _SpyLLM()
    reply, version = compose_reply(_decision("GREEN"), TEMPLATES, spy, "bonjour")
    assert reply == "generated" and version == "spy-1"
    assert spy.calls == ["bonjour"]


def test_templated_responder_ignores_context_and_is_deterministic() -> None:
    responder = TemplatedSupportiveResponder(TEMPLATES.green_acknowledgments)
    a = responder.generate("meme texte", {"display_name": "Alex"})
    b = responder.generate("meme texte", None)
    assert a == b and a in TEMPLATES.green_acknowledgments
