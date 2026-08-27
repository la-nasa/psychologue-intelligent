from __future__ import annotations

"""Read-only context assembly for personalizing a GREEN-level reply.

This module only ever runs after the crisis engine has already classified a
message as GREEN (see responder.py::compose_reply): it has no influence on
crisis detection or on ORANGE/RED replies, which never reach it. Building
this context must never fail loudly -- a patient's message still deserves a
reply even if their profile row is missing or a query errors -- so every
lookup here is best-effort and degrades to less context, never an exception.
"""

RECENT_MESSAGES_LIMIT = 6

# Standard PHQ-9 severity bands (Kroenke, Spitzer & Williams, 2001), the same
# published thresholds used clinically -- not invented for this project.
# Only the qualitative band is ever exposed to a generative responder, never
# the raw score: a number is something to quote back verbatim by accident,
# a mood word is not.
_PHQ9_BANDS = (
    (4, "minimale"),
    (9, "légère"),
    (14, "modérée"),
    (19, "modérément sévère"),
    (27, "sévère"),
)


def phq9_severity_band(total_score: int) -> str:
    for upper_bound, label in _PHQ9_BANDS:
        if total_score <= upper_bound:
            return label
    return _PHQ9_BANDS[-1][1]


def build_context(conn, patient_id: str, conversation_id: str) -> dict:
    trend = _phq9_trend(conn, patient_id)
    return {
        "display_name": _display_name(conn, patient_id),
        "phq9_trend": trend,
        "phq9_severity_band": phq9_severity_band(trend[0]["total_score"]) if trend else None,
        "recent_messages": _recent_messages(conn, conversation_id),
    }


def _display_name(conn, patient_id: str) -> str | None:
    try:
        row = conn.execute("SELECT display_name FROM profiles WHERE user_id=?", (patient_id,)).fetchone()
    except Exception:
        return None
    name = (row["display_name"] if row else "") or ""
    return name.strip() or None


def _phq9_trend(conn, patient_id: str) -> list[dict]:
    try:
        rows = conn.execute(
            "SELECT total_score, completed_at FROM phq9_assessments WHERE user_id=? ORDER BY completed_at DESC LIMIT 2",
            (patient_id,),
        ).fetchall()
    except Exception:
        return []
    return [{"total_score": row["total_score"], "completed_at": row["completed_at"]} for row in rows]


def _recent_messages(conn, conversation_id: str) -> list[dict]:
    try:
        rows = conn.execute(
            "SELECT author_type, content FROM messages WHERE conversation_id=? ORDER BY sequence_no DESC LIMIT ?",
            (conversation_id, RECENT_MESSAGES_LIMIT),
        ).fetchall()
    except Exception:
        return []
    # Reverse to chronological order (oldest first) -- the order a prompt should read them in.
    return [{"author_type": row["author_type"], "content": row["content"]} for row in reversed(rows)]
