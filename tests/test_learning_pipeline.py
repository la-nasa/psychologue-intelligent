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
from backend.app.learning import anonymize_text

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


class AnonymizationTests(unittest.TestCase):
    def test_redacts_email_and_phone(self):
        redacted = anonymize_text("Contact me at jane.doe@example.com or 06 12 34 56 78 please.")
        self.assertNotIn("jane.doe@example.com", redacted)
        self.assertNotIn("06 12 34 56 78", redacted)
        self.assertIn("[REDACTED_EMAIL]", redacted)
        self.assertIn("[REDACTED_PHONE]", redacted)

    def test_leaves_ordinary_text_untouched(self):
        text = "I had a calm day today."
        self.assertEqual(anonymize_text(text), text)


class LearningPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.settings = Settings(database_path=Path(self.temp.name) / "test.db", password_iterations=1_000)
        self.app = application(self.settings)
        self.conn = connect(self.settings.database_path)
        service = AuthService(self.conn, self.settings)

        self.admin_id = service.provision_privileged_user("admin@example.test", "correct horse battery", "ADMIN", ADMIN_SECRET, "seed")
        self.clinician_id = service.provision_privileged_user("clinician@example.test", "correct horse battery", "CLINICIAN", CLINICIAN_SECRET, "seed")
        self.other_clinician_id = service.provision_privileged_user("other-clinician@example.test", "correct horse battery", "CLINICIAN", OTHER_CLINICIAN_SECRET, "seed")

        self.admin_token = self._login("admin@example.test", ADMIN_SECRET)
        self.clinician_token = self._login("clinician@example.test", CLINICIAN_SECRET)
        self.other_clinician_token = self._login("other-clinician@example.test", OTHER_CLINICIAN_SECRET)

    def tearDown(self):
        self.conn.close()
        self.app.close()
        self.temp.cleanup()

    def _login(self, email: str, secret: str) -> str:
        body = json.dumps({"email": email, "password": "correct horse battery", "totp_code": totp_now(secret)}).encode()
        _, _, payload = invoke(self.app, "POST", "/api/v1/auth/sessions", body, {"Content-Type": "application/json"})
        return json.loads(payload)["access_token"]

    def _auth(self, token: str) -> dict:
        return {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}

    def _register_patient_with_message(self, email: str, learning_consent: bool, text: str) -> tuple[str, str]:
        registration = json.dumps({"email": email, "password": "correct horse battery"}).encode()
        invoke(self.app, "POST", "/api/v1/auth/register", registration, {"Content-Type": "application/json"})
        _, _, payload = invoke(self.app, "POST", "/api/v1/auth/sessions", registration, {"Content-Type": "application/json"})
        token = json.loads(payload)["access_token"]
        auth = self._auth(token)
        invoke(self.app, "POST", "/api/v1/consents", b'{"purpose":"CARE","version":"1"}', auth)
        if learning_consent:
            invoke(self.app, "POST", "/api/v1/consents", b'{"purpose":"LEARNING","version":"1"}', auth)
        _, _, payload = invoke(self.app, "POST", "/api/v1/conversations", b"{}", auth)
        conversation_id = json.loads(payload)["id"]
        invoke(self.app, "POST", f"/api/v1/conversations/{conversation_id}/messages", json.dumps({"text": text}).encode(), auth)
        return token, conversation_id

    def test_only_consenting_patients_messages_are_sampled(self):
        self._register_patient_with_message("consenting@example.test", True, "Ma journee etait plutot calme")
        self._register_patient_with_message("nonconsenting@example.test", False, "Ma journee etait plutot calme aussi")

        status, _, payload = invoke(self.app, "POST", "/api/v1/admin/learning/sample", headers=self._auth(self.admin_token))
        self.assertEqual(status, "201 Created")
        self.assertEqual(json.loads(payload)["created"], 1)

    def test_sampling_is_idempotent_and_only_admin_can_trigger_it(self):
        self._register_patient_with_message("patient@example.test", True, "Ma journee etait calme")

        status, _, _ = invoke(self.app, "POST", "/api/v1/admin/learning/sample", headers=self._auth(self.clinician_token))
        self.assertEqual(status, "401 Unauthorized")

        invoke(self.app, "POST", "/api/v1/admin/learning/sample", headers=self._auth(self.admin_token))
        status, _, payload = invoke(self.app, "POST", "/api/v1/admin/learning/sample", headers=self._auth(self.admin_token))
        self.assertEqual(json.loads(payload)["created"], 0)

    def test_review_queue_never_exposes_patient_identity(self):
        self._register_patient_with_message("identifiable@example.test", True, "Contact me at me@example.test if needed")
        invoke(self.app, "POST", "/api/v1/admin/learning/sample", headers=self._auth(self.admin_token))

        status, _, payload = invoke(self.app, "GET", "/api/v1/clinician/learning/feedback", headers=self._auth(self.clinician_token))
        self.assertEqual(status, "200 OK")
        items = json.loads(payload)["items"]
        self.assertEqual(len(items), 1)
        self.assertNotIn("patient_id", items[0])
        self.assertNotIn("email", items[0])
        self.assertNotIn("identifiable@example.test", items[0]["anonymized_content"])
        self.assertIn("[REDACTED_EMAIL]", items[0]["anonymized_content"])

    def test_only_clinician_can_review_and_double_review_is_rejected(self):
        self._register_patient_with_message("patient2@example.test", True, "Ma journee etait calme")
        invoke(self.app, "POST", "/api/v1/admin/learning/sample", headers=self._auth(self.admin_token))
        _, _, payload = invoke(self.app, "GET", "/api/v1/clinician/learning/feedback", headers=self._auth(self.clinician_token))
        feedback_id = json.loads(payload)["items"][0]["id"]

        body = json.dumps({"decision": "APPROVED", "justification": "Représentatif et sûr pour l'entraînement."}).encode()
        status, _, _ = invoke(self.app, "POST", f"/api/v1/clinician/learning/feedback/{feedback_id}/review", body, self._auth(self.admin_token))
        self.assertEqual(status, "401 Unauthorized")

        status, _, payload = invoke(self.app, "POST", f"/api/v1/clinician/learning/feedback/{feedback_id}/review", body, self._auth(self.clinician_token))
        self.assertEqual(status, "200 OK")
        self.assertEqual(json.loads(payload)["review_status"], "APPROVED")

        status, _, _ = invoke(self.app, "POST", f"/api/v1/clinician/learning/feedback/{feedback_id}/review", body, self._auth(self.other_clinician_token))
        self.assertEqual(status, "401 Unauthorized")

    def test_dataset_creation_requires_approved_feedback_and_is_immutable_snapshot(self):
        status, _, _ = invoke(self.app, "POST", "/api/v1/admin/learning/datasets", headers=self._auth(self.admin_token))
        self.assertEqual(status, "401 Unauthorized")  # nothing approved yet

        self._register_patient_with_message("patient3@example.test", True, "Ma journee etait calme")
        invoke(self.app, "POST", "/api/v1/admin/learning/sample", headers=self._auth(self.admin_token))
        _, _, payload = invoke(self.app, "GET", "/api/v1/clinician/learning/feedback", headers=self._auth(self.clinician_token))
        feedback_id = json.loads(payload)["items"][0]["id"]
        body = json.dumps({"decision": "APPROVED", "justification": "OK pour le dataset."}).encode()
        invoke(self.app, "POST", f"/api/v1/clinician/learning/feedback/{feedback_id}/review", body, self._auth(self.clinician_token))

        status, _, payload = invoke(self.app, "POST", "/api/v1/admin/learning/datasets", headers=self._auth(self.admin_token))
        self.assertEqual(status, "201 Created")
        dataset = json.loads(payload)
        self.assertEqual(dataset["status"], "FINALIZED")
        self.assertEqual(dataset["item_count"], 1)

        # the same approved item cannot be swept into a second dataset
        status, _, _ = invoke(self.app, "POST", "/api/v1/admin/learning/datasets", headers=self._auth(self.admin_token))
        self.assertEqual(status, "401 Unauthorized")

    def test_model_version_requires_two_distinct_clinician_approvals_before_deploy(self):
        status, _, payload = invoke(
            self.app, "POST", "/api/v1/admin/learning/models",
            json.dumps({"kind": "EMOTION", "version": "emotion-classifier-dev-1", "metrics": {"test_accuracy": 0.69}}).encode(),
            self._auth(self.admin_token),
        )
        self.assertEqual(status, "201 Created")
        model_id = json.loads(payload)["id"]
        self.assertEqual(json.loads(payload)["status"], "PENDING_REVIEW")

        # clinicians can see pending models (needed to cast their approval) but admins cannot use the clinician path
        status, _, payload = invoke(self.app, "GET", "/api/v1/clinician/learning/models", headers=self._auth(self.clinician_token))
        self.assertEqual(status, "200 OK")
        self.assertEqual(len(json.loads(payload)["items"]), 1)
        status, _, _ = invoke(self.app, "GET", "/api/v1/clinician/learning/models", headers=self._auth(self.admin_token))
        self.assertEqual(status, "401 Unauthorized")

        # cannot deploy before approval
        status, _, _ = invoke(self.app, "POST", f"/api/v1/admin/learning/models/{model_id}/deploy", headers=self._auth(self.admin_token))
        self.assertEqual(status, "401 Unauthorized")

        decision_body = json.dumps({"decision": "APPROVED", "justification": "Métriques et portée revues, acceptable."}).encode()
        status, _, payload = invoke(self.app, "POST", f"/api/v1/clinician/learning/models/{model_id}/decisions", decision_body, self._auth(self.clinician_token))
        self.assertEqual(json.loads(payload)["status"], "PENDING_REVIEW")  # only one of two approvals so far

        # the same clinician cannot approve twice to fake a second reviewer
        status, _, _ = invoke(self.app, "POST", f"/api/v1/clinician/learning/models/{model_id}/decisions", decision_body, self._auth(self.clinician_token))
        self.assertEqual(status, "401 Unauthorized")

        status, _, payload = invoke(self.app, "POST", f"/api/v1/clinician/learning/models/{model_id}/decisions", decision_body, self._auth(self.other_clinician_token))
        self.assertEqual(json.loads(payload)["status"], "APPROVED")

        status, _, payload = invoke(self.app, "POST", f"/api/v1/admin/learning/models/{model_id}/deploy", headers=self._auth(self.admin_token))
        self.assertEqual(status, "200 OK")
        self.assertEqual(json.loads(payload)["status"], "DEPLOYED")

        status, _, payload = invoke(self.app, "POST", f"/api/v1/admin/learning/models/{model_id}/rollback", headers=self._auth(self.admin_token))
        self.assertEqual(json.loads(payload)["status"], "ROLLED_BACK")

    def test_single_rejection_blocks_a_model_version(self):
        _, _, payload = invoke(
            self.app, "POST", "/api/v1/admin/learning/models",
            json.dumps({"kind": "RISK", "version": "risk-dev-2"}).encode(),
            self._auth(self.admin_token),
        )
        model_id = json.loads(payload)["id"]
        body = json.dumps({"decision": "REJECTED", "justification": "Biais non acceptable détecté."}).encode()
        status, _, payload = invoke(self.app, "POST", f"/api/v1/clinician/learning/models/{model_id}/decisions", body, self._auth(self.clinician_token))
        self.assertEqual(json.loads(payload)["status"], "REJECTED")

        status, _, _ = invoke(self.app, "POST", f"/api/v1/admin/learning/models/{model_id}/deploy", headers=self._auth(self.admin_token))
        self.assertEqual(status, "401 Unauthorized")


if __name__ == "__main__":
    unittest.main()
