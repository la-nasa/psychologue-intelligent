"""Politiques cliniques versionnées — porté de v1 `backend/app/policy.py` (ADR-002/004).

Ce sont des DONNÉES, pas du code : seuils de crise, textes de réponse encadrant
une crise, canaux de notification. Chargées et validées au démarrage ; refusées
hors `development` sans `approved_by`/`approved_at`. Cible de migration : la
table `crisis_policies` (data-model-v2 §4). Pur, sans I/O réseau ni DB.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CrisisPolicy:
    version: str
    country: str
    environment: str
    red_score: float
    orange_score: float
    orange_confidence_floor: float
    response_sla_minutes: dict[str, int]
    human_review_required: dict[str, bool]
    notification_channels: tuple[str, ...]
    emergency_contacts: tuple[str, ...]
    approved_by: str | None
    approved_at: str | None


@dataclass(frozen=True)
class CrisisRules:
    version: str
    high_risk_terms: tuple[str, ...]
    concern_terms: tuple[str, ...]


@dataclass(frozen=True)
class ResponseTemplates:
    version: str
    red: str
    orange: str
    green_acknowledgments: tuple[str, ...]
    approved_by: str | None
    approved_at: str | None


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"policy file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"policy file is not valid JSON: {path}") from error


def load_crisis_policy(path: Path) -> CrisisPolicy:
    data = _read_json(path)
    try:
        version = str(data["version"])
        environment = str(data["environment"])
        thresholds = data["alert_thresholds"]
        red_score, orange_score = float(thresholds["red_score"]), float(thresholds["orange_score"])
        confidence_floor = float(thresholds["orange_confidence_floor"])
        sla = {str(k): int(v) for k, v in data["response_sla_minutes"].items()}
        review = {str(k): bool(v) for k, v in data["human_review_required"].items()}
        channels = tuple(str(c) for c in data["notification_channels"])
        contacts = tuple(str(c) for c in data["emergency_contacts"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"policy file is missing or misshapen fields: {path}") from error

    if not version:
        raise ValueError("policy version must not be empty")
    if not (0 <= orange_score < red_score <= 1):
        raise ValueError("policy thresholds must satisfy 0 <= orange_score < red_score <= 1")
    if not (0 <= confidence_floor <= 1):
        raise ValueError("orange_confidence_floor must be between 0 and 1")
    if any(minutes <= 0 for minutes in sla.values()):
        raise ValueError("response SLA minutes must be positive")

    approved_by, approved_at = data.get("approved_by"), data.get("approved_at")
    if environment != "development" and (not approved_by or not approved_at):
        raise ValueError(
            "a clinical crisis policy outside the development environment requires "
            "approved_by and approved_at to be set before it can be loaded"
        )

    return CrisisPolicy(
        version=version,
        country=str(data.get("country", "unset")),
        environment=environment,
        red_score=red_score,
        orange_score=orange_score,
        orange_confidence_floor=confidence_floor,
        response_sla_minutes=sla,
        human_review_required=review,
        notification_channels=channels,
        emergency_contacts=contacts,
        approved_by=approved_by,
        approved_at=approved_at,
    )


def load_crisis_rules(path: Path) -> CrisisRules:
    data = _read_json(path)
    try:
        version = str(data["version"])
        high_risk_terms = tuple(str(t) for t in data["high_risk_terms"])
        concern_terms = tuple(str(t) for t in data["concern_terms"])
    except (KeyError, TypeError) as error:
        raise ValueError(f"rules file is missing or misshapen fields: {path}") from error
    if not version:
        raise ValueError("rules version must not be empty")
    return CrisisRules(version=version, high_risk_terms=high_risk_terms, concern_terms=concern_terms)


def load_response_templates(path: Path) -> ResponseTemplates:
    data = _read_json(path)
    try:
        version = str(data["version"])
        environment = str(data["environment"])
        red, orange = str(data["red"]), str(data["orange"])
        green_acknowledgments = tuple(str(t) for t in data["green_acknowledgments"])
    except (KeyError, TypeError) as error:
        raise ValueError(f"response templates file is missing or misshapen fields: {path}") from error

    if not version or not red or not orange or not green_acknowledgments:
        raise ValueError("response templates must all be non-empty")

    approved_by, approved_at = data.get("approved_by"), data.get("approved_at")
    if environment != "development" and (not approved_by or not approved_at):
        raise ValueError(
            "crisis-adjacent response templates outside the development environment "
            "require approved_by and approved_at to be set before they can be loaded"
        )

    return ResponseTemplates(
        version=version, red=red, orange=orange, green_acknowledgments=green_acknowledgments,
        approved_by=approved_by, approved_at=approved_at,
    )
