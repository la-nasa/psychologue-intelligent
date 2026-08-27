from __future__ import annotations

import json
import re
from uuid import uuid4

from .auth import utc_now

ANONYMIZATION_VERSION = "anonymization-dev-1"
REQUIRED_DISTINCT_APPROVALS = 2

_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d .-]{7,}\d)(?!\w)")


def _audit(conn, request_id: str, action: str, actor_id: str, resource_type: str, resource_id: str | None) -> None:
    conn.execute(
        "INSERT INTO audit_logs(id,occurred_at,request_id,actor_id,action,resource_type,resource_id,outcome,metadata) VALUES (?,?,?,?,?,?,?,'SUCCESS',?)",
        (str(uuid4()), utc_now().isoformat(), request_id, actor_id, action, resource_type, resource_id, json.dumps({})),
    )


def anonymize_text(text: str) -> str:
    """Best-effort pattern redaction only -- NOT a validated PII scrubber. This is
    the 'privacy filter' first pass in the master prompt's Section 15 sequence;
    the human review step that follows is the real safeguard, not this regex."""
    redacted = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    redacted = _PHONE_PATTERN.sub("[REDACTED_PHONE]", redacted)
    return redacted


def sample_and_queue_for_review(conn, actor_id: str, request_id: str, limit: int = 50) -> list[str]:
    """Only messages from patients with a currently-active LEARNING consent are
    eligible -- checked at sampling time, so a later revocation stops a patient's
    future messages from being sampled immediately. It does not retroactively
    remove messages already sampled or already included in a finalized dataset
    snapshot; that limitation is documented in docs/reports (Phase 8b) rather
    than silently assumed away."""
    rows = conn.execute(
        """
        SELECT m.id, m.content FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        JOIN consents co ON co.user_id = c.patient_id AND co.purpose = 'LEARNING' AND co.revoked_at IS NULL
        WHERE m.author_type = 'PATIENT'
          AND NOT EXISTS (SELECT 1 FROM human_feedback hf WHERE hf.message_id = m.id)
        ORDER BY m.created_at ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    now = utc_now().isoformat()
    created_ids = []
    for row in rows:
        feedback_id = str(uuid4())
        conn.execute(
            "INSERT INTO human_feedback(id,message_id,anonymized_content,anonymization_version,review_status,sampled_at) "
            "VALUES (?,?,?,?,'PENDING',?)",
            (feedback_id, row["id"], anonymize_text(row["content"]), ANONYMIZATION_VERSION, now),
        )
        created_ids.append(feedback_id)
    _audit(conn, request_id, "learning.sample", actor_id, "HUMAN_FEEDBACK", None)
    return created_ids


def list_pending_feedback(conn) -> list[dict]:
    """Deliberately not scoped by patient-clinician relationship: any clinician
    may review, and the payload never carries patient identity. A patient's own
    treating clinician recognizing their writing style is itself a
    re-identification risk this cross-assignment avoids."""
    rows = conn.execute(
        "SELECT id,anonymized_content,anonymization_version,sampled_at FROM human_feedback "
        "WHERE review_status='PENDING' ORDER BY sampled_at ASC",
    ).fetchall()
    return [dict(row) for row in rows]


def review_feedback(conn, feedback_id: str, clinician_id: str, decision: str, justification: str, request_id: str) -> dict:
    if decision not in ("APPROVED", "REJECTED"):
        raise ValueError("invalid review decision")
    if not justification.strip():
        raise ValueError("a justification is required")
    row = conn.execute("SELECT review_status FROM human_feedback WHERE id=?", (feedback_id,)).fetchone()
    if not row:
        raise ValueError("feedback item not found")
    if row["review_status"] != "PENDING":
        raise ValueError("feedback item already reviewed")
    now = utc_now().isoformat()
    # SEC-001 class fix: guard against two clinicians reviewing the same item
    # concurrently, where the second reviewer's UPDATE would otherwise silently
    # overwrite the first reviewer's decision (same TOCTOU as decide_model_version).
    cursor = conn.execute(
        "UPDATE human_feedback SET review_status=?, reviewed_by=?, review_justification=?, reviewed_at=? WHERE id=? AND review_status='PENDING'",
        (decision, clinician_id, justification, now, feedback_id),
    )
    if cursor.rowcount == 0:
        raise ValueError("feedback item was already reviewed concurrently by another clinician")
    _audit(conn, request_id, "learning.feedback.review", clinician_id, "HUMAN_FEEDBACK", feedback_id)
    return dict(conn.execute("SELECT * FROM human_feedback WHERE id=?", (feedback_id,)).fetchone())


def create_dataset_version(conn, actor_id: str, request_id: str) -> dict:
    """Snapshots every currently-APPROVED, not-yet-included feedback item into a
    new immutable dataset. Immutability is deliberate (Section 15: reproducible
    dataset lineage), which is exactly why sampling/consent checks happen
    earlier, not here -- this step only ever freezes what already passed them."""
    approved_not_included = conn.execute(
        """
        SELECT id FROM human_feedback
        WHERE review_status='APPROVED'
          AND id NOT IN (SELECT human_feedback_id FROM training_dataset_items)
        """,
    ).fetchall()
    if not approved_not_included:
        raise ValueError("no newly approved feedback available to build a dataset")

    now = utc_now().isoformat()
    dataset_id = str(uuid4())
    version = f"learning-dataset-{now[:10]}-{dataset_id[:8]}"
    conn.execute(
        "INSERT INTO training_datasets(id,version,status,created_by,created_at,item_count) VALUES (?,?,'FINALIZED',?,?,?)",
        (dataset_id, version, actor_id, now, len(approved_not_included)),
    )
    conn.executemany(
        "INSERT INTO training_dataset_items(dataset_id,human_feedback_id) VALUES (?,?)",
        [(dataset_id, row["id"]) for row in approved_not_included],
    )
    _audit(conn, request_id, "learning.dataset.create", actor_id, "TRAINING_DATASET", dataset_id)
    return dict(conn.execute("SELECT * FROM training_datasets WHERE id=?", (dataset_id,)).fetchone())


def list_datasets(conn) -> list[dict]:
    return [dict(row) for row in conn.execute("SELECT * FROM training_datasets ORDER BY created_at DESC").fetchall()]


def register_model_version(conn, actor_id: str, kind: str, version: str, dataset_id: str | None, metrics: dict, request_id: str) -> dict:
    if kind not in ("LLM", "EMOTION", "RISK", "CRISIS"):
        raise ValueError("invalid model kind")
    if not version:
        raise ValueError("version is required")
    if dataset_id is not None and not conn.execute("SELECT 1 FROM training_datasets WHERE id=?", (dataset_id,)).fetchone():
        raise ValueError("dataset not found")
    model_version_id = str(uuid4())
    now = utc_now().isoformat()
    try:
        conn.execute(
            "INSERT INTO model_versions(id,kind,version,dataset_id,status,metrics_json,created_by,created_at) "
            "VALUES (?,?,?,?,'PENDING_REVIEW',?,?,?)",
            (model_version_id, kind, version, dataset_id, json.dumps(metrics), actor_id, now),
        )
    except Exception as error:
        raise ValueError("a model version with this kind and version already exists") from error
    _audit(conn, request_id, "learning.model.register", actor_id, "MODEL_VERSION", model_version_id)
    return dict(conn.execute("SELECT * FROM model_versions WHERE id=?", (model_version_id,)).fetchone())


def list_model_versions(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT mv.*, COUNT(CASE WHEN ma.decision='APPROVED' THEN 1 END) AS approval_count
        FROM model_versions mv LEFT JOIN model_approvals ma ON ma.model_version_id = mv.id
        GROUP BY mv.id ORDER BY mv.created_at DESC
        """,
    ).fetchall()
    return [dict(row) for row in rows]


