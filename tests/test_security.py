"""Adversarial security test suite (master prompt Section 17, Niveau 5).

This does not replace the negative-authorization tests already embedded in
each domain's test file (test_clinician_dashboard.py, test_admin_console.py,
test_conversation.py, test_learning_pipeline.py, etc.) -- those already cover
IDOR/BOLA for every resource type as it was built. This file adds the attack
classes that don't naturally belong to any one domain: injection payloads,
auth bypass attempts, path traversal, rate limiting, payload/content-type
abuse, and secret leakage checks.
"""
from __future__ import annotations

import json
import sys
import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.ai import KeywordRiskModel
from backend.app.alerts import transition
from backend.app.auth import AuthService
from backend.app.config import Settings
from backend.app.db import connect, migrate
from backend.app.http import MAX_BODY_BYTES, application
from backend.app.learning import decide_model_version, register_model_version, review_feedback
from backend.app.notifications import LogNotificationProvider
from backend.app.pipeline import handle_incoming_message
from backend.app.policy import load_crisis_policy, load_crisis_rules
from scripts.dev_server import FRONTEND_ROOT, _safe_static_path


def invoke(app, method: str, path: str, body: bytes = b"", headers: dict[str, str] | None = None):
    result = {}
    headers = headers or {}
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "wsgi.input": BytesIO(body),
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": headers.get("Content-Type", ""),
        "REMOTE_ADDR": headers.get("Remote-Addr", "127.0.0.1"),
    }
    if "Authorization" in headers:
        environ["HTTP_AUTHORIZATION"] = headers["Authorization"]

    def start_response(status, response_headers):
        result["status"], result["headers"] = status, dict(response_headers)

    payload = b"".join(app(environ, start_response))
    return result["status"], result["headers"], payload


class PathTraversalTests(unittest.TestCase):
    """scripts/dev_server.py serves the three frontends from one process; a
    traversal bug there would expose the whole filesystem, not just the app."""

    def test_dotdot_traversal_is_rejected(self):
        for payload in ("../../../../etc/passwd", "..\\..\\..\\windows\\win.ini", "clinician/../../pyproject.toml"):
            self.assertIsNone(_safe_static_path(payload), f"traversal not blocked: {payload}")

    def test_absolute_path_escape_is_rejected(self):
        self.assertIsNone(_safe_static_path("/etc/passwd"))

    def test_ordinary_file_within_root_is_allowed(self):
        path = _safe_static_path("index.html")
        self.assertIsNotNone(path)
        self.assertTrue(str(path).startswith(str(FRONTEND_ROOT)))


class InjectionResilienceTests(unittest.TestCase):
    """Every query in this codebase is parameterized (sqlite3 '?' placeholders);
    these tests exercise that claim with real payloads instead of trusting it."""

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.settings = Settings(database_path=Path(self.temp.name) / "test.db", password_iterations=1_000)
        self.app = application(self.settings)

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def test_sql_injection_in_login_does_not_bypass_authentication(self):
        payloads = [
            {"email": "' OR '1'='1", "password": "' OR '1'='1' --"},
            {"email": "admin@example.test'; DROP TABLE users; --", "password": "whatever12345"},
        ]
        for body in payloads:
            status, _, _ = invoke(self.app, "POST", "/api/v1/auth/sessions", json.dumps(body).encode(), {"Content-Type": "application/json"})
            self.assertEqual(status, "401 Unauthorized")
        # the table must still exist and be usable after the DROP TABLE attempt
        registration = b'{"email":"still.works@example.test","password":"correct horse battery"}'
        status, _, _ = invoke(self.app, "POST", "/api/v1/auth/register", registration, {"Content-Type": "application/json"})
        self.assertEqual(status, "201 Created")

    def test_script_payload_in_message_is_stored_literally_not_executed_or_mangled(self):
        registration = b'{"email":"xss@example.test","password":"correct horse battery"}'
        invoke(self.app, "POST", "/api/v1/auth/register", registration, {"Content-Type": "application/json"})
        _, _, payload = invoke(self.app, "POST", "/api/v1/auth/sessions", registration, {"Content-Type": "application/json"})
        auth = {"Content-Type": "application/json", "Authorization": "Bearer " + json.loads(payload)["access_token"]}
        invoke(self.app, "POST", "/api/v1/consents", b'{"purpose":"CARE","version":"1"}', auth)
        _, _, payload = invoke(self.app, "POST", "/api/v1/conversations", b"{}", auth)
        conversation_id = json.loads(payload)["id"]

        malicious = "<script>alert(document.cookie)</script>"
        status, _, payload = invoke(self.app, "POST", f"/api/v1/conversations/{conversation_id}/messages", json.dumps({"text": malicious}).encode(), auth)
        self.assertEqual(status, "201 Created")
        # stored and returned byte-for-byte as data, never interpreted server-side
        self.assertEqual(json.loads(payload)["patient_message"]["content"], malicious)

    def test_path_like_payload_in_display_name_is_just_a_string(self):
        registration = b'{"email":"pathlike@example.test","password":"correct horse battery"}'
        invoke(self.app, "POST", "/api/v1/auth/register", registration, {"Content-Type": "application/json"})
        _, _, payload = invoke(self.app, "POST", "/api/v1/auth/sessions", registration, {"Content-Type": "application/json"})
        auth = {"Content-Type": "application/json", "Authorization": "Bearer " + json.loads(payload)["access_token"]}
        status, _, _ = invoke(self.app, "POST", "/api/v1/profile", json.dumps({"display_name": "../../../etc/passwd"}).encode(), auth)
        self.assertEqual(status, "204 No Content")


class AuthBypassTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.settings = Settings(database_path=Path(self.temp.name) / "test.db", password_iterations=1_000)
        self.app = application(self.settings)
        registration = b'{"email":"bypass@example.test","password":"correct horse battery"}'
        invoke(self.app, "POST", "/api/v1/auth/register", registration, {"Content-Type": "application/json"})
        _, _, payload = invoke(self.app, "POST", "/api/v1/auth/sessions", registration, {"Content-Type": "application/json"})
        self.valid_token = json.loads(payload)["access_token"]

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def test_missing_authorization_header_is_rejected(self):
        status, _, _ = invoke(self.app, "GET", "/api/v1/me")
        self.assertEqual(status, "401 Unauthorized")

    def test_malformed_scheme_is_rejected(self):
        for header in (f"Token {self.valid_token}", self.valid_token, "Bearer", "Bearer "):
            status, _, _ = invoke(self.app, "GET", "/api/v1/me", headers={"Authorization": header})
            self.assertEqual(status, "401 Unauthorized", f"should reject: {header!r}")

    def test_tampered_token_is_rejected(self):
        tampered = self.valid_token[:-1] + ("a" if self.valid_token[-1] != "a" else "b")
        status, _, _ = invoke(self.app, "GET", "/api/v1/me", headers={"Authorization": f"Bearer {tampered}"})
        self.assertEqual(status, "401 Unauthorized")

    def test_revoked_token_is_rejected_immediately(self):
        auth = {"Content-Type": "application/json", "Authorization": f"Bearer {self.valid_token}"}
        invoke(self.app, "POST", "/api/v1/auth/logout", b"{}", auth)
        status, _, _ = invoke(self.app, "GET", "/api/v1/me", headers=auth)
        self.assertEqual(status, "401 Unauthorized")

    def test_session_endpoint_never_sets_a_cookie(self):
        """Bearer-token auth with no ambient credential means classic CSRF does
        not apply here by construction -- verify that construction holds."""
        registration = b'{"email":"nocookie@example.test","password":"correct horse battery"}'
        invoke(self.app, "POST", "/api/v1/auth/register", registration, {"Content-Type": "application/json"})
        _, headers, _ = invoke(self.app, "POST", "/api/v1/auth/sessions", registration, {"Content-Type": "application/json"})
        self.assertNotIn("Set-Cookie", headers)


class PrivilegeEscalationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.settings = Settings(database_path=Path(self.temp.name) / "test.db", password_iterations=1_000)
        self.app = application(self.settings)
        registration = b'{"email":"escalate@example.test","password":"correct horse battery"}'
        invoke(self.app, "POST", "/api/v1/auth/register", registration, {"Content-Type": "application/json"})
        _, _, payload = invoke(self.app, "POST", "/api/v1/auth/sessions", registration, {"Content-Type": "application/json"})
        self.auth = {"Content-Type": "application/json", "Authorization": "Bearer " + json.loads(payload)["access_token"]}

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def test_extra_role_field_in_profile_update_is_ignored(self):
        body = json.dumps({"display_name": "Legit Name", "role": "ADMIN", "is_active": 1}).encode()
        status, _, _ = invoke(self.app, "POST", "/api/v1/profile", body, self.auth)
        self.assertEqual(status, "204 No Content")
        _, _, payload = invoke(self.app, "GET", "/api/v1/me", headers=self.auth)
        self.assertEqual(json.loads(payload)["role"], "PATIENT")

    def test_patient_cannot_reach_admin_or_clinician_routes(self):
        for method, path in [
            ("GET", "/api/v1/admin/users"),
            ("GET", "/api/v1/admin/relationships"),
            ("POST", "/api/v1/admin/learning/sample"),
            ("GET", "/api/v1/clinician/patients"),
            ("GET", "/api/v1/clinician/alerts"),
            ("GET", "/api/v1/clinician/learning/feedback"),
        ]:
            status, _, _ = invoke(self.app, method, path, headers=self.auth)
            self.assertEqual(status, "401 Unauthorized", f"{method} {path} should be denied to a patient")


class RateLimitingTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.settings = Settings(database_path=Path(self.temp.name) / "test.db", password_iterations=1_000)
        self.app = application(self.settings)
        invoke(self.app, "POST", "/api/v1/auth/register", b'{"email":"limited@example.test","password":"correct horse battery"}', {"Content-Type": "application/json"})
        invoke(self.app, "POST", "/api/v1/auth/register", b'{"email":"unrelated@example.test","password":"correct horse battery"}', {"Content-Type": "application/json"})

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def test_repeated_failed_logins_are_throttled(self):
        bad = json.dumps({"email": "limited@example.test", "password": "wrong password entirely"}).encode()
        statuses = [invoke(self.app, "POST", "/api/v1/auth/sessions", bad, {"Content-Type": "application/json"})[0] for _ in range(6)]
        self.assertIn("429 Too Many Requests", statuses)

    def test_registration_flooding_from_one_source_is_throttled(self):
        statuses = []
        for i in range(11):
            body = json.dumps({"email": f"flood{i}@example.test", "password": "correct horse battery"}).encode()
            statuses.append(invoke(self.app, "POST", "/api/v1/auth/register", body, {"Content-Type": "application/json"})[0])
        self.assertIn("429 Too Many Requests", statuses)

    def test_message_flooding_by_one_patient_is_throttled(self):
        registration = b'{"email":"flooder@example.test","password":"correct horse battery"}'
        invoke(self.app, "POST", "/api/v1/auth/register", registration, {"Content-Type": "application/json"})
        _, _, payload = invoke(self.app, "POST", "/api/v1/auth/sessions", registration, {"Content-Type": "application/json"})
        auth = {"Content-Type": "application/json", "Authorization": "Bearer " + json.loads(payload)["access_token"]}
        invoke(self.app, "POST", "/api/v1/consents", b'{"purpose":"CARE","version":"1"}', auth)
        _, _, payload = invoke(self.app, "POST", "/api/v1/conversations", b"{}", auth)
        conversation_id = json.loads(payload)["id"]
        statuses = []
        for _ in range(35):
            body = json.dumps({"text": "hello"}).encode()
            statuses.append(invoke(self.app, "POST", f"/api/v1/conversations/{conversation_id}/messages", body, auth)[0])
        self.assertIn("429 Too Many Requests", statuses)

    def test_phq9_submission_flooding_by_one_patient_is_throttled(self):
        registration = b'{"email":"phq9flooder@example.test","password":"correct horse battery"}'
        invoke(self.app, "POST", "/api/v1/auth/register", registration, {"Content-Type": "application/json"})
        _, _, payload = invoke(self.app, "POST", "/api/v1/auth/sessions", registration, {"Content-Type": "application/json"})
        auth = {"Content-Type": "application/json", "Authorization": "Bearer " + json.loads(payload)["access_token"]}
        statuses = []
        for _ in range(25):
            body = json.dumps({"answers": [1] * 9}).encode()
            statuses.append(invoke(self.app, "POST", "/api/v1/assessments/phq9", body, auth)[0])
        self.assertIn("429 Too Many Requests", statuses)

    def test_throttling_is_scoped_and_does_not_lock_out_other_accounts(self):
        bad = json.dumps({"email": "limited@example.test", "password": "wrong password entirely"}).encode()
        for _ in range(6):
            invoke(self.app, "POST", "/api/v1/auth/sessions", bad, {"Content-Type": "application/json"})
        good = json.dumps({"email": "unrelated@example.test", "password": "correct horse battery"}).encode()
        status, _, _ = invoke(self.app, "POST", "/api/v1/auth/sessions", good, {"Content-Type": "application/json"})
        self.assertEqual(status, "201 Created")


class PayloadAndContentTypeAbuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.settings = Settings(database_path=Path(self.temp.name) / "test.db", password_iterations=1_000)
        self.app = application(self.settings)

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def test_oversized_body_is_rejected_before_parsing(self):
        oversized = json.dumps({"email": "x@example.test", "password": "y" * (MAX_BODY_BYTES + 1000)}).encode()
        status, _, _ = invoke(self.app, "POST", "/api/v1/auth/register", oversized, {"Content-Type": "application/json"})
        self.assertEqual(status, "413 Payload Too Large")

    def test_wrong_content_type_is_rejected(self):
        status, _, _ = invoke(self.app, "POST", "/api/v1/auth/register", b"email=x&password=y", {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(status, "415 Unsupported Media Type")

    def test_malformed_json_does_not_crash_the_server(self):
        status, _, _ = invoke(self.app, "POST", "/api/v1/auth/register", b"{not valid json", {"Content-Type": "application/json"})
        self.assertEqual(status, "400 Bad Request")

    def test_unknown_route_never_leaks_a_stack_trace(self):
        # unauthenticated: the auth gate runs before route matching, so an unknown
        # path with no token is correctly 401, not 404 -- it never even reveals
        # whether the route exists to a caller who hasn't proven who they are.
        status, _, payload = invoke(self.app, "GET", "/api/v1/this/route/does/not/exist")
        self.assertEqual(status, "401 Unauthorized")
        self.assertNotIn("Traceback", json.dumps(json.loads(payload)))

        # authenticated: only now does a genuinely unknown route surface as 404.
        registration = b'{"email":"routecheck@example.test","password":"correct horse battery"}'
        invoke(self.app, "POST", "/api/v1/auth/register", registration, {"Content-Type": "application/json"})
        _, _, session_payload = invoke(self.app, "POST", "/api/v1/auth/sessions", registration, {"Content-Type": "application/json"})
        auth = {"Authorization": "Bearer " + json.loads(session_payload)["access_token"]}
        status, _, payload = invoke(self.app, "GET", "/api/v1/this/route/does/not/exist", headers=auth)
        self.assertEqual(status, "404 Not Found")
        self.assertNotIn("Traceback", json.dumps(json.loads(payload)))


class SecurityHeadersTests(unittest.TestCase):
    """SEC-002 (security audit, Phase 14+): CSP/HSTS/Permissions-Policy were
    missing entirely before this phase -- only X-Content-Type-Options,
    X-Frame-Options and Referrer-Policy existed."""

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.settings = Settings(database_path=Path(self.temp.name) / "test.db", password_iterations=1_000)
        self.app = application(self.settings)

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def test_api_responses_carry_a_restrictive_header_set(self):
        _, headers, _ = invoke(self.app, "GET", "/health/live")
        self.assertEqual(headers["Content-Security-Policy"], "default-src 'none'; frame-ancestors 'none'")
        self.assertIn("max-age=", headers["Strict-Transport-Security"])
        self.assertIn("geolocation=()", headers["Permissions-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["X-Frame-Options"], "DENY")

    def test_error_responses_also_carry_the_full_header_set(self):
        _, headers, _ = invoke(self.app, "GET", "/api/v1/does/not/exist")
        self.assertIn("Content-Security-Policy", headers)
        self.assertIn("Strict-Transport-Security", headers)


class SecretLeakageTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.settings = Settings(database_path=Path(self.temp.name) / "test.db", password_iterations=1_000)
        self.app = application(self.settings)

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def test_me_endpoint_never_returns_password_hash_or_session_internals(self):
        registration = b'{"email":"secretcheck@example.test","password":"correct horse battery"}'
        invoke(self.app, "POST", "/api/v1/auth/register", registration, {"Content-Type": "application/json"})
        _, _, payload = invoke(self.app, "POST", "/api/v1/auth/sessions", registration, {"Content-Type": "application/json"})
        auth = {"Content-Type": "application/json", "Authorization": "Bearer " + json.loads(payload)["access_token"]}
        _, _, me_payload = invoke(self.app, "GET", "/api/v1/me", headers=auth)
        body_text = me_payload.decode()
        for forbidden in ("password_hash", "mfa_secret", "token_hash"):
            self.assertNotIn(forbidden, body_text)

    def test_failed_login_error_does_not_reveal_whether_the_account_exists(self):
        existing = json.dumps({"email": "secretcheck@example.test", "password": "wrong password"}).encode()
        nonexistent = json.dumps({"email": "never.registered@example.test", "password": "wrong password"}).encode()
        registration = b'{"email":"secretcheck@example.test","password":"correct horse battery"}'
        invoke(self.app, "POST", "/api/v1/auth/register", registration, {"Content-Type": "application/json"})
        status_a, _, payload_a = invoke(self.app, "POST", "/api/v1/auth/sessions", existing, {"Content-Type": "application/json"})
        status_b, _, payload_b = invoke(self.app, "POST", "/api/v1/auth/sessions", nonexistent, {"Content-Type": "application/json"})
        self.assertEqual(status_a, status_b)
        # trace_id is a legitimate per-request correlation UUID and is expected to
        # differ; everything a caller could use to distinguish the two cases must not
        body_a, body_b = json.loads(payload_a), json.loads(payload_b)
        body_a.pop("trace_id"), body_b.pop("trace_id")
        self.assertEqual(body_a, body_b)


class BusinessLogicRaceConditionTests(unittest.TestCase):
    """SEC-001 (security audit, Phase 14+): three functions validated a status
    with one SELECT, then wrote with an unguarded UPDATE -- a classic TOCTOU
    (CWE-362). Reproduced and confirmed exploitable with real, separate
    sqlite3.Connection objects (as two concurrent requests would have) before
    being fixed. These tests force the exact interleaving deterministically
    (no timing-based flakiness) rather than hoping real threads happen to race."""

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.settings = Settings(database_path=Path(self.temp.name) / "race.db", password_iterations=1_000)
        self.setup_conn = connect(self.settings.database_path)
        migrate(self.setup_conn)
        self.service = AuthService(self.setup_conn, self.settings)

    def tearDown(self):
        self.setup_conn.close()
        self.temp.cleanup()

    def test_model_rejection_cannot_be_overwritten_by_a_racing_approval(self):
        admin_id = self.service.provision_privileged_user("admin@race.test", "correct horse battery", "ADMIN", "JBSWY3DPEHPK3PXP", "seed")
        clin_a = self.service.provision_privileged_user("a@race.test", "correct horse battery", "CLINICIAN", "JBSWY3DPEHPK3PXQ", "seed")
        clin_b = self.service.provision_privileged_user("b@race.test", "correct horse battery", "CLINICIAN", "JBSWY3DPEHPK3PXR", "seed")
        clin_c = self.service.provision_privileged_user("c@race.test", "correct horse battery", "CLINICIAN", "JBSWY3DPEHPK3PXS", "seed")
        model = register_model_version(self.setup_conn, admin_id, "RISK", "race-test-1", None, {}, "seed")
        decide_model_version(self.setup_conn, model["id"], clin_c, "APPROVED", "first legitimate approval", "seed")

        # two separate connections, exactly like two concurrent HTTP requests would use
        conn_a = connect(self.settings.database_path)
        conn_b = connect(self.settings.database_path)
        try:
            # B's request reads PENDING_REVIEW (its precondition check would pass)...
            self.assertEqual(conn_b.execute("SELECT status FROM model_versions WHERE id=?", (model["id"],)).fetchone()["status"], "PENDING_REVIEW")
            # ...then A's full, real rejection commits first...
            decide_model_version(conn_a, model["id"], clin_a, "REJECTED", "found a real bias issue", "seed-a")
            self.assertEqual(conn_a.execute("SELECT status FROM model_versions WHERE id=?", (model["id"],)).fetchone()["status"], "REJECTED")
            # ...and only now does B, unaware A already decided, try to record its approval.
            with self.assertRaises(ValueError):
                decide_model_version(conn_b, model["id"], clin_b, "APPROVED", "looked fine to me", "seed-b")
            # the rejection must survive: it is never silently overwritten back to APPROVED
            self.assertEqual(conn_b.execute("SELECT status FROM model_versions WHERE id=?", (model["id"],)).fetchone()["status"], "REJECTED")
        finally:
            conn_a.close()
            conn_b.close()

    def test_feedback_review_cannot_be_overwritten_by_a_racing_reviewer(self):
        # human_feedback.message_id has a real foreign key to messages(id), so a
        # fake id would fail under PRAGMA foreign_keys=ON: create a real message.
        patient_id = self.service.register_patient("racepatient@example.test", "correct horse battery", "seed")
        self.service.grant_consent(patient_id, "LEARNING", "1", "seed")
        conversation_id = str(uuid4())
        self.setup_conn.execute(
            "INSERT INTO conversations(id,patient_id,status,created_at,updated_at) VALUES (?,?,'ACTIVE',?,?)",
            (conversation_id, patient_id, "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
        )
        message_id = str(uuid4())
        self.setup_conn.execute(
            "INSERT INTO messages(id,conversation_id,author_type,content,sequence_no,created_at) VALUES (?,?,'PATIENT','hello',1,?)",
            (message_id, conversation_id, "2026-01-01T00:00:00+00:00"),
        )
        self.setup_conn.execute(
            "INSERT INTO human_feedback(id,message_id,anonymized_content,anonymization_version,review_status,sampled_at) VALUES (?,?,?,?,'PENDING',?)",
            ("feedback-race-1", message_id, "some anonymized text", "anonymization-dev-1", "2026-01-01T00:00:00+00:00"),
        )
        clin_a = self.service.provision_privileged_user("a2@race.test", "correct horse battery", "CLINICIAN", "JBSWY3DPEHPK3PXQ", "seed")
        clin_b = self.service.provision_privileged_user("b2@race.test", "correct horse battery", "CLINICIAN", "JBSWY3DPEHPK3PXR", "seed")

        conn_a = connect(self.settings.database_path)
        conn_b = connect(self.settings.database_path)
        try:
            self.assertEqual(conn_b.execute("SELECT review_status FROM human_feedback WHERE id=?", ("feedback-race-1",)).fetchone()["review_status"], "PENDING")
            review_feedback(conn_a, "feedback-race-1", clin_a, "REJECTED", "not representative", "seed-a")
            with self.assertRaises(ValueError):
                review_feedback(conn_b, "feedback-race-1", clin_b, "APPROVED", "looked fine to me", "seed-b")
            self.assertEqual(conn_b.execute("SELECT review_status FROM human_feedback WHERE id=?", ("feedback-race-1",)).fetchone()["review_status"], "REJECTED")
        finally:
            conn_a.close()
            conn_b.close()

    def test_alert_transition_cannot_be_overwritten_by_a_racing_transition(self):
        patient_id = self.service.register_patient("alertrace@example.test", "correct horse battery", "seed")
        policy = load_crisis_policy(Path("config/policies/crisis-policy-v1.json"))
        rules = load_crisis_rules(Path("config/policies/crisis-rules-v1.json"))
        outcome = handle_incoming_message(self.setup_conn, patient_id, "plan suicidaire", "msg-race-2", KeywordRiskModel(), policy, rules, LogNotificationProvider(), "seed")
        alert_id = outcome.alert["id"]
        clinician_id = self.service.provision_privileged_user("clin-race@race.test", "correct horse battery", "CLINICIAN", "JBSWY3DPEHPK3PXQ", "seed")

        conn_a = connect(self.settings.database_path)
        conn_b = connect(self.settings.database_path)
        try:
            # both requests read the alert while it is still OPEN
            self.assertEqual(conn_b.execute("SELECT status FROM alerts WHERE id=?", (alert_id,)).fetchone()["status"], "OPEN")
            # A's transition to CANCELLED commits first
            transition(conn_a, alert_id, "CANCELLED", clinician_id, "false alarm, closing")
            self.assertEqual(conn_a.execute("SELECT status FROM alerts WHERE id=?", (alert_id,)).fetchone()["status"], "CANCELLED")
            # B, still believing the alert was OPEN, tries to escalate it instead
            with self.assertRaises(ValueError):
                transition(conn_b, alert_id, "ESCALATED", clinician_id, "escalating to psychiatrist on call")
            # A's cancellation must not be silently discarded by B's stale write
            self.assertEqual(conn_b.execute("SELECT status FROM alerts WHERE id=?", (alert_id,)).fetchone()["status"], "CANCELLED")
            # exactly one action was recorded, not two conflicting ones
            actions = conn_b.execute("SELECT action FROM alert_actions WHERE alert_id=?", (alert_id,)).fetchall()
            self.assertEqual([row["action"] for row in actions], ["CANCELLED"])
        finally:
            conn_a.close()
            conn_b.close()


if __name__ == "__main__":
    unittest.main()
