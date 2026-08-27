"""Full end-to-end journeys (master prompt Section 43 / Phase 13).

Each test tells one complete story from start to finish, exercising the real
WSGI application exactly as an HTTP client would, across every domain the
story touches. This is deliberately different from the domain test files
(test_conversation.py, test_clinician_dashboard.py, test_learning_pipeline.py,
etc.): those verify one module's contract in isolation; these verify that the
modules actually compose into the journeys the project is meant to support.
A change that breaks the *integration* between two correctly-behaving modules
would still pass every per-module test but should fail here.

Scope note: this is E2E at the HTTP/application layer (calling the real
`application(settings)` WSGI callable end to end), not a browser-driven E2E.
The UI layer for each of these journeys was manually verified in a real
browser during the phase that built it (see docs/reports/phase-7, phase-8a,
phase-8b, phase-23). Scripting an actual browser-driven E2E suite would mean
adding a browser-automation dependency (e.g. Playwright) -- a deliberate
choice left to the user rather than added unilaterally.
"""
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
from backend.app.db import connect
from backend.app.http import application

ADMIN_SECRET = "KRSXG5CTMVRXEZLU"
CLINICIAN_SECRET = "JBSWY3DPEHPK3PXP"
OTHER_CLINICIAN_SECRET = "JBSWY3DPEHPK3PXQ"


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


