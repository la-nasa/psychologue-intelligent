from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain.safety.policy import load_crisis_policy, load_crisis_rules, load_response_templates

_DIR = Path("config/policies")
_POLICY = _DIR / "crisis-policy-v1.json"


def _valid_policy() -> dict:
    return json.loads(_POLICY.read_text(encoding="utf-8"))


def test_loads_the_shipped_policy_rules_and_templates() -> None:
    policy = load_crisis_policy(_POLICY)
    rules = load_crisis_rules(_DIR / "crisis-rules-v1.json")
    templates = load_response_templates(_DIR / "response-templates-v1.json")
    assert 0 <= policy.orange_score < policy.red_score <= 1
    assert rules.high_risk_terms and templates.red and templates.orange


def test_rejects_inverted_thresholds(tmp_path: Path) -> None:
    data = _valid_policy()
    data["alert_thresholds"]["orange_score"] = 0.9
    data["alert_thresholds"]["red_score"] = 0.5
    p = tmp_path / "policy.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        load_crisis_policy(p)


def test_rejects_unapproved_policy_outside_development(tmp_path: Path) -> None:
    data = _valid_policy()
    data["environment"] = "production"
    p = tmp_path / "policy.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        load_crisis_policy(p)


def test_accepts_approved_policy_outside_development(tmp_path: Path) -> None:
    data = _valid_policy()
    data["environment"] = "production"
    data["approved_by"] = "clinician-lead"
    data["approved_at"] = "2026-01-01T00:00:00+00:00"
    p = tmp_path / "policy.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    assert load_crisis_policy(p).approved_by == "clinician-lead"


def test_rejects_missing_file() -> None:
    with pytest.raises(ValueError):
        load_crisis_policy(Path("does/not/exist.json"))
