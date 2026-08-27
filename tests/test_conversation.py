from __future__ import annotations

import json
import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.config import Settings
from backend.app.http import application
from backend.app.policy import load_response_templates


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


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.settings = Settings(database_path=Path(self.temp.name) / "test.db", password_iterations=1_000)
        self.app = application(self.settings)
        registration = b'{"email":"chat@example.test","password":"correct horse battery"}'
        invoke(self.app, "POST", "/api/v1/auth/register", registration, {"Content-Type": "application/json"})
        _, _, payload = invoke(self.app, "POST", "/api/v1/auth/sessions", registration, {"Content-Type": "application/json"})
        token = json.loads(payload)["access_token"]
        self.auth = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        # onboarding grants CARE consent, same as the real patient app flow
        invoke(self.app, "POST", "/api/v1/consents", b'{"purpose":"CARE","version":"1"}', self.auth)

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def _start_conversation(self) -> str:
        status, _, payload = invoke(self.app, "POST", "/api/v1/conversations", b"{}", self.auth)
        self.assertEqual(status, "201 Created")
        return json.loads(payload)["id"]

    def test_conversation_requires_care_consent(self):
        registration = b'{"email":"noconsent@example.test","password":"correct horse battery"}'
        invoke(self.app, "POST", "/api/v1/auth/register", registration, {"Content-Type": "application/json"})
        _, _, payload = invoke(self.app, "POST", "/api/v1/auth/sessions", registration, {"Content-Type": "application/json"})
        auth = {"Content-Type": "application/json", "Authorization": "Bearer " + json.loads(payload)["access_token"]}
        status, _, _ = invoke(self.app, "POST", "/api/v1/conversations", b"{}", auth)
        self.assertEqual(status, "401 Unauthorized")

    def test_starting_conversation_twice_returns_the_same_one(self):
        first = self._start_conversation()
        second = self._start_conversation()
        self.assertEqual(first, second)

    def test_green_message_gets_a_templated_acknowledgment_not_a_safety_template(self):
        conversation_id = self._start_conversation()
        body = json.dumps({"text": "Ma journee etait plutot calme"}).encode()
        status, _, payload = invoke(self.app, "POST", f"/api/v1/conversations/{conversation_id}/messages", body, self.auth)
        self.assertEqual(status, "201 Created")
        result = json.loads(payload)
        self.assertEqual(result["patient_message"]["content"], "Ma journee etait plutot calme")
        # Assert the reply is actually one of the configured GREEN acknowledgments,
        # not merely "doesn't contain the RED phrase" -- that weaker check would
        # have missed the real bug where ordinary messages were coming back with
        # the ORANGE safety template instead (see ai.py's KeywordRiskModel fix).
        templates = load_response_templates(Path("config/policies/response-templates-v1.json"))
        self.assertIn(result["assistant_message"]["content"], templates.green_acknowledgments)
        self.assertEqual(result["patient_message"]["sequence_no"], 1)
        self.assertEqual(result["assistant_message"]["sequence_no"], 2)

    def test_red_message_gets_the_fixed_safety_template_not_the_llm(self):
        conversation_id = self._start_conversation()
        body = json.dumps({"text": "J'ai un plan suicidaire"}).encode()
        status, _, payload = invoke(self.app, "POST", f"/api/v1/conversations/{conversation_id}/messages", body, self.auth)
        self.assertEqual(status, "201 Created")
        result = json.loads(payload)
        self.assertIn("service d'urgence", result["assistant_message"]["content"])
        self.assertTrue(result["assistant_message"]["id"])

    def test_history_reflects_both_messages_in_order(self):
        conversation_id = self._start_conversation()
        invoke(self.app, "POST", f"/api/v1/conversations/{conversation_id}/messages", json.dumps({"text": "Bonjour"}).encode(), self.auth)
        status, _, payload = invoke(self.app, "GET", f"/api/v1/conversations/{conversation_id}/messages", headers=self.auth)
        self.assertEqual(status, "200 OK")
        items = json.loads(payload)["items"]
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["author_type"], "PATIENT")
        self.assertEqual(items[1]["author_type"], "ASSISTANT")

    def test_cannot_send_message_to_another_patients_conversation(self):
        conversation_id = self._start_conversation()
        registration = b'{"email":"other-patient@example.test","password":"correct horse battery"}'
        invoke(self.app, "POST", "/api/v1/auth/register", registration, {"Content-Type": "application/json"})
        _, _, payload = invoke(self.app, "POST", "/api/v1/auth/sessions", registration, {"Content-Type": "application/json"})
        other_auth = {"Content-Type": "application/json", "Authorization": "Bearer " + json.loads(payload)["access_token"]}
        invoke(self.app, "POST", "/api/v1/consents", b'{"purpose":"CARE","version":"1"}', other_auth)

        body = json.dumps({"text": "essai"}).encode()
        status, _, _ = invoke(self.app, "POST", f"/api/v1/conversations/{conversation_id}/messages", body, other_auth)
        self.assertEqual(status, "401 Unauthorized")
        status, _, _ = invoke(self.app, "GET", f"/api/v1/conversations/{conversation_id}/messages", headers=other_auth)
        self.assertEqual(status, "401 Unauthorized")

    def test_rejects_empty_and_oversized_messages(self):
        conversation_id = self._start_conversation()
        status, _, _ = invoke(self.app, "POST", f"/api/v1/conversations/{conversation_id}/messages", b'{"text":""}', self.auth)
        self.assertEqual(status, "401 Unauthorized")
        status, _, _ = invoke(self.app, "POST", f"/api/v1/conversations/{conversation_id}/messages", json.dumps({"text": "x" * 8001}).encode(), self.auth)
        self.assertEqual(status, "401 Unauthorized")


if __name__ == "__main__":
    unittest.main()
