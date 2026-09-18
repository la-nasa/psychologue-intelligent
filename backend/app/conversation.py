from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

from .ai import LLMProvider
from .auth import utc_now
from .crisis import RiskModel
from .emotion import EmotionModel
from .notifications import NotificationProvider
from .personalization import build_context
from .pipeline import handle_incoming_message
from .policy import CrisisPolicy, CrisisRules, ResponseTemplates
from .responder import compose_reply

MAX_MESSAGE_LENGTH = 8_000


def _require_care_consent(conn, patient_id: str) -> None:
    row = conn.execute("SELECT 1 FROM consents WHERE user_id=? AND purpose='CARE' AND revoked_at IS NULL", (patient_id,)).fetchone()
    if not row:
        raise PermissionError("care consent is required before starting a conversation")


def get_or_create_active_conversation(conn, patient_id: str, request_id: str) -> dict:
    _require_care_consent(conn, patient_id)
    existing = conn.execute("SELECT * FROM conversations WHERE patient_id=? AND status='ACTIVE' ORDER BY created_at DESC LIMIT 1", (patient_id,)).fetchone()
    if existing:
        return dict(existing)
    conversation_id = str(uuid4())
    now = utc_now().isoformat()
    conn.execute("INSERT INTO conversations(id,patient_id,status,created_at,updated_at) VALUES (?,?,'ACTIVE',?,?)", (conversation_id, patient_id, now, now))
    return dict(conn.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone())


def _require_owned_active_conversation(conn, patient_id: str, conversation_id: str) -> None:
    row = conn.execute("SELECT 1 FROM conversations WHERE id=? AND patient_id=? AND status='ACTIVE'", (conversation_id, patient_id)).fetchone()
    if not row:
        raise PermissionError("no active conversation with this id for this patient")


def _next_sequence_no(conn, conversation_id: str) -> int:
    row = conn.execute("SELECT COALESCE(MAX(sequence_no), 0) AS max_seq FROM messages WHERE conversation_id=?", (conversation_id,)).fetchone()
    return row["max_seq"] + 1


def _validate_text(text: str) -> None:
    if not isinstance(text, str) or not (0 < len(text) <= MAX_MESSAGE_LENGTH):
        raise ValueError("message text must be a non-empty string within the size limit")


def _persist_patient_message(conn, conversation_id: str, text: str, now: str) -> tuple[str, int]:
    message_id, sequence = str(uuid4()), _next_sequence_no(conn, conversation_id)
    conn.execute("INSERT INTO messages(id,conversation_id,author_type,content,sequence_no,created_at) VALUES (?,?,'PATIENT',?,?,?)", (message_id, conversation_id, text, sequence, now))
    return message_id, sequence


def _finish_assistant_message(conn, conversation_id: str, patient_message_id: str, patient_sequence: int, text: str, version: str, now: str) -> dict:
    assistant_id, assistant_sequence = str(uuid4()), patient_sequence + 1
    conn.execute("INSERT INTO messages(id,conversation_id,author_type,content,sequence_no,responder_version,created_at) VALUES (?,?,'ASSISTANT',?,?,?,?)", (assistant_id, conversation_id, text, assistant_sequence, version, now))
    conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conversation_id))
    return {"patient_message": dict(conn.execute("SELECT id,author_type,content,sequence_no,created_at FROM messages WHERE id=?", (patient_message_id,)).fetchone()), "assistant_message": dict(conn.execute("SELECT id,author_type,content,sequence_no,created_at FROM messages WHERE id=?", (assistant_id,)).fetchone())}


def _safe_reply_stream(outcome, templates: ResponseTemplates, router, text: str, context: dict) -> tuple[Iterator[str], str]:
    if outcome.decision.level == "RED":
        return iter((templates.red,)), f"template:{templates.version}"
    if outcome.decision.level == "ORANGE":
        return iter((templates.orange,)), f"template:{templates.version}"
    complexity = "deep" if len(text) > 280 or len(context.get("recent_messages", [])) > 8 else "fast"
    return router.stream(text, context, complexity), router.provider.version


def stream_message(conn, patient_id: str, conversation_id: str, text: str, risk_model: RiskModel, policy: CrisisPolicy, rules: CrisisRules, templates: ResponseTemplates, router, notification_provider: NotificationProvider, request_id: str, emotion_model: EmotionModel | None = None) -> Iterator[str | dict]:
    """Run the normal safety pipeline, then yield response chunks and persist once complete.

    The risk/crisis decision is completed before the first generated chunk. The
    router is reachable only for GREEN; ORANGE/RED always use policy templates.
    """
    _require_owned_active_conversation(conn, patient_id, conversation_id)
    _validate_text(text)
    now = utc_now().isoformat()
    patient_id_message, patient_sequence = _persist_patient_message(conn, conversation_id, text, now)
    outcome = handle_incoming_message(conn, patient_id, text, patient_id_message, risk_model, policy, rules, notification_provider, request_id, emotion_model=emotion_model)
    conn.execute("UPDATE messages SET crisis_event_id=? WHERE id=?", (outcome.crisis_event_id, patient_id_message))
    context = build_context(conn, patient_id, conversation_id)
    chunks, version = _safe_reply_stream(outcome, templates, router, text, context)
    collected: list[str] = []
    for chunk in chunks:
        if chunk:
            collected.append(chunk)
            yield chunk
    reply = "".join(collected).strip()
    if not reply:
        raise RuntimeError("empty response from all configured providers")
    yield _finish_assistant_message(conn, conversation_id, patient_id_message, patient_sequence, reply, version, now)


def send_message(conn, patient_id: str, conversation_id: str, text: str, risk_model: RiskModel, policy: CrisisPolicy, rules: CrisisRules, templates: ResponseTemplates, llm: LLMProvider, notification_provider: NotificationProvider, request_id: str, emotion_model: EmotionModel | None = None) -> dict:
    _require_owned_active_conversation(conn, patient_id, conversation_id)
    _validate_text(text)
    now = utc_now().isoformat()
    patient_message_id, patient_seq = _persist_patient_message(conn, conversation_id, text, now)
    outcome = handle_incoming_message(conn, patient_id, text, patient_message_id, risk_model, policy, rules, notification_provider, request_id, emotion_model=emotion_model)
    conn.execute("UPDATE messages SET crisis_event_id=? WHERE id=?", (outcome.crisis_event_id, patient_message_id))
    context = build_context(conn, patient_id, conversation_id)
    reply_text, responder_version = compose_reply(outcome.decision, templates, llm, text, context)
    return _finish_assistant_message(conn, conversation_id, patient_message_id, patient_seq, reply_text, responder_version, now)


def get_messages(conn, patient_id: str, conversation_id: str) -> list[dict]:
    row = conn.execute("SELECT 1 FROM conversations WHERE id=? AND patient_id=?", (conversation_id, patient_id)).fetchone()
    if not row:
        raise PermissionError("no conversation with this id for this patient")
    rows = conn.execute("SELECT id,author_type,content,sequence_no,created_at FROM messages WHERE conversation_id=? ORDER BY sequence_no ASC", (conversation_id,)).fetchall()
    return [dict(r) for r in rows]
