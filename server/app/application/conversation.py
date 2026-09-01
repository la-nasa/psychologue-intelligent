"""Conversation Orchestrator (master prompt §16, overview-v2 §5).

Responsable, pour un message patient : validation, persistance, appel du
**pipeline de sûreté (Phase B) avant toute génération**, construction du contexte
minimal, routage FAST/DEEP, streaming de la réponse, `OutputSafety`, mise à jour
de l'état de dialogue, événements d'audit.

INVARIANTS re-testés ici :
- ORANGE/RED -> gabarit fixe, aucun fournisseur LLM n'est appelé (`compose_reply`
  reçoit un espion qui lève s'il est invoqué).
- GREEN + DEEP sans consentement `AI_EXTERNAL` -> dégradation locale, jamais de
  transfert externe.
- `CARE` requis pour converser.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompt import build_messages
from app.ai.providers.base import ProviderUnavailable
from app.ai.routing import model_router
from app.ai.routing.dialogue_policy import classify
from app.application import assessment, audit, consent, memory, personalization, profile
from app.application.output_safety import check as output_safety_check
from app.application.safety import SafetyConfig, evaluate_incoming_message
from app.core.config import get_settings
from app.core.crypto import decrypt, encrypt
from app.core.errors import DomainError, NotFoundError, PermissionDeniedError
from app.domain.safety.crisis import RiskModel
from app.domain.safety.responder import compose_reply
from app.infrastructure.models import Conversation, ConversationState, Message

LOGGER = logging.getLogger("pi.conversation")
_MAX_MESSAGE_CHARS = 8_000
_RECENT_TURNS = 6


class _RaisingLLM:
    """Passé à `compose_reply` sur le chemin non-GREEN : s'il est appelé, c'est
    une violation de l'invariant ADR-004 -> lève au lieu de générer."""

    version = "must-never-be-called"

    def generate(self, text: str, context: dict | None = None) -> str:
        raise AssertionError("compose_reply invoked an LLM for a non-GREEN message")


@dataclass(frozen=True)
class TurnResult:
    patient_message: dict
    assistant_message: dict
    decision_level: str
    generation_path: str | None
    provider: str | None


async def get_or_create_active_conversation(
    session: AsyncSession, *, organization_id: uuid.UUID, patient_id: uuid.UUID, request_id: str
) -> Conversation:
    if not await consent.has_active_consent(session, patient_id, "CARE"):
        raise PermissionDeniedError("care consent is required before starting a conversation")
    existing = (
        await session.execute(
            select(Conversation)
            .where(Conversation.patient_id == patient_id, Conversation.status == "ACTIVE")
            .order_by(Conversation.created_at.desc())
        )
    ).scalars().first()
    if existing is not None:
        return existing

    convo = Conversation(id=uuid.uuid4(), organization_id=organization_id, patient_id=patient_id, status="ACTIVE")
    session.add(convo)
    await session.flush()
    session.add(ConversationState(conversation_id=convo.id, organization_id=organization_id, stage="WELCOME"))
    await session.flush()
    await audit.record(
        session, request_id=request_id, action="conversation.start", resource_type="conversation",
        resource_id=str(convo.id), organization_id=organization_id, actor_id=patient_id, outcome="SUCCESS",
    )
    return convo


async def _require_owned_active(session: AsyncSession, patient_id: uuid.UUID, conversation_id: uuid.UUID) -> Conversation:
    convo = (
        await session.execute(select(Conversation).where(Conversation.id == conversation_id))
    ).scalar_one_or_none()
    if convo is None or convo.patient_id != patient_id:
        raise NotFoundError("no conversation with this id for this patient")
    if convo.status != "ACTIVE":
        raise DomainError("conversation is closed", code="conversation_closed")
    return convo


async def _next_sequence_no(session: AsyncSession, conversation_id: uuid.UUID) -> int:
    row = await session.execute(
        select(func.coalesce(func.max(Message.sequence_no), 0)).where(Message.conversation_id == conversation_id)
    )
    return int(row.scalar_one()) + 1


async def _recent_messages(session: AsyncSession, conversation_id: uuid.UUID) -> list[dict]:
    rows = (
        await session.execute(
            select(Message.author_type, Message.content_enc)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.sequence_no.desc())
            .limit(_RECENT_TURNS)
        )
    ).all()
    return [{"author_type": at, "content": decrypt(enc) or ""} for at, enc in reversed(rows)]


