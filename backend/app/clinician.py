from __future__ import annotations

import json
from uuid import uuid4

from .auth import utc_now

ALERT_LIST_STATUSES = {"OPEN", "ACKNOWLEDGED", "IN_REVIEW", "ESCALATED", "RESOLVED", "CLOSED", "CANCELLED"}
ALERT_LIST_LEVELS = {"GREEN", "ORANGE", "RED"}


def _audit(conn, request_id: str, action: str, actor_id: str, resource_type: str, resource_id: str | None, outcome: str = "SUCCESS") -> None:
    conn.execute(
        "INSERT INTO audit_logs(id,occurred_at,request_id,actor_id,action,resource_type,resource_id,outcome,metadata) VALUES (?,?,?,?,?,?,?,?,?)",
        (str(uuid4()), utc_now().isoformat(), request_id, actor_id, action, resource_type, resource_id, outcome, json.dumps({})),
    )


def create_relationship(conn, patient_id: str, clinician_id: str, actor_id: str, request_id: str) -> str:
    patient = conn.execute("SELECT role FROM users WHERE id=? AND is_active=1", (patient_id,)).fetchone()
    clinician = conn.execute("SELECT role FROM users WHERE id=? AND is_active=1", (clinician_id,)).fetchone()
    if not patient or patient["role"] != "PATIENT" or not clinician or clinician["role"] != "CLINICIAN":
        _audit(conn, request_id, "relationship.create", actor_id, "RELATIONSHIP", None, "DENIED")
        raise ValueError("invalid patient or clinician")
    existing = conn.execute(
        "SELECT id FROM patient_clinician_relationships WHERE patient_id=? AND clinician_id=? AND status='ACTIVE'",
        (patient_id, clinician_id),
    ).fetchone()
    if existing:
        return existing["id"]
    relationship_id = str(uuid4())
    conn.execute(
        "INSERT INTO patient_clinician_relationships(id,patient_id,clinician_id,status,created_by,created_at) VALUES (?,?,?,'ACTIVE',?,?)",
        (relationship_id, patient_id, clinician_id, actor_id, utc_now().isoformat()),
    )
    _audit(conn, request_id, "relationship.create", actor_id, "RELATIONSHIP", relationship_id)
    return relationship_id


def end_relationship(conn, relationship_id: str, actor_id: str, request_id: str) -> None:
    row = conn.execute("SELECT status FROM patient_clinician_relationships WHERE id=?", (relationship_id,)).fetchone()
    if not row or row["status"] != "ACTIVE":
        raise ValueError("relationship is not active")
    conn.execute(
        "UPDATE patient_clinician_relationships SET status='ENDED', ends_at=? WHERE id=?",
        (utc_now().isoformat(), relationship_id),
    )
    _audit(conn, request_id, "relationship.end", actor_id, "RELATIONSHIP", relationship_id)


def has_active_relationship(conn, clinician_id: str, patient_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM patient_clinician_relationships WHERE clinician_id=? AND patient_id=? AND status='ACTIVE'",
        (clinician_id, patient_id),
    ).fetchone()
    return row is not None


def require_active_relationship(conn, clinician_id: str, patient_id: str) -> None:
    if not has_active_relationship(conn, clinician_id, patient_id):
        raise PermissionError("no active relationship with this patient")


def list_patients_for_clinician(conn, clinician_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT u.id AS patient_id, COALESCE(p.display_name, '') AS display_name,
               (SELECT total_score FROM phq9_assessments WHERE user_id = u.id ORDER BY completed_at DESC LIMIT 1) AS latest_phq9_score,
               (SELECT completed_at FROM phq9_assessments WHERE user_id = u.id ORDER BY completed_at DESC LIMIT 1) AS latest_phq9_at,
               (SELECT count(*) FROM alerts WHERE patient_id = u.id AND status IN ('OPEN','ACKNOWLEDGED','IN_REVIEW','ESCALATED')) AS open_alert_count
        FROM patient_clinician_relationships r
        JOIN users u ON u.id = r.patient_id
        LEFT JOIN profiles p ON p.user_id = u.id
        WHERE r.clinician_id = ? AND r.status = 'ACTIVE'
        ORDER BY open_alert_count DESC, display_name ASC
        """,
        (clinician_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def patient_timeline(conn, clinician_id: str, patient_id: str) -> dict:
    require_active_relationship(conn, clinician_id, patient_id)
    profile = conn.execute("SELECT display_name FROM profiles WHERE user_id=?", (patient_id,)).fetchone()
    phq9 = conn.execute(
        "SELECT id,instrument_version,total_score,item9_score,completed_at FROM phq9_assessments WHERE user_id=? ORDER BY completed_at DESC",
        (patient_id,),
    ).fetchall()
    alerts = conn.execute(
        "SELECT id,level,status,score,policy_version,created_at,acknowledged_at FROM alerts WHERE patient_id=? ORDER BY created_at DESC",
        (patient_id,),
    ).fetchall()
    alert_ids = [row["id"] for row in alerts]
    actions: list[dict] = []
    if alert_ids:
        placeholders = ",".join("?" * len(alert_ids))  # only "?" characters; alert_ids are bound below, never interpolated
        actions = [dict(row) for row in conn.execute(
            f"SELECT id,alert_id,actor_id,action,justification,created_at FROM alert_actions WHERE alert_id IN ({placeholders}) ORDER BY created_at DESC",  # nosec B608
            alert_ids,
        ).fetchall()]
    return {
        "patient_id": patient_id,
        "display_name": profile["display_name"] if profile else "",
        "phq9_history": [dict(row) for row in phq9],
        "alerts": [dict(row) for row in alerts],
        "alert_actions": actions,
    }


def list_alerts_for_clinician(conn, clinician_id: str, level: str | None = None, status: str | None = None) -> list[dict]:
    if level is not None and level not in ALERT_LIST_LEVELS:
        raise ValueError("invalid level filter")
    if status is not None and status not in ALERT_LIST_STATUSES:
        raise ValueError("invalid status filter")
    query = """
        SELECT a.id,a.patient_id,COALESCE(p.display_name,'') AS patient_display_name,a.level,a.status,a.score,
               a.policy_version,a.created_at,a.acknowledged_at
        FROM alerts a
        JOIN patient_clinician_relationships r ON r.patient_id = a.patient_id AND r.clinician_id = ? AND r.status = 'ACTIVE'
        LEFT JOIN profiles p ON p.user_id = a.patient_id
        WHERE 1=1
    """
    params: list = [clinician_id]
    if level is not None:
        query += " AND a.level = ?"
        params.append(level)
    if status is not None:
        query += " AND a.status = ?"
        params.append(status)
    query += " ORDER BY a.created_at DESC"
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def act_on_alert(conn, clinician_id: str, alert_id: str, target_status: str, justification: str, request_id: str) -> dict:
    from .alerts import transition

    row = conn.execute("SELECT patient_id FROM alerts WHERE id=?", (alert_id,)).fetchone()
    if not row:
        raise ValueError("alert not found")
    require_active_relationship(conn, clinician_id, row["patient_id"])
    transition(conn, alert_id, target_status, clinician_id, justification)
    _audit(conn, request_id, "alert.action", clinician_id, "ALERT", alert_id)
    return dict(conn.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone())
