"""PatientSummaryService + Evidence (master prompt §35, audit roadmap Phase 13).

Assemble une **synthèse corrélationnelle** de la situation d'un patient à partir
de ses enregistrements structurés (PHQ-9, alertes, évaluations de risque,
objectifs, mémoire, consentements). Contraintes :

- **Chaque affirmation porte au moins une pièce justificative** (`evidence`)
  pointant vers une ligne réelle que le clinicien peut ouvrir. Aucune phrase
  n'est produite sans enregistrement source — vérifié par test.
- **Aucun texte libre généré par un LLM** : que des gabarits déterministes sur
  des données chiffrées/numériques. Zéro risque d'hallucination.
- **Jamais un diagnostic** : formulations corrélationnelles (« en hausse »,
  « coté à », « signal à explorer »), jamais « le patient souffre de… ». Un
  avertissement explicite accompagne toujours la synthèse.
- **Aucun contenu déchiffré** : ni message de conversation, ni contenu de
  mémoire, ni réponse brute au questionnaire — seulement des métadonnées et des
  agrégats.
"""
from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import Base
from app.domain.assessment.phq9 import severity_band
from app.infrastructure.models import (
    Alert,
    Consent,
    Conversation,
    Goal,
    GoalProgress,
    Memory,
    Phq9Assessment,
    RiskAssessment,
)

DISCLAIMER = (
    "Cette synthèse est une agrégation corrélationnelle d'enregistrements ; elle "
    "ne constitue pas un diagnostic, ne remplace pas l'évaluation d'un clinicien "
    "et n'a aucune valeur clinique validée. Chaque élément renvoie à sa source."
)

_OPEN_STATUSES = ("OPEN", "NOTIFIED", "ACKNOWLEDGED", "IN_REVIEW", "ESCALATED")

# Types de pièces justificatives — chaque valeur correspond à une table réelle,
# résolue par `resolve_evidence`.
EVIDENCE_TYPES = (
    "phq9_assessment", "alert", "risk_assessment", "goal", "goal_progress", "memory", "consent", "conversation",
)


@dataclass(frozen=True)
class Evidence:
    type: str
    id: str


@dataclass(frozen=True)
class SummaryStatement:
    key: str
    category: str  # assessment | safety | risk | engagement | goals | consent
    text: str
    evidence: tuple[Evidence, ...]
    as_of: str | None


@dataclass(frozen=True)
class PatientSummary:
    patient_id: str
    generated_at: str
    statements: tuple[SummaryStatement, ...]
    disclaimer: str

    def to_dict(self) -> dict:
        return {
            "patient_id": self.patient_id,
            "generated_at": self.generated_at,
            "disclaimer": self.disclaimer,
            "statements": [
                {**asdict(s), "evidence": [asdict(e) for e in s.evidence]} for s in self.statements
            ],
        }


def _ev(type_: str, id_: uuid.UUID) -> Evidence:
    return Evidence(type=type_, id=str(id_))


async def _phq9_statements(session: AsyncSession, patient_id: uuid.UUID) -> list[SummaryStatement]:
    rows = (
        await session.execute(
            select(Phq9Assessment)
            .where(Phq9Assessment.user_id == patient_id)
            .order_by(Phq9Assessment.completed_at.desc())
            .limit(2)
        )
    ).scalars().all()
    if not rows:
        return []
    latest = rows[0]
    out = [
        SummaryStatement(
            key="phq9.latest",
            category="assessment",
            text=(
                f"Dernier PHQ-9 ({latest.completed_at.date().isoformat()}) : "
                f"{latest.total_score}/27, sévérité {severity_band(latest.total_score)}."
            ),
            evidence=(_ev("phq9_assessment", latest.id),),
            as_of=latest.completed_at.isoformat(),
        )
    ]
    if len(rows) == 2:
        previous = rows[1]
        delta = latest.total_score - previous.total_score
        direction = "en hausse" if delta > 0 else ("en baisse" if delta < 0 else "stable")
        out.append(
            SummaryStatement(
                key="phq9.trend",
                category="assessment",
                text=(
                    f"Score total {direction} de {delta:+d} point(s) depuis le PHQ-9 précédent "
                    f"({previous.completed_at.date().isoformat()})."
                ),
                evidence=(_ev("phq9_assessment", latest.id), _ev("phq9_assessment", previous.id)),
                as_of=latest.completed_at.isoformat(),
            )
        )
    if latest.item9_score >= 1:
        out.append(
            SummaryStatement(
                key="phq9.item9",
                category="safety",
                text=(
                    f"Item 9 (pensées de mort ou d'automutilation) coté {latest.item9_score}/3 au dernier "
                    "questionnaire — signal de sûreté à explorer en entretien."
                ),
                evidence=(_ev("phq9_assessment", latest.id),),
                as_of=latest.completed_at.isoformat(),
            )
        )
    return out


