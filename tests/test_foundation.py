from __future__ import annotations

import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.ai import KeywordRiskModel
from backend.app.alerts import open_alert, transition
from backend.app.auth import AuthService, require_role
from backend.app.config import Settings
from backend.app.crisis import CrisisDetector
from backend.app.db import MIGRATIONS, connect, migrate
from backend.app.http import application
from backend.app.phq9 import calculate
from backend.app.policy import load_crisis_policy, load_crisis_rules
from backend.app.security import verify_totp

DEFAULT_POLICY = load_crisis_policy(Path("config/policies/crisis-policy-v1.json"))
DEFAULT_RULES = load_crisis_rules(Path("config/policies/crisis-rules-v1.json"))


def invoke(app, method: str, path: str, body: bytes = b"", headers: dict[str, str] | None = None):
    result = {}
    headers = headers or {}
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "wsgi.input": BytesIO(body),
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": headers.get("Content-Type", ""),
        "REMOTE_ADDR": "127.0.0.1",
    }
    if "Authorization" in headers:
        environ["HTTP_AUTHORIZATION"] = headers["Authorization"]

    def start_response(status, response_headers):
        result["status"], result["headers"] = status, dict(response_headers)

    payload = b"".join(app(environ, start_response))
    return result["status"], result["headers"], payload


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.settings = Settings(database_path=Path(self.temp.name) / "test.db", password_iterations=1_000)
        self.app = application(self.settings)

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def test_migration_is_idempotent(self):
        conn = connect(self.settings.database_path)
        try:
            migrate(conn)
            migrate(conn)
            self.assertEqual(conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0], len(MIGRATIONS))
        finally:
            conn.close()

    def test_register_login_me_and_logout(self):
        registration = b'{"email":"patient@example.test","password":"correct horse battery"}'
        status, headers, _ = invoke(self.app, "POST", "/api/v1/auth/register", registration, {"Content-Type": "application/json"})
        self.assertEqual(status, "201 Created")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

        status, _, payload = invoke(self.app, "POST", "/api/v1/auth/sessions", registration, {"Content-Type": "application/json"})
        self.assertEqual(status, "201 Created")
        token = __import__("json").loads(payload)["access_token"]

        status, _, payload = invoke(self.app, "GET", "/api/v1/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(status, "200 OK")
        self.assertIn(b'"role":"PATIENT"', payload)

        status, _, _ = invoke(self.app, "POST", "/api/v1/auth/logout", b"{}", {"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
        self.assertEqual(status, "204 No Content")
        status, _, _ = invoke(self.app, "GET", "/api/v1/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(status, "401 Unauthorized")

    def test_rejects_non_json_and_short_password(self):
        status, _, _ = invoke(self.app, "POST", "/api/v1/auth/register", b"email=x", {"Content-Type": "text/plain"})
        self.assertEqual(status, "415 Unsupported Media Type")
        body = b'{"email":"x@example.test","password":"short"}'
        status, _, _ = invoke(self.app, "POST", "/api/v1/auth/register", body, {"Content-Type": "application/json"})
        self.assertEqual(status, "401 Unauthorized")

    def test_health_and_rbac_denial(self):
        status, _, payload = invoke(self.app, "GET", "/health/live")
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload, b'{"status":"live"}')
        conn = connect(self.settings.database_path)
        user_id = AuthService(conn, self.settings).register_patient("rbac@example.test", "correct horse battery", "rbac")
        user = conn.execute("SELECT id, email, role FROM users WHERE id=?", (user_id,)).fetchone()
        with self.assertRaises(PermissionError):
            require_role(user, "CLINICIAN")
        self.assertEqual(conn.execute("SELECT count(*) FROM audit_logs").fetchone()[0], 1)
        conn.close()

    def test_profile_consent_and_deletion_request(self):
        registration = b'{"email":"privacy@example.test","password":"correct horse battery"}'
        invoke(self.app, "POST", "/api/v1/auth/register", registration, {"Content-Type": "application/json"})
        _, _, payload = invoke(self.app, "POST", "/api/v1/auth/sessions", registration, {"Content-Type": "application/json"})
        token = __import__("json").loads(payload)["access_token"]
        auth = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        self.assertEqual(invoke(self.app, "POST", "/api/v1/profile", b'{"display_name":"Camille"}', auth)[0], "204 No Content")
        self.assertEqual(invoke(self.app, "POST", "/api/v1/consents", b'{"purpose":"CARE","version":"1"}', auth)[0], "204 No Content")
        self.assertEqual(invoke(self.app, "POST", "/api/v1/consents", b'{"purpose":"LEARNING","version":"1"}', auth)[0], "204 No Content")
        self.assertEqual(invoke(self.app, "POST", "/api/v1/consents/revoke", b'{"purpose":"LEARNING"}', auth)[0], "204 No Content")
        self.assertEqual(invoke(self.app, "POST", "/api/v1/privacy/deletion-requests", b"{}", auth)[0], "202 Accepted")

    def test_phq9_score_validation_and_history(self):
        self.assertEqual(calculate([0, 1, 2, 3, 0, 1, 2, 3, 1]).total_score, 13)
        with self.assertRaises(ValueError): calculate([0] * 8)
        with self.assertRaises(ValueError): calculate(None)  # missing field must not raise a bare TypeError
        registration = b'{"email":"phq@example.test","password":"correct horse battery"}'
        invoke(self.app, "POST", "/api/v1/auth/register", registration, {"Content-Type": "application/json"})
        _, _, payload = invoke(self.app, "POST", "/api/v1/auth/sessions", registration, {"Content-Type": "application/json"})
        auth = {"Content-Type": "application/json", "Authorization": "Bearer " + __import__("json").loads(payload)["access_token"]}
        status, _, payload = invoke(self.app, "POST", "/api/v1/assessments/phq9", b'{"answers":[0,1,2,3,0,1,2,3,1]}', auth)
        self.assertEqual(status, "201 Created"); self.assertIn(b'"total_score":13', payload)
        status, _, _ = invoke(self.app, "POST", "/api/v1/assessments/phq9", b'{}', auth)
        self.assertEqual(status, "401 Unauthorized")  # missing "answers" is rejected cleanly, not a 500
        status, _, payload = invoke(self.app, "GET", "/api/v1/assessments/phq9", headers={"Authorization": auth["Authorization"]})
        self.assertEqual(status, "200 OK"); self.assertIn(b'"total_score":13', payload)

    def test_risk_engine_is_independent_and_conservative(self):
        model = KeywordRiskModel()
        detector = CrisisDetector(DEFAULT_POLICY, DEFAULT_RULES)
        self.assertEqual(detector.evaluate("J'ai un plan suicidaire", model).level, "RED")
        self.assertEqual(detector.evaluate("Je suis perdu", model).level, "ORANGE")
        # No rule or model signal at all -> GREEN. Regression guard: this used to come
        # back ORANGE for every ordinary message because the model's "no match"
        # confidence (0.50) sat below the policy's uncertainty floor (0.65), which
        # made the conservative fallback fire unconditionally (found by exercising
        # the chat feature manually, see Phase 8 report).
        self.assertEqual(detector.evaluate("Ma journée était calme", model).level, "GREEN")

    def test_alert_idempotency_and_state_machine(self):
        conn=connect(self.settings.database_path); migrate(conn); service=AuthService(conn,self.settings); user=service.register_patient("alert@example.test","correct horse battery","a")
        detector=CrisisDetector(DEFAULT_POLICY, DEFAULT_RULES); decision=detector.evaluate("plan suicidaire",KeywordRiskModel())
        conn.execute("INSERT INTO risk_assessments(id,patient_id,input_reference,score,confidence,model_version,model_available,created_at) VALUES ('ra-1',?,'ref',?,?,?,1,'2026-01-01T00:00:00+00:00')",(user,decision.score,decision.confidence,decision.model_version))
        conn.execute("INSERT INTO crisis_events(id,risk_assessment_id,patient_id,level,reasons,rules_version,policy_version,created_at) VALUES ('ce-1','ra-1',?,?,?,?,?,'2026-01-01T00:00:00+00:00')",(user,decision.level,",".join(decision.reasons),decision.rules_version,decision.policy_version))
        first,created_first=open_alert(conn,user,"ce-1",decision,"message-1"); second,created_second=open_alert(conn,user,"ce-1",decision,"message-1")
        self.assertEqual(first["id"],second["id"]); self.assertTrue(created_first); self.assertFalse(created_second)
        transition(conn,first["id"],"ACKNOWLEDGED",user,"review started")
        with self.assertRaises(ValueError): transition(conn,first["id"],"CLOSED",user,"too early")
        conn.close()

    def test_clinician_requires_totp(self):
        conn = connect(self.settings.database_path)
        service = AuthService(conn, self.settings)
        user_id = service.register_patient("clinician@example.test", "correct horse battery", "seed")
        secret = "JBSWY3DPEHPK3PXP"
        conn.execute("UPDATE users SET role='CLINICIAN', mfa_secret=? WHERE id=?", (secret, user_id))
        with self.assertRaises(PermissionError):
            service.authenticate("clinician@example.test", "correct horse battery", "mfa")
        self.assertFalse(verify_totp(secret, "000000", now=0))
        conn.close()


if __name__ == "__main__":
    unittest.main()