class JourneyTestBase(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.settings = Settings(database_path=Path(self.temp.name) / "test.db", password_iterations=1_000)
        self.app = application(self.settings)
        self.conn = connect(self.settings.database_path)

    def tearDown(self):
        self.conn.close()
        self.app.close()
        self.temp.cleanup()

    def auth(self, token: str) -> dict:
        return {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}

    def register_and_login_patient(self, email: str) -> str:
        body = json.dumps({"email": email, "password": "correct horse battery"}).encode()
        status, _, _ = invoke(self.app, "POST", "/api/v1/auth/register", body, {"Content-Type": "application/json"})
        self.assertEqual(status, "201 Created")
        status, _, payload = invoke(self.app, "POST", "/api/v1/auth/sessions", body, {"Content-Type": "application/json"})
        self.assertEqual(status, "201 Created")
        return json.loads(payload)["access_token"]

    def login_privileged(self, email: str, secret: str) -> str:
        body = json.dumps({"email": email, "password": "correct horse battery", "totp_code": totp_now(secret)}).encode()
        status, _, payload = invoke(self.app, "POST", "/api/v1/auth/sessions", body, {"Content-Type": "application/json"})
        self.assertEqual(status, "201 Created")
        return json.loads(payload)["access_token"]

    def provision(self, email: str, role: str, secret: str) -> str:
        return AuthService(self.conn, self.settings).provision_privileged_user(email, "correct horse battery", role, secret, "seed")


class NormalUserJourneyTest(JourneyTestBase):
    """Registration -> Consent -> Onboarding -> Chat -> PHQ-9 -> Dashboard."""

    def test_normal_journey(self):
        patient_token = self.register_and_login_patient("normal.journey@example.test")
        patient_auth = self.auth(patient_token)

        # onboarding: profile + care consent (as the real onboarding form does)
        status, _, _ = invoke(self.app, "POST", "/api/v1/profile", b'{"display_name":"Alex"}', patient_auth)
        self.assertEqual(status, "204 No Content")
        status, _, _ = invoke(self.app, "POST", "/api/v1/consents", b'{"purpose":"CARE","version":"1"}', patient_auth)
        self.assertEqual(status, "204 No Content")

        # chat: a calm message gets a normal acknowledgment, not a safety template
        status, _, payload = invoke(self.app, "POST", "/api/v1/conversations", b"{}", patient_auth)
        self.assertEqual(status, "201 Created")
        conversation_id = json.loads(payload)["id"]
        status, _, payload = invoke(
            self.app, "POST", f"/api/v1/conversations/{conversation_id}/messages",
            json.dumps({"text": "Bonjour, ma semaine s'est plutot bien passee."}).encode(), patient_auth,
        )
        self.assertEqual(status, "201 Created")
        chat_result = json.loads(payload)
        self.assertNotIn("urgence", chat_result["assistant_message"]["content"])

        # PHQ-9
        status, _, payload = invoke(
            self.app, "POST", "/api/v1/assessments/phq9",
            json.dumps({"answers": [1, 1, 0, 1, 0, 1, 0, 1, 0]}).encode(), patient_auth,
        )
        self.assertEqual(status, "201 Created")
        phq9_score = json.loads(payload)["total_score"]
        self.assertEqual(phq9_score, 5)

        # a clinician is assigned to this patient by an admin
        patient_id = json.loads(invoke(self.app, "GET", "/api/v1/me", headers=patient_auth)[2])["id"]
        self.provision("normal.admin@example.test", "ADMIN", ADMIN_SECRET)
        clinician_id = self.provision("normal.clinician@example.test", "CLINICIAN", CLINICIAN_SECRET)
        admin_token = self.login_privileged("normal.admin@example.test", ADMIN_SECRET)
        status, _, _ = invoke(
            self.app, "POST", "/api/v1/admin/relationships",
            json.dumps({"patient_id": patient_id, "clinician_id": clinician_id}).encode(), self.auth(admin_token),
        )
        self.assertEqual(status, "201 Created")

        # the dashboard: clinician sees the patient with the right PHQ-9 score and no open alerts
        clinician_token = self.login_privileged("normal.clinician@example.test", CLINICIAN_SECRET)
        status, _, payload = invoke(self.app, "GET", "/api/v1/clinician/patients", headers=self.auth(clinician_token))
        self.assertEqual(status, "200 OK")
        patients = json.loads(payload)["items"]
        self.assertEqual(len(patients), 1)
        self.assertEqual(patients[0]["latest_phq9_score"], phq9_score)
        self.assertEqual(patients[0]["open_alert_count"], 0)

        status, _, payload = invoke(self.app, "GET", f"/api/v1/clinician/patients/{patient_id}/timeline", headers=self.auth(clinician_token))
        timeline = json.loads(payload)
        self.assertEqual(len(timeline["phq9_history"]), 1)
        self.assertEqual(timeline["alerts"], [])  # a calm message never opens an alert


class DistressJourneyTest(JourneyTestBase):
    """Chat -> risk detection -> ORANGE alert -> notification attempt -> clinician review."""

    def test_distress_journey(self):
        patient_token = self.register_and_login_patient("distress.journey@example.test")
        patient_auth = self.auth(patient_token)
        invoke(self.app, "POST", "/api/v1/consents", b'{"purpose":"CARE","version":"1"}', patient_auth)
        patient_id = json.loads(invoke(self.app, "GET", "/api/v1/me", headers=patient_auth)[2])["id"]

        self.provision("distress.admin@example.test", "ADMIN", ADMIN_SECRET)
        clinician_id = self.provision("distress.clinician@example.test", "CLINICIAN", CLINICIAN_SECRET)
        admin_token = self.login_privileged("distress.admin@example.test", ADMIN_SECRET)
        invoke(self.app, "POST", "/api/v1/admin/relationships", json.dumps({"patient_id": patient_id, "clinician_id": clinician_id}).encode(), self.auth(admin_token))

        status, _, payload = invoke(self.app, "POST", "/api/v1/conversations", b"{}", patient_auth)
        conversation_id = json.loads(payload)["id"]
        status, _, payload = invoke(
            self.app, "POST", f"/api/v1/conversations/{conversation_id}/messages",
            json.dumps({"text": "Je suis desespere et je me sens perdu en ce moment."}).encode(), patient_auth,
        )
        self.assertEqual(status, "201 Created")
        self.assertIn("professionnel", json.loads(payload)["assistant_message"]["content"])

        # the alert exists, is scoped to this clinician, and a notification was attempted
        clinician_token = self.login_privileged("distress.clinician@example.test", CLINICIAN_SECRET)
        status, _, payload = invoke(self.app, "GET", "/api/v1/clinician/alerts?level=ORANGE", headers=self.auth(clinician_token))
        alerts = json.loads(payload)["items"]
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["status"], "OPEN")
        notification_count = self.conn.execute("SELECT count(*) FROM notifications WHERE alert_id=?", (alerts[0]["id"],)).fetchone()[0]
        self.assertEqual(notification_count, 1)  # honestly SKIPPED_NO_CHANNEL by default policy, but attempted and recorded

        # clinician review
        status, _, payload = invoke(
            self.app, "POST", f"/api/v1/clinician/alerts/{alerts[0]['id']}/actions",
            json.dumps({"action": "ACKNOWLEDGED", "justification": "Contact pris avec la patiente."}).encode(), self.auth(clinician_token),
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(json.loads(payload)["status"], "ACKNOWLEDGED")


class CrisisJourneyTest(JourneyTestBase):
    """Chat -> crisis engine -> RED alert -> escalation -> human action -> resolution."""

    def test_crisis_journey(self):
        patient_token = self.register_and_login_patient("crisis.journey@example.test")
        patient_auth = self.auth(patient_token)
        invoke(self.app, "POST", "/api/v1/consents", b'{"purpose":"CARE","version":"1"}', patient_auth)
        patient_id = json.loads(invoke(self.app, "GET", "/api/v1/me", headers=patient_auth)[2])["id"]

        self.provision("crisis.admin@example.test", "ADMIN", ADMIN_SECRET)
        clinician_id = self.provision("crisis.clinician@example.test", "CLINICIAN", CLINICIAN_SECRET)
        admin_token = self.login_privileged("crisis.admin@example.test", ADMIN_SECRET)
        invoke(self.app, "POST", "/api/v1/admin/relationships", json.dumps({"patient_id": patient_id, "clinician_id": clinician_id}).encode(), self.auth(admin_token))

        _, _, payload = invoke(self.app, "POST", "/api/v1/conversations", b"{}", patient_auth)
        conversation_id = json.loads(payload)["id"]
        status, _, payload = invoke(
            self.app, "POST", f"/api/v1/conversations/{conversation_id}/messages",
            json.dumps({"text": "J'ai un plan suicidaire, je veux en finir ce soir."}).encode(), patient_auth,
        )
        self.assertEqual(status, "201 Created")
        self.assertIn("urgence", json.loads(payload)["assistant_message"]["content"])

        clinician_token = self.login_privileged("crisis.clinician@example.test", CLINICIAN_SECRET)
        status, _, payload = invoke(self.app, "GET", "/api/v1/clinician/alerts?level=RED", headers=self.auth(clinician_token))
        alerts = json.loads(payload)["items"]
        self.assertEqual(len(alerts), 1)
        alert_id = alerts[0]["id"]
        self.assertEqual(alerts[0]["status"], "OPEN")

        # escalation -> human action -> resolution: walk the full lifecycle
        for target, justification in [
            ("ESCALATED", "Situation a haut risque, escalade vers le psychiatre de garde."),
            ("RESOLVED", "Patiente jointe et mise en securite, suivi programme."),
        ]:
            status, _, payload = invoke(
                self.app, "POST", f"/api/v1/clinician/alerts/{alert_id}/actions",
                json.dumps({"action": target, "justification": justification}).encode(), self.auth(clinician_token),
            )
            self.assertEqual(status, "200 OK", f"transition to {target} failed: {payload}")
            self.assertEqual(json.loads(payload)["status"], target)

        # every transition left an auditable action with its justification
        actions = self.conn.execute("SELECT action, justification FROM alert_actions WHERE alert_id=? ORDER BY created_at", (alert_id,)).fetchall()
        self.assertEqual([row["action"] for row in actions], ["ESCALATED", "RESOLVED"])
        self.assertTrue(all(row["justification"] for row in actions))


class LearningJourneyTest(JourneyTestBase):
    """Production sample -> anonymization -> clinician review -> dataset -> model
    registration -> dual clinical approval -> deployment -> rollback."""

    def test_learning_journey(self):
        patient_token = self.register_and_login_patient("learning.journey@example.test")
        patient_auth = self.auth(patient_token)
        invoke(self.app, "POST", "/api/v1/consents", b'{"purpose":"CARE","version":"1"}', patient_auth)
        invoke(self.app, "POST", "/api/v1/consents", b'{"purpose":"LEARNING","version":"1"}', patient_auth)

        _, _, payload = invoke(self.app, "POST", "/api/v1/conversations", b"{}", patient_auth)
        conversation_id = json.loads(payload)["id"]
        invoke(
            self.app, "POST", f"/api/v1/conversations/{conversation_id}/messages",
            json.dumps({"text": "Ma journee etait plutot calme, merci de demander."}).encode(), patient_auth,
        )

        self.provision("learning.admin@example.test", "ADMIN", ADMIN_SECRET)
        self.provision("learning.clinician1@example.test", "CLINICIAN", CLINICIAN_SECRET)
        self.provision("learning.clinician2@example.test", "CLINICIAN", OTHER_CLINICIAN_SECRET)
        admin_token = self.login_privileged("learning.admin@example.test", ADMIN_SECRET)
        clinician1_token = self.login_privileged("learning.clinician1@example.test", CLINICIAN_SECRET)
        clinician2_token = self.login_privileged("learning.clinician2@example.test", OTHER_CLINICIAN_SECRET)

        # production -> sampling -> anonymization
        status, _, payload = invoke(self.app, "POST", "/api/v1/admin/learning/sample", b"{}", self.auth(admin_token))
        self.assertEqual(status, "201 Created")
        self.assertEqual(json.loads(payload)["created"], 1)

        # clinician review
        _, _, payload = invoke(self.app, "GET", "/api/v1/clinician/learning/feedback", headers=self.auth(clinician1_token))
        feedback_id = json.loads(payload)["items"][0]["id"]
        status, _, _ = invoke(
            self.app, "POST", f"/api/v1/clinician/learning/feedback/{feedback_id}/review",
            json.dumps({"decision": "APPROVED", "justification": "Contenu sur et representatif."}).encode(), self.auth(clinician1_token),
        )
        self.assertEqual(status, "200 OK")

        # dataset version
        status, _, payload = invoke(self.app, "POST", "/api/v1/admin/learning/datasets", b"{}", self.auth(admin_token))
        self.assertEqual(status, "201 Created")
        dataset = json.loads(payload)
        self.assertEqual(dataset["status"], "FINALIZED")

        # model registry with dual clinical approval
        status, _, payload = invoke(
            self.app, "POST", "/api/v1/admin/learning/models",
            json.dumps({"kind": "EMOTION", "version": "e2e-journey-model-1", "dataset_id": dataset["id"], "metrics": {"test_accuracy": 0.69}}).encode(),
            self.auth(admin_token),
        )
        self.assertEqual(status, "201 Created")
        model_id = json.loads(payload)["id"]

        for token in (clinician1_token, clinician2_token):
            status, _, payload = invoke(
                self.app, "POST", f"/api/v1/clinician/learning/models/{model_id}/decisions",
                json.dumps({"decision": "APPROVED", "justification": "Portee et limites revues, acceptable."}).encode(), self.auth(token),
            )
            self.assertEqual(status, "200 OK")
        self.assertEqual(json.loads(payload)["status"], "APPROVED")

        # deployment
        status, _, payload = invoke(self.app, "POST", f"/api/v1/admin/learning/models/{model_id}/deploy", b"{}", self.auth(admin_token))
        self.assertEqual(status, "200 OK")
        self.assertEqual(json.loads(payload)["status"], "DEPLOYED")

        # rollback (Section 15 explicitly requires this capability to exist)
        status, _, payload = invoke(self.app, "POST", f"/api/v1/admin/learning/models/{model_id}/rollback", b"{}", self.auth(admin_token))
        self.assertEqual(status, "200 OK")
        self.assertEqual(json.loads(payload)["status"], "ROLLED_BACK")


if __name__ == "__main__":
    unittest.main()