async def _alert_statements(session: AsyncSession, patient_id: uuid.UUID) -> list[SummaryStatement]:
    rows = (
        await session.execute(
            select(Alert)
            .where(Alert.patient_id == patient_id, Alert.status.in_(_OPEN_STATUSES))
            .order_by(Alert.created_at.asc())
        )
    ).scalars().all()
    if not rows:
        return []
    red = sum(1 for a in rows if a.level == "RED")
    orange = sum(1 for a in rows if a.level == "ORANGE")
    oldest = rows[0]
    return [
        SummaryStatement(
            key="alerts.open",
            category="safety",
            text=(
                f"{len(rows)} alerte(s) en cours ({red} RED, {orange} ORANGE) ; la plus ancienne ouverte "
                f"depuis le {oldest.created_at.date().isoformat()}."
            ),
            evidence=tuple(_ev("alert", a.id) for a in rows),
            as_of=rows[-1].created_at.isoformat(),
        )
    ]


async def _risk_statements(session: AsyncSession, patient_id: uuid.UUID, *, now: dt.datetime) -> list[SummaryStatement]:
    window_start = now - dt.timedelta(days=7)
    rows = (
        await session.execute(
            select(RiskAssessment)
            .where(RiskAssessment.patient_id == patient_id, RiskAssessment.created_at >= window_start)
            .order_by(RiskAssessment.created_at.desc())
        )
    ).scalars().all()
    if not rows:
        return []
    top = max(rows, key=lambda r: r.score)
    return [
        SummaryStatement(
            key="risk.recent",
            category="risk",
            text=(
                f"{len(rows)} évaluation(s) de risque sur 7 jours ; score maximal {top.score:.2f} "
                f"(modèle {top.model_version}, corrélation — pas un verdict)."
            ),
            evidence=tuple(_ev("risk_assessment", r.id) for r in rows),
            as_of=rows[0].created_at.isoformat(),
        )
    ]