def decide_model_version(conn, model_version_id: str, approver_id: str, decision: str, justification: str, request_id: str) -> dict:
    """Requires REQUIRED_DISTINCT_APPROVALS separate clinicians to APPROVE before
    a model can be deployed (master prompt Section 15: validation by two
    psychologists). A single REJECTED vote blocks it immediately -- conservative
    by design, matching the crisis engine's own fail-safe posture."""
    if decision not in ("APPROVED", "REJECTED"):
        raise ValueError("invalid decision")
    if not justification.strip():
        raise ValueError("a justification is required")
    row = conn.execute("SELECT status FROM model_versions WHERE id=?", (model_version_id,)).fetchone()
    if not row:
        raise ValueError("model version not found")
    if row["status"] not in ("PENDING_REVIEW",):
        raise ValueError("model version is not awaiting review")

    now = utc_now().isoformat()
    try:
        conn.execute(
            "INSERT INTO model_approvals(id,model_version_id,approver_id,decision,justification,created_at) VALUES (?,?,?,?,?,?)",
            (str(uuid4()), model_version_id, approver_id, decision, justification, now),
        )
    except Exception as error:
        raise ValueError("this approver has already reviewed this model version") from error

    # SEC-001 fix (security audit, Phase 14+): the status-changing UPDATE below is
    # guarded with "AND status='PENDING_REVIEW'" and its rowcount checked. Without
    # this, two concurrent decisions -- e.g. a REJECT and, racing it, an APPROVE
    # that reaches the 2-approval threshold -- could interleave so the APPROVE's
    # UPDATE runs after the REJECT already committed, silently overwriting a
    # rejection back to APPROVED. Reproduced and confirmed exploitable before this
    # fix; see tests/test_security.py::BusinessLogicRaceConditionTests.
    if decision == "REJECTED":
        cursor = conn.execute("UPDATE model_versions SET status='REJECTED' WHERE id=? AND status='PENDING_REVIEW'", (model_version_id,))
    else:
        approvals = conn.execute(
            "SELECT COUNT(*) AS n FROM model_approvals WHERE model_version_id=? AND decision='APPROVED'",
            (model_version_id,),
        ).fetchone()["n"]
        cursor = None
        if approvals >= REQUIRED_DISTINCT_APPROVALS:
            cursor = conn.execute("UPDATE model_versions SET status='APPROVED' WHERE id=? AND status='PENDING_REVIEW'", (model_version_id,))

    if cursor is not None and cursor.rowcount == 0:
        # Someone else's decision already changed the status concurrently (most
        # likely a rejection). This approver's vote is still recorded above for
        # audit purposes, but the outcome it would have caused was already
        # superseded -- report that honestly instead of silently discarding it.
        raise ValueError("model version was already decided concurrently by another reviewer")

    _audit(conn, request_id, "learning.model.decision", approver_id, "MODEL_VERSION", model_version_id)
    return dict(conn.execute("SELECT * FROM model_versions WHERE id=?", (model_version_id,)).fetchone())