async def _build_context(
    session: AsyncSession, patient_id: uuid.UUID, conversation_id: uuid.UUID, *, query_text: str, one_question_only: bool
) -> dict:
    # Best-effort : jamais bloquant, jamais une exception (overview-v2 §5).
    ctx: dict = {"recent_messages": [], "relevant_memories": [], "one_question_only": one_question_only}
    try:
        prof = await profile.get_profile(session, patient_id)
        ctx["display_name"] = prof.get("display_name") or None
        ctx["about_me"] = prof.get("about_me") or None
        ctx["recent_messages"] = await _recent_messages(session, conversation_id)
    except Exception:
        LOGGER.exception("context build degraded (profile/history)")
    try:
        style = await personalization.resolve_style(session, patient_id)
        ctx["interaction_style"] = style.as_context()
        ctx["language"] = style.language
    except Exception:
        LOGGER.exception("context build degraded (personalization)")
    try:
        # Mémoire épisodique pertinente (retrieval pgvector) — jamais une mémoire
        # révoquée / expirée / incertaine (filtré dans memory.retrieve).
        ctx["relevant_memories"] = await memory.retrieve(
            session, user_id=patient_id, query_text=query_text, limit=3, types=("EPISODIC", "SEMANTIC")
        )
    except Exception:
        LOGGER.exception("context build degraded (memory retrieval)")
    try:
        # Bande de sévérité PHQ-9 qualitative — jamais le score brut (TV-02) ;
        # ne fait qu'influencer subtilement le ton (voir ai/prompt.build_messages).
        ctx["phq9_severity_band"] = await assessment.latest_severity_band(session, patient_id)
    except Exception:
        LOGGER.exception("context build degraded (phq9 band)")
    return ctx


def _stage_for(level: str) -> str:
    return "CRISIS" if level in ("ORANGE", "RED") else "EXPLORATION"


async def stream_turn(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    patient_id: uuid.UUID,
    conversation_id: uuid.UUID,
    text: str,
    safety_config: SafetyConfig,
    risk_model: RiskModel,
    notification_provider,
    providers: model_router.Providers,
    request_id: str,
    cancel: asyncio.Event | None = None,
) -> AsyncIterator[dict]:
    await _require_owned_active(session, patient_id, conversation_id)
    if not isinstance(text, str) or not (0 < len(text) <= _MAX_MESSAGE_CHARS):
        raise DomainError("message text must be a non-empty string within the size limit", code="invalid_message")

    seq = await _next_sequence_no(session, conversation_id)
    patient_msg_id = uuid.uuid4()
    session.add(
        Message(
            id=patient_msg_id, organization_id=organization_id, conversation_id=conversation_id,
            author_type="PATIENT", content_enc=encrypt(text) or "", sequence_no=seq,
        )
    )
    await session.flush()
    yield {"type": "user_message", "id": str(patient_msg_id), "sequence_no": seq, "content": text}

    outcome = await evaluate_incoming_message(
        session, organization_id=organization_id, patient_id=patient_id, text=text,
        message_reference=str(patient_msg_id), config=safety_config, risk_model=risk_model,
        notification_provider=notification_provider, request_id=request_id,
    )
    await session.execute(
        update(Message).where(Message.id == patient_msg_id).values(crisis_event_id=outcome.crisis_event_id)
    )
    decision = outcome.decision

    assistant_seq = seq + 1
    style_snapshot: dict = {}
    if decision.level != "GREEN":
        reply_text, responder_version = compose_reply(decision, safety_config.templates, _RaisingLLM(), text)
        gen_path, provider_name = "TEMPLATE", None
        yield {"type": "assistant_chunk", "text": reply_text}
    else:
        plan = classify(text, recent_turns=seq - 1, decision=decision)
        ctx = await _build_context(
            session, patient_id, conversation_id, query_text=text, one_question_only=plan.one_question_only
        )
        style_snapshot = ctx.get("interaction_style") or {}
        has_external = await consent.has_active_consent(session, patient_id, "AI_EXTERNAL")
        route = await model_router.route(
            requested_path=plan.path, has_ai_external_consent=has_external, providers=providers
        )
        messages = build_messages(text, ctx)
        max_tokens = get_settings().llm_max_reply_tokens

        fragments: list[str] = []
        cancelled = False
        infra_failure = False
        chosen = route.provider
        try:
            async for fragment in chosen.stream(messages, max_tokens=max_tokens):
                if cancel is not None and cancel.is_set():
                    cancelled = True
                    break
                fragments.append(fragment)
                yield {"type": "assistant_chunk", "text": fragment}
        except ProviderUnavailable:
            LOGGER.info("provider %s unavailable mid-stream; falling back to local", chosen.name)
            chosen = providers.local
            fragments = []
            try:
                async for fragment in chosen.stream(messages, max_tokens=max_tokens):
                    fragments.append(fragment)
                    yield {"type": "assistant_chunk", "text": fragment}
                route = model_router.Route(provider=chosen, effective_path="FAST", reason="mid_stream_fallback")
            except Exception:
                LOGGER.exception("local fallback also failed")
                infra_failure = True
        except Exception:
            # SAFE_FALLBACK (master prompt §30) : toute défaillance d'infrastructure
            # de génération => message de repli neutre, jamais un 500 sans réponse,
            # jamais une réponse partielle non vérifiée livrée telle quelle.
            LOGGER.exception("generation failed; using safe fallback")
            infra_failure = True

        if infra_failure:
            reply_text = safety_config.templates.safe_fallback
            responder_version = "safe_fallback:generation_error"
            gen_path, provider_name = route.effective_path, chosen.name
            yield {"type": "assistant_correction", "text": reply_text}
        else:
            raw = "".join(fragments).strip()
            safe = output_safety_check(raw, decision=decision, templates=safety_config.templates)
            reply_text = safe.text
            gen_path, provider_name = route.effective_path, chosen.name
            marks = [route.provider.version]
            if cancelled:
                marks.append("interrupted")
            if safe.replaced:
                marks.append(f"safe_fallback:{safe.reason}")
            responder_version = "+".join(marks)
            if cancelled or safe.replaced:
                yield {"type": "assistant_correction", "text": reply_text}

    assistant_msg_id = uuid.uuid4()
    session.add(
        Message(
            id=assistant_msg_id, organization_id=organization_id, conversation_id=conversation_id,
            author_type="ASSISTANT", content_enc=encrypt(reply_text) or "", sequence_no=assistant_seq,
            responder_version=responder_version, generation_path=gen_path, llm_provider=provider_name,
            crisis_event_id=outcome.crisis_event_id,
        )
    )
    now = dt.datetime.now(dt.UTC)
    await session.execute(update(Conversation).where(Conversation.id == conversation_id).values(updated_at=now))
    state_values: dict = {"risk_state": decision.level, "stage": _stage_for(decision.level), "updated_at": now}
    if style_snapshot:
        state_values["interaction_style_json"] = style_snapshot
        state_values["language"] = style_snapshot.get("language", "fr")
    await session.execute(
        update(ConversationState).where(ConversationState.conversation_id == conversation_id).values(**state_values)
    )
    await session.flush()
    await audit.record(
        session, request_id=request_id, action="message.replied", resource_type="conversation",
        resource_id=str(conversation_id), organization_id=organization_id, actor_id=patient_id, outcome="SUCCESS",
        metadata={"level": decision.level, "path": gen_path, "provider": provider_name or "template"},
    )

    # Mémoire épisodique : les mots du patient, provenance USER_DECLARED (il l'a dit),
    # jamais une inférence. GREEN uniquement — on n'archive pas un message de crise
    # pour le réinjecter plus tard (décision de périmètre, revue clinique = Phase 14).
    # Best-effort : un échec de mémoire ne casse jamais la conversation.
    if decision.level == "GREEN":
        try:
            await memory.remember(
                session, organization_id=organization_id, user_id=patient_id, content=text,
                type="EPISODIC", provenance="USER_DECLARED", consent_scope="CARE",
                source_conversation_id=conversation_id, source_message_id=patient_msg_id, request_id=request_id,
            )
        except Exception:
            LOGGER.exception("episodic memory write failed")

    yield {
        "type": "assistant_message",
        "id": str(assistant_msg_id),
        "sequence_no": assistant_seq,
        "content": reply_text,
        "generation_path": gen_path,
        "provider": provider_name,
        "decision_level": decision.level,
    }
    yield {"type": "done"}