async def _goal_statements(session: AsyncSession, patient_id: uuid.UUID) -> list[SummaryStatement]:
    goals = (
        await session.execute(
            select(Goal).where(Goal.user_id == patient_id, Goal.status == "ACTIVE").order_by(Goal.created_at.desc())
        )
    ).scalars().all()
    if not goals:
        return []
    goal_ids = [g.id for g in goals]
    latest_progress = (
        await session.execute(
            select(GoalProgress)
            .where(GoalProgress.goal_id.in_(goal_ids))
            .order_by(GoalProgress.recorded_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    evidence = [_ev("goal", g.id) for g in goals]
    text = f"{len(goals)} objectif(s) de travail actif(s), choisi(s) par la personne."
    as_of = goals[0].created_at.isoformat()
    if latest_progress is not None:
        evidence.append(_ev("goal_progress", latest_progress.id))
        text += (
            f" Progression la plus récente : {latest_progress.value}/100 le "
            f"{latest_progress.recorded_at.date().isoformat()}."
        )
        as_of = latest_progress.recorded_at.isoformat()
    return [
        SummaryStatement(key="goals.active", category="goals", text=text, evidence=tuple(evidence), as_of=as_of)
    ]


async def _engagement_statements(session: AsyncSession, patient_id: uuid.UUID) -> list[SummaryStatement]:
    convs = (
        await session.execute(
            select(Conversation)
            .where(Conversation.patient_id == patient_id)
            .order_by(Conversation.updated_at.desc())
        )
    ).scalars().all()
    if not convs:
        return []
    return [
        SummaryStatement(
            key="engagement.activity",
            category="engagement",
            text=(
                f"{len(convs)} conversation(s) ; dernière activité le {convs[0].updated_at.date().isoformat()}. "
                "(Volume uniquement — aucun contenu.)"
            ),
            # On borne les pièces aux 5 conversations les plus récentes : suffisant
            # pour tracer, sans lister des dizaines d'identifiants.
            evidence=tuple(_ev("conversation", c.id) for c in convs[:5]),
            as_of=convs[0].updated_at.isoformat(),
        )
    ]


async def _memory_statements(session: AsyncSession, patient_id: uuid.UUID) -> list[SummaryStatement]:
    rows = (
        await session.execute(
            select(Memory).where(Memory.user_id == patient_id, Memory.status == "ACTIVE")
        )
    ).scalars().all()
    if not rows:
        return []
    declared = sum(1 for m in rows if m.provenance == "USER_DECLARED")
    inferred = sum(1 for m in rows if m.provenance == "MODEL_INFERRED")
    return [
        SummaryStatement(
            key="context.memory",
            category="engagement",
            text=(
                f"{len(rows)} élément(s) de mémoire actif(s) ({declared} déclaré(s) par la personne, "
                f"{inferred} inféré(s)). Contenu non exposé ici."
            ),
            evidence=tuple(_ev("memory", m.id) for m in rows),
            as_of=max(m.created_at for m in rows).isoformat(),
        )
    ]


async def _consent_statements(session: AsyncSession, patient_id: uuid.UUID) -> list[SummaryStatement]:
    rows = (
        await session.execute(
            select(Consent).where(Consent.user_id == patient_id, Consent.revoked_at.is_(None))
        )
    ).scalars().all()
    if not rows:
        return []
    purposes = sorted({c.purpose for c in rows})
    return [
        SummaryStatement(
            key="consent.active",
            category="consent",
            text="Consentements actifs : " + ", ".join(purposes) + ".",
            evidence=tuple(_ev("consent", c.id) for c in rows),
            as_of=max(c.granted_at for c in rows).isoformat(),
        )
    ]


async def build_summary(
    session: AsyncSession, *, patient_id: uuid.UUID, now: dt.datetime | None = None
) -> PatientSummary:
    moment = now or dt.datetime.now(dt.UTC)
    groups = [
        *await _phq9_statements(session, patient_id),
        *await _alert_statements(session, patient_id),
        *await _risk_statements(session, patient_id, now=moment),
        *await _goal_statements(session, patient_id),
        *await _engagement_statements(session, patient_id),
        *await _memory_statements(session, patient_id),
        *await _consent_statements(session, patient_id),
    ]
    # Invariant dur : aucune affirmation sans pièce justificative.
    statements = tuple(s for s in groups if s.evidence)
    if len(statements) != len(groups):  # pragma: no cover - garde défensive
        raise RuntimeError("a summary statement was produced without evidence")
    return PatientSummary(
        patient_id=str(patient_id),
        generated_at=moment.isoformat(),
        statements=statements,
        disclaimer=DISCLAIMER,
    )


_RESOLVERS: dict[str, type[Base]] = {
    "phq9_assessment": Phq9Assessment,
    "alert": Alert,
    "risk_assessment": RiskAssessment,
    "goal": Goal,
    "goal_progress": GoalProgress,
    "memory": Memory,
    "consent": Consent,
    "conversation": Conversation,
}


async def resolve_evidence(
    session: AsyncSession, *, patient_id: uuid.UUID, evidence: Evidence
) -> dict | None:
    """Résout une pièce justificative vers un descriptif **non sensible** de la
    ligne source, en vérifiant qu'elle appartient bien au patient. `None` si
    l'identifiant ne correspond à rien de rattaché à ce patient (traçabilité
    cassée)."""
    model = _RESOLVERS.get(evidence.type)
    if model is None:
        return None
    try:
        row_id = uuid.UUID(evidence.id)
    except ValueError:
        return None

    owner_col = "user_id" if hasattr(model, "user_id") else "patient_id"
    if evidence.type == "goal_progress":
        joined = (
            await session.execute(
                select(GoalProgress, Goal.user_id)
                .join(Goal, Goal.id == GoalProgress.goal_id)
                .where(GoalProgress.id == row_id)
            )
        ).first()
        if joined is None or joined[1] != patient_id:
            return None
        return {"type": evidence.type, "id": evidence.id, "recorded_at": joined[0].recorded_at.isoformat()}

    row = (
        await session.execute(select(model).where(model.id == row_id))  # type: ignore[attr-defined]
    ).scalar_one_or_none()
    if row is None or getattr(row, owner_col) != patient_id:
        return None
    created = getattr(row, "created_at", None) or getattr(row, "completed_at", None) or getattr(row, "granted_at", None)
    return {"type": evidence.type, "id": evidence.id, "as_of": created.isoformat() if created else None}
