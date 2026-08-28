from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from .config import Settings
from .phq9 import PHQ9_VERSION, calculate
from .security import hash_password, new_token, token_hash, verify_password, verify_totp


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class AuthService:
    def __init__(self, conn: sqlite3.Connection, settings: Settings):
        self.conn, self.settings = conn, settings

    def audit(self, request_id: str, action: str, outcome: str, actor_id: str | None = None, resource_type: str = "AUTH", resource_id: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO audit_logs(id, occurred_at, request_id, actor_id, action, resource_type, resource_id, outcome, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid4()), utc_now().isoformat(), request_id, actor_id, action, resource_type, resource_id, outcome, json.dumps({})),
        )

    def register_patient(self, email: str, password: str, request_id: str) -> str:
        normalized = email.strip().lower()
        if not (3 <= len(normalized) <= 320 and "@" in normalized):
            raise ValueError("invalid email")
        try:
            user_id = str(uuid4())
            self.conn.execute(
                "INSERT INTO users(id, email, password_hash, role, created_at) VALUES (?, ?, ?, 'PATIENT', ?)",
                (user_id, normalized, hash_password(password, self.settings.password_iterations), utc_now().isoformat()),
            )
        except sqlite3.IntegrityError as error:
            self.audit(request_id, "auth.register", "DENIED")
            raise ValueError("account cannot be created") from error
        self.audit(request_id, "auth.register", "SUCCESS", user_id, "USER", user_id)
        return user_id

    def provision_privileged_user(self, email: str, password: str, role: str, totp_secret: str, request_id: str) -> str:
        """Clinician and admin accounts are never self-registered over HTTP: they are
        provisioned out-of-band (see scripts/provision_user.py) by an operator who has
        already verified the person's identity and role locally."""
        if role not in ("CLINICIAN", "ADMIN"):
            raise ValueError("only CLINICIAN or ADMIN accounts require provisioning")
        normalized = email.strip().lower()
        if not (3 <= len(normalized) <= 320 and "@" in normalized):
            raise ValueError("invalid email")
        user_id = str(uuid4())
        try:
            self.conn.execute(
                "INSERT INTO users(id, email, password_hash, role, mfa_secret, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, normalized, hash_password(password, self.settings.password_iterations), role, totp_secret, utc_now().isoformat()),
            )
        except sqlite3.IntegrityError as error:
            self.audit(request_id, "auth.provision", "DENIED", resource_type="USER")
            raise ValueError("account cannot be created") from error
        self.audit(request_id, "auth.provision", "SUCCESS", user_id, "USER", user_id)
        return user_id

    def authenticate(self, email: str, password: str, request_id: str, totp_code: str | None = None) -> str:
        row = self.conn.execute("SELECT * FROM users WHERE email = ? AND is_active = 1", (email.strip().lower(),)).fetchone()
        if row is None or not verify_password(password, row["password_hash"]):
            self.audit(request_id, "auth.login", "DENIED")
            raise PermissionError("invalid credentials")
        if row["role"] in ("CLINICIAN", "ADMIN") and (not row["mfa_secret"] or not verify_totp(row["mfa_secret"], totp_code or "")):
            self.audit(request_id, "auth.mfa", "DENIED", row["id"])
            raise PermissionError("mfa required")
        token = new_token()
        expiry = utc_now() + timedelta(seconds=self.settings.session_ttl_seconds)
        self.conn.execute(
            "INSERT INTO sessions(id, user_id, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid4()), row["id"], token_hash(token), expiry.isoformat(), utc_now().isoformat()),
        )
        self.audit(request_id, "auth.login", "SUCCESS", row["id"], "SESSION")
        return token

    def current_user(self, token: str, request_id: str) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT u.id, u.email, u.role FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ? AND s.revoked_at IS NULL AND s.expires_at > ? AND u.is_active = 1",
            (token_hash(token), utc_now().isoformat()),
        ).fetchone()
        if row is None:
            self.audit(request_id, "auth.session", "DENIED")
            raise PermissionError("invalid session")
        return row

    def revoke(self, token: str, request_id: str) -> None:
        self.conn.execute("UPDATE sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL", (utc_now().isoformat(), token_hash(token)))
        self.audit(request_id, "auth.logout", "SUCCESS")

    def save_profile(self, user_id: str, display_name: str, request_id: str, about_me: str = "") -> None:
        name = display_name.strip()
        if len(name) > 100:
            raise ValueError("display name too long")
        about = about_me.strip()
        if len(about) > 2000:
            raise ValueError("about_me too long")
        now = utc_now().isoformat()
        # onboarding_completed_at is stamped on the *first* save only (COALESCE
        # keeps whatever was already there): this is also how the frontend
        # tells a first-time onboarding apart from a later profile edit --
        # see GET /api/v1/profile.
        self.conn.execute(
            "INSERT INTO profiles(user_id, display_name, about_me, onboarding_completed_at, updated_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET display_name=excluded.display_name, about_me=excluded.about_me, "
            "onboarding_completed_at=COALESCE(profiles.onboarding_completed_at, excluded.onboarding_completed_at), updated_at=excluded.updated_at",
            (user_id, name, about or None, now, now),
        )
        self.audit(request_id, "profile.update", "SUCCESS", user_id, "PROFILE", user_id)

    def get_profile(self, user_id: str) -> dict:
        row = self.conn.execute("SELECT display_name, about_me, onboarding_completed_at FROM profiles WHERE user_id=?", (user_id,)).fetchone()
        consents = sorted({r["purpose"] for r in self.conn.execute("SELECT purpose FROM consents WHERE user_id=? AND revoked_at IS NULL", (user_id,)).fetchall()})
        if row is None:
            return {"display_name": "", "about_me": None, "onboarding_completed_at": None, "consents": consents}
        return {"display_name": row["display_name"], "about_me": row["about_me"], "onboarding_completed_at": row["onboarding_completed_at"], "consents": consents}

    def grant_consent(self, user_id: str, purpose: str, version: str, request_id: str) -> None:
        if purpose not in {"CARE", "LEARNING"} or not version or len(version) > 40:
            raise ValueError("invalid consent")
        self.conn.execute(
            "INSERT INTO consents(id, user_id, purpose, version, granted_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(user_id, purpose, version) DO UPDATE SET granted_at=excluded.granted_at, revoked_at=NULL",
            (str(uuid4()), user_id, purpose, version, utc_now().isoformat()),
        )
        self.audit(request_id, "consent.grant", "SUCCESS", user_id, "CONSENT", purpose)

    def revoke_consent(self, user_id: str, purpose: str, request_id: str) -> None:
        """Required before any sampling can honestly respect an opt-out: without
        this, LEARNING consent could be granted but never withdrawn, which is
        exactly the gap Section 55 warns against."""
        if purpose not in {"CARE", "LEARNING"}:
            raise ValueError("invalid consent purpose")
        self.conn.execute(
            "UPDATE consents SET revoked_at=? WHERE user_id=? AND purpose=? AND revoked_at IS NULL",
            (utc_now().isoformat(), user_id, purpose),
        )
        self.audit(request_id, "consent.revoke", "SUCCESS", user_id, "CONSENT", purpose)

    def request_deletion(self, user_id: str, request_id: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO deletion_requests(id, user_id, status, created_at) VALUES (?, ?, 'OPEN', ?)",
            (str(uuid4()), user_id, utc_now().isoformat()),
        )
        self.audit(request_id, "privacy.deletion_requested", "SUCCESS", user_id, "USER", user_id)

    def submit_phq9(self, user_id: str, answers: list[int], request_id: str) -> dict:
        result = calculate(answers)
        assessment_id = str(uuid4())
        self.conn.execute("INSERT INTO phq9_assessments(id,user_id,instrument_version,answers_json,total_score,item9_score,completed_at) VALUES (?,?,?,?,?,?,?)", (assessment_id, user_id, PHQ9_VERSION, json.dumps(answers), result.total_score, result.item9_score, utc_now().isoformat()))
        self.audit(request_id, "assessment.phq9.submit", "SUCCESS", user_id, "PHQ9", assessment_id)
        return {"id": assessment_id, "version": PHQ9_VERSION, "total_score": result.total_score, "item9_score": result.item9_score}

    def phq9_history(self, user_id: str) -> list[dict]:
        rows = self.conn.execute("SELECT id,instrument_version,total_score,item9_score,completed_at FROM phq9_assessments WHERE user_id=? ORDER BY completed_at DESC", (user_id,)).fetchall()
        return [dict(row) for row in rows]


def require_role(user: sqlite3.Row, *roles: str) -> None:
    if user["role"] not in roles:
        raise PermissionError("forbidden")