async def send_message(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    patient_id: uuid.UUID,
    conversation_id: uuid.UUID,
    text: str,
    safety_config: SafetyConfig,
    risk_model: RiskModel,
    notification_provider,
    providers: model_router.Providers,
    request_id: str,
) -> TurnResult:
    patient_msg: dict = {}
    assistant_msg: dict = {}
    async for event in stream_turn(
        session, organization_id=organization_id, patient_id=patient_id, conversation_id=conversation_id,
        text=text, safety_config=safety_config, risk_model=risk_model, notification_provider=notification_provider,
        providers=providers, request_id=request_id, cancel=None,
    ):
        if event["type"] == "user_message":
            patient_msg = event
        elif event["type"] == "assistant_message":
            assistant_msg = event
    return TurnResult(
        patient_message=patient_msg,
        assistant_message=assistant_msg,
        decision_level=assistant_msg.get("decision_level", "UNKNOWN"),
        generation_path=assistant_msg.get("generation_path"),
        provider=assistant_msg.get("provider"),
    )


async def get_messages(
    session: AsyncSession, *, patient_id: uuid.UUID, conversation_id: uuid.UUID
) -> list[dict]:
    convo = (
        await session.execute(select(Conversation).where(Conversation.id == conversation_id))
    ).scalar_one_or_none()
    if convo is None or convo.patient_id != patient_id:
        raise NotFoundError("no conversation with this id for this patient")
    rows = (
        await session.execute(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.sequence_no)
        )
    ).scalars().all()
    return [
        {
            "id": str(m.id),
            "author_type": m.author_type,
            "content": decrypt(m.content_enc) or "",
            "sequence_no": m.sequence_no,
            "generation_path": m.generation_path,
            "created_at": m.created_at.isoformat(),
        }
        for m in rows
    ]
