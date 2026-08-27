from __future__ import annotations

import base64
import hashlib
import hmac
import json
import struct
import time
import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.auth import AuthService
from backend.app.config import Settings
from backend.app.http import application

CLINICIAN_SECRET = "JBSWY3DPEHPK3PXP"
ADMIN_SECRET = "KRSXG5CTMVRXEZLU"


def totp_now(secret_b32: str) -> str:
    key = base64.b32decode(secret_b32.upper())
    counter = int(time.time()) // 30
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    index = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[index:index + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{value:06d}"


def invoke(app, method: str, path: str, body: bytes = b"", headers: dict[str, str] | None = None):
    result = {}
    headers = headers or {}
    path, _, query = path.partition("?")
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query,
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


class ClinicianDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.settings = Settings(database_path=Path(self.temp.name) / "test.db", password_iterations=1_000)
        self.app = application(self.settings)
        from backend.app.db import connect
        self.conn = connect(self.settings.database_path)
        service = AuthService(self.conn, self.settings)

        self.patient_id = service.register_patient("patient@example.test", "correct horse battery", "seed")
        self.other_patient_id = service.register_patient("other-patient@example.test", "correct horse battery", "seed")
        self.clinician_id = service.provision_privileged_user("clinician@example.test", "correct horse battery", "CLINICIAN", CLINICIAN_SECRET, "seed")
        self.other_clinician_id = service.provision_privileged_user("other-clinician@example.test", "correct horse battery", "CLINICIAN", "JBSWY3DPEHPK3PXQ", "seed")
        self.admin_id = service.provision_privileged_user("admin@example.test", "correct horse battery", "ADMIN", ADMIN_SECRET, "seed")

        self.admin_token = self._login("admin@example.test", ADMIN_SECRET)
        self.clinician_token = self._login("clinician@example.test", CLINICIAN_SECRET)
        self.other_clinician_token = self._login("other-clinician@example.test", "JBSWY3DPEHPK3PXQ")
        self.patient_token = self._patient_login("patient@example.test")

    def tearDown(self):
        self.conn.close()
        self.app.close()
        self.temp.cleanup()

    def _login(self, email: str, secret: str) -> str:
        body = json.dumps({"email": email, "password": "correct horse battery", "totp_code": totp_now(secret)}).encode()
        _, _, payload = invoke(self.app, "POST", "/api/v1/auth/sessions", body, {"Content-Type": "application/json"})
        return json.loads(payload)["access_token"]

    def _patient_login(self, email: str) -> str:
        body = json.dumps({"email": email, "password": "correct horse battery"}).encode()
        _, _, payload = invoke(self.app, "POST", "/api/v1/auth/sessions", body, {"Content-Type": "application/json"})
        return json.loads(payload)["access_token"]

    def _auth(self, token: str) -> dict:
        return {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}

    def _create_relationship(self, patient_id: str, clinician_id: str) -> str:
        body = json.dumps({"patient_id": patient_id, "clinician_id": clinician_id}).encode()
        status, _, payload = invoke(self.app, "POST", "/api/v1/admin/relationships", body, self._auth(self.admin_token))
        self.assertEqual(status, "201 Created")
        return json.loads(payload)["id"]

    def test_only_admin_can_create_relationships(self):
        body = json.dumps({"patient_id": self.patient_id, "clinician_id": self.clinician_id}).encode()
        status, _, _ = invoke(self.app, "POST", "/api/v1/admin/relationships", body, self._auth(self.patient_token))
        self.assertEqual(status, "401 Unauthorized")

    def test_relationship_creation_is_idempotent(self):
        first = self._create_relationship(self.patient_id, self.clinician_id)
        body = json.dumps({"patient_id": self.patient_id, "clinician_id": self.clinician_id}).encode()
        status, _, payload = invoke(self.app, "POST", "/api/v1/admin/relationships", body, self._auth(self.admin_token))
        self.assertEqual(status, "201 Created")
        self.assertEqual(json.loads(payload)["id"], first)

    def test_clinician_sees_only_their_own_patients(self):
        self._create_relationship(self.patient_id, self.clinician_id)
        status, _, payload = invoke(self.app, "GET", "/api/v1/clinician/patients", headers=self._auth(self.clinician_token))
        self.assertEqual(status, "200 OK")
        items = json.loads(payload)["items"]
        self.assertEqual([item["patient_id"] for item in items], [self.patient_id])

        status, _, payload = invoke(self.app, "GET", "/api/v1/clinician/patients", headers=self._auth(self.other_clinician_token))
        self.assertEqual(json.loads(payload)["items"], [])

    def test_timeline_denied_without_active_relationship(self):
        status, _, _ = invoke(self.app, "GET", f"/api/v1/clinician/patients/{self.patient_id}/timeline", headers=self._auth(self.clinician_token))
        self.assertEqual(status, "401 Unauthorized")

    def test_timeline_includes_phq9_and_alerts_for_owned_patient(self):
        self._create_relationship(self.patient_id, self.clinician_id)
        invoke(self.app, "POST", "/api/v1/assessments/phq9", json.dumps({"answers": [1, 1, 1, 1, 1, 1, 1, 1, 1]}).encode(), self._auth(self.patient_token))

        from backend.app.ai import KeywordRiskModel
        from backend.app.notifications import LogNotificationProvider
        from backend.app.pipeline import handle_incoming_message
        from backend.app.policy import load_crisis_policy, load_crisis_rules
        policy = load_crisis_policy(Path("config/policies/crisis-policy-v1.json"))
        rules = load_crisis_rules(Path("config/policies/crisis-rules-v1.json"))
        handle_incoming_message(self.conn, self.patient_id, "plan suicidaire", "msg-1", KeywordRiskModel(), policy, rules, LogNotificationProvider(), "req-1")

        status, _, payload = invoke(self.app, "GET", f"/api/v1/clinician/patients/{self.patient_id}/timeline", headers=self._auth(self.clinician_token))
        self.assertEqual(status, "200 OK")
        timeline = json.loads(payload)
        self.assertEqual(len(timeline["phq9_history"]), 1)
        self.assertEqual(len(timeline["alerts"]), 1)
        self.assertEqual(timeline["alerts"][0]["level"], "RED")

    def test_alerts_are_scoped_and_filterable(self):
        self._create_relationship(self.patient_id, self.clinician_id)
        from backend.app.ai import KeywordRiskModel
        from backend.app.notifications import LogNotificationProvider
        from backend.app.pipeline import handle_incoming_message
        from backend.app.policy import load_crisis_policy, load_crisis_rules
        policy = load_crisis_policy(Path("config/policies/crisis-policy-v1.json"))
        rules = load_crisis_rules(Path("config/policies/crisis-rules-v1.json"))
        handle_incoming_message(self.conn, self.patient_id, "plan suicidaire", "msg-1", KeywordRiskModel(), policy, rules, LogNotificationProvider(), "req-1")

        _, _, payload = invoke(self.app, "GET", "/api/v1/clinician/alerts", headers=self._auth(self.clinician_token))
        self.assertEqual(len(json.loads(payload)["items"]), 1)

        _, _, payload = invoke(self.app, "GET", "/api/v1/clinician/alerts?level=GREEN", headers=self._auth(self.clinician_token))
        self.assertEqual(json.loads(payload)["items"], [])

        _, _, payload = invoke(self.app, "GET", "/api/v1/clinician/alerts", headers=self._auth(self.other_clinician_token))
        self.assertEqual(json.loads(payload)["items"], [])

    def test_cannot_act_on_alert_without_relationship(self):
        self._create_relationship(self.patient_id, self.clinician_id)
        from backend.app.ai import KeywordRiskModel
        from backend.app.notifications import LogNotificationProvider
        from backend.app.pipeline import handle_incoming_message
        from backend.app.policy import load_crisis_policy, load_crisis_rules
        policy = load_crisis_policy(Path("config/policies/crisis-policy-v1.json"))
        rules = load_crisis_rules(Path("config/policies/crisis-rules-v1.json"))
        outcome = handle_incoming_message(self.conn, self.patient_id, "plan suicidaire", "msg-1", KeywordRiskModel(), policy, rules, LogNotificationProvider(), "req-1")
        alert_id = outcome.alert["id"]

        body = json.dumps({"action": "ACKNOWLEDGED", "justification": "review started"}).encode()
        status, _, _ = invoke(self.app, "POST", f"/api/v1/clinician/alerts/{alert_id}/actions", body, self._auth(self.other_clinician_token))
        self.assertEqual(status, "401 Unauthorized")

        status, _, payload = invoke(self.app, "POST", f"/api/v1/clinician/alerts/{alert_id}/actions", body, self._auth(self.clinician_token))
        self.assertEqual(status, "200 OK")
        self.assertEqual(json.loads(payload)["status"], "ACKNOWLEDGED")

    def test_ending_a_relationship_revokes_access(self):
        relationship_id = self._create_relationship(self.patient_id, self.clinician_id)
        status, _, _ = invoke(self.app, "POST", f"/api/v1/admin/relationships/{relationship_id}/end", headers=self._auth(self.admin_token))
        self.assertEqual(status, "204 No Content")
        status, _, payload = invoke(self.app, "GET", "/api/v1/clinician/patients", headers=self._auth(self.clinician_token))
        self.assertEqual(json.loads(payload)["items"], [])
        status, _, _ = invoke(self.app, "GET", f"/api/v1/clinician/patients/{self.patient_id}/timeline", headers=self._auth(self.clinician_token))
        self.assertEqual(status, "401 Unauthorized")


if __name__ == "__main__":
    unittest.main()
