"""PHQ-9 — scoring pur (porté de v1 `backend/app/phq9.py`).

Instrument versionné. L'item 9 (idées suicidaires ou d'automutilation) est
**isolé** : son score est conservé séparément et sert de signal de sûreté,
indépendamment du score total (master prompt §8, §136).

Bandes de sévérité : seuils cliniques publiés de Kroenke, Spitzer & Williams
(2001), les mêmes qu'en usage clinique — non inventés pour ce projet. Ils
restent des **repères configurables soumis à validation professionnelle**, pas
des décisions médicales.
"""
from __future__ import annotations

from dataclasses import dataclass

PHQ9_VERSION = "PHQ-9-1"
_ITEMS = 9
_MAX_ITEM = 3

# (borne supérieure incluse, libellé)
_BANDS: tuple[tuple[int, str], ...] = (
    (4, "minimale"),
    (9, "légère"),
    (14, "modérée"),
    (19, "modérément sévère"),
    (27, "sévère"),
)


@dataclass(frozen=True)
class Phq9Result:
    instrument_version: str
    total_score: int
    item9_score: int
    severity_band: str


def severity_band(total_score: int) -> str:
    for upper, label in _BANDS:
        if total_score <= upper:
            return label
    return _BANDS[-1][1]


def score(answers: list[int]) -> Phq9Result:
    if (
        not isinstance(answers, list)
        or len(answers) != _ITEMS
        or any(not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= _MAX_ITEM for v in answers)
    ):
        raise ValueError("PHQ-9 requires exactly nine integer answers between 0 and 3")
    total = sum(answers)
    return Phq9Result(
        instrument_version=PHQ9_VERSION,
        total_score=total,
        item9_score=answers[8],
        severity_band=severity_band(total),
    )
