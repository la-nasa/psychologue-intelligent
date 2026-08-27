from __future__ import annotations

from uuid import uuid4

from .auth import utc_now
from .crisis import CrisisDecision

TRANSITIONS={"OPEN":{"ACKNOWLEDGED","ESCALATED","CANCELLED"},"ACKNOWLEDGED":{"IN_REVIEW","ESCALATED","RESOLVED"},"IN_REVIEW":{"ESCALATED","RESOLVED"},"ESCALATED":{"RESOLVED"},"RESOLVED":{"CLOSED"}}

def open_alert(conn, patient_id: str, crisis_event_id: str, decision: CrisisDecision, key: str):
    row=conn.execute("SELECT * FROM alerts WHERE idempotency_key=?",(key,)).fetchone()
    if row:return dict(row), False
    alert_id=str(uuid4()); now=utc_now().isoformat()
    conn.execute("INSERT INTO alerts(id,patient_id,crisis_event_id,level,status,idempotency_key,score,policy_version,created_at) VALUES (?,?,?,?,'OPEN',?,?,?,?)",(alert_id,patient_id,crisis_event_id,decision.level,key,decision.score,decision.policy_version,now))
    return dict(conn.execute("SELECT * FROM alerts WHERE id=?",(alert_id,)).fetchone()), True

def transition(conn, alert_id: str, target: str, actor_id: str, justification: str):
    row=conn.execute("SELECT status FROM alerts WHERE id=?",(alert_id,)).fetchone()
    if not row:raise ValueError("alert not found")
    current_status=row["status"]
    if target not in TRANSITIONS.get(current_status,set()):raise ValueError("invalid alert transition")
    now=utc_now().isoformat()
    # SEC-001 class fix: the UPDATE is guarded by the status we actually validated
    # against ("AND status=?"), so two clinicians racing conflicting transitions
    # from the same starting state (e.g. OPEN->CANCELLED and OPEN->ESCALATED) can
    # no longer have the second writer silently clobber the first -- the loser
    # gets an explicit error instead of a lost update on a safety-critical record.
    cursor=conn.execute("UPDATE alerts SET status=?,acknowledged_at=CASE WHEN ?='ACKNOWLEDGED' THEN ? ELSE acknowledged_at END WHERE id=? AND status=?",(target,target,now,alert_id,current_status))
    if cursor.rowcount==0:raise ValueError("alert status changed concurrently; reload and retry")
    conn.execute("INSERT INTO alert_actions(id,alert_id,actor_id,action,justification,created_at) VALUES (?,?,?,?,?,?)",(str(uuid4()),alert_id,actor_id,target,justification,now))
