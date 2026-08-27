from __future__ import annotations

from uuid import uuid4

from .ai import LLMProvider
from .auth import utc_now
from .crisis import RiskModel
from .emotion import EmotionModel
from .notifications import NotificationProvider
from .pipeline import handle_incoming_message
from .policy import CrisisPolicy, CrisisRules, ResponseTemplates
from .responder import compose_reply

MAX_MESSAGE_LENGTH = 8_000


def _require_care_consent(conn, patient_id: str) -> None:
    row = conn.execute(
        "SELECT 1 FROM consents WHERE user_id=? AND purpose='CARE' AND revoked_at IS NULL",
        (patient_id,),
    ).fetchone()
    if not row:
        raise PermissionError("care consent is required before starting a conversation")


def get_or_create_active_conversation(conn, patient_id: str, request_id: str) -> dict:
    _require_care_consent(conn, patient_id)
    existing = conn.execute(
        "SELECT * FROM conversations WHERE patient_id=? AND status='ACTIVE' ORDER BY created_at DESC LIMIT 1",
        (patient_id,),
    ).fetchone()
    if existing:
        return dict(existing)
    conversation_id = str(uuid4())
    now = utc_now().isoformat()
    conn.execute(
        "INSERT INTO conversations(id,patient_id,status,created_at,updated_at) VALUES (?,?,'ACTIVE',?,?)",
        (conversation_id, patient_id, now, now),
    )
    return dict(conn.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone())


def _require_owned_active_conversation(conn, patient_id: str, conversation_id: str) -> None:
    row = conn.execute(
        "SELECT 1 FROM conversations WHERE id=? AND patient_id=? AND status='ACTIVE'",
        (conversation_id, patient_id),
    ).fetchone()
    if not row:
        raise PermissionError("no active conversation with this id for this patient")


def _next_sequence_no(conn, conversation_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(sequence_no), 0) AS max_seq FROM messages WHERE conversation_id=?",
        (conversation_id,),
    ).fetchone()
    return row["max_seq"] + 1


def send_message(
    conn,
    patient_id: str,
    conversation_id: str,
    text: str,
    risk_model: RiskModel,
    policy: CrisisPolicy,
    rules: CrisisRules,
    templates: ResponseTemplates,
    llm: LLMProvider,
    notification_provider: NotificationProvider,
    request_id: str,
    emotion_model: EmotionModel | None = None,
) -> dict:
    _require_owned_active_conversation(conn, patient_id, conversation_id)
    if not isinstance(text, str) or not (0 < len(text) <= MAX_MESSAGE_LENGTH):
        raise ValueError("message text must be a non-empty string within the size limit")

    now = utc_now().isoformat()
    patient_message_id = str(uuid4())
    patient_seq = _next_sequence_no(conn, conversation_id)
    conn.execute(
        "INSERT INTO messages(id,conversation_id,author_type,content,sequence_no,created_at) VALUES (?,?,'PATIENT',?,?,?)",
        (patient_message_id, conversation_id, text, patient_seq, now),
    )

    outcome = handle_incoming_message(
        conn, patient_id, text, patient_message_id, risk_model, policy, rules, notification_provider, request_id,
        emotion_model=emotion_model,
    )
    conn.execute("UPDATE messages SET crisis_event_id=? WHERE id=?", (outcome.crisis_event_id, patient_message_id))

    reply_text, responder_version = compose_reply(outcome.decision, templates, llm, text)
    assistant_message_id = str(uuid4())
    assistant_seq = patient_seq + 1
    conn.execute(
        "INSERT INTO messages(id,conversation_id,author_type,content,sequence_no,responder_version,created_at) "
        "VALUES (?,?,'ASSISTANT',?,?,?,?)",
        (assistant_message_id, conversation_id, reply_text, assistant_seq, responder_version, now),
    )
    conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conversation_id))

    return {
        "patient_message": dict(conn.execute("SELECT id,author_type,content,sequence_no,created_at FROM messages WHERE id=?", (patient_message_id,)).fetchone()),
        "assistant_message": dict(conn.execute("SELECT id,author_type,content,sequence_no,created_at FROM messages WHERE id=?", (assistant_message_id,)).fetchone()),
    }


def get_messages(conn, patient_id: str, conversation_id: str) -> list[dict]:
    row = conn.execute("SELECT 1 FROM conversations WHERE id=? AND patient_id=?", (conversation_id, patient_id)).fetchone()
    if not row:
        raise PermissionError("no conversation with this id for this patient")
    rows = conn.execute(
        "SELECT id,author_type,content,sequence_no,created_at FROM messages WHERE conversation_id=? ORDER BY sequence_no ASC",
        (conversation_id,),
    ).fetchall()
    return [dict(r) for r in rows]