def deploy_model_version(conn, model_version_id: str, actor_id: str, request_id: str) -> dict:
    """Marks the registry state only: there is no real traffic-routing/shadow
    deployment infrastructure to actually switch (see Phase 10/13 debt).
    Recording this transition truthfully, rather than pretending a real
    rollout happened, is the point."""
    row = conn.execute("SELECT status FROM model_versions WHERE id=?", (model_version_id,)).fetchone()
    if not row or row["status"] != "APPROVED":
        raise ValueError("model version must be APPROVED before it can be deployed")
    conn.execute("UPDATE model_versions SET status='DEPLOYED' WHERE id=?", (model_version_id,))
    _audit(conn, request_id, "learning.model.deploy", actor_id, "MODEL_VERSION", model_version_id)
    return dict(conn.execute("SELECT * FROM model_versions WHERE id=?", (model_version_id,)).fetchone())


def rollback_model_version(conn, model_version_id: str, actor_id: str, request_id: str) -> dict:
    row = conn.execute("SELECT status FROM model_versions WHERE id=?", (model_version_id,)).fetchone()
    if not row or row["status"] != "DEPLOYED":
        raise ValueError("only a DEPLOYED model version can be rolled back")
    conn.execute("UPDATE model_versions SET status='ROLLED_BACK' WHERE id=?", (model_version_id,))
    _audit(conn, request_id, "learning.model.rollback", actor_id, "MODEL_VERSION", model_version_id)
    return dict(conn.execute("SELECT * FROM model_versions WHERE id=?", (model_version_id,)).fetchone())
