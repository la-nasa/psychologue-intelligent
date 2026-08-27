from __future__ import annotations

VALID_ROLES = {"PATIENT", "CLINICIAN", "ADMIN"}
VALID_RELATIONSHIP_STATUSES = {"ACTIVE", "ENDED"}


def list_users(conn, role: str | None = None) -> list[dict]:
    """Never returns password_hash or the raw TOTP secret: only what an operator
    needs to identify an account, plus whether MFA is configured at all."""
    if role is not None and role not in VALID_ROLES:
        raise ValueError("invalid role filter")
    query = "SELECT id, email, role, is_active, created_at, (mfa_secret IS NOT NULL) AS mfa_enabled FROM users"
    params: list = []
    if role is not None:
        query += " WHERE role = ?"
        params.append(role)
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    return [{**dict(row), "is_active": bool(row["is_active"]), "mfa_enabled": bool(row["mfa_enabled"])} for row in rows]


def list_relationships(conn, status: str | None = None) -> list[dict]:
    if status is not None and status not in VALID_RELATIONSHIP_STATUSES:
        raise ValueError("invalid status filter")
    query = """
        SELECT r.id, r.patient_id, p.email AS patient_email, r.clinician_id, c.email AS clinician_email,
               r.status, r.created_at, r.ends_at
        FROM patient_clinician_relationships r
        JOIN users p ON p.id = r.patient_id
        JOIN users c ON c.id = r.clinician_id
        WHERE 1=1
    """
    params: list = []
    if status is not None:
        query += " AND r.status = ?"
        params.append(status)
    query += " ORDER BY r.created_at DESC"
    return [dict(row) for row in conn.execute(query, params).fetchall()]
