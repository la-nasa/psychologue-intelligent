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


class AdminConsoleTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.settings = Settings(database_path=Path(self.temp.name) / "test.db", password_iterations=1_000)
        self.app = application(self.settings)
        self.conn = connect(self.settings.database_path)
        service = AuthService(self.conn, self.settings)

        self.patient_id = service.register_patient("patient@example.test", "correct horse battery", "seed")
        self.clinician_id = service.provision_privileged_user("clinician@example.test", "correct horse battery", "CLINICIAN", CLINICIAN_SECRET, "seed")
        service.provision_privileged_user("admin@example.test", "correct horse battery", "ADMIN", ADMIN_SECRET, "seed")

        self.admin_token = self._login("admin@example.test", ADMIN_SECRET)
        self.clinician_token = self._login("clinician@example.test", CLINICIAN_SECRET)

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

    def test_only_admin_can_list_users(self):
        status, _, _ = invoke(self.app, "GET", "/api/v1/admin/users", headers=self._auth(self.clinician_token))
        self.assertEqual(status, "401 Unauthorized")

    def test_list_users_filters_by_role_and_hides_sensitive_fields(self):
        status, _, payload = invoke(self.app, "GET", "/api/v1/admin/users?role=PATIENT", headers=self._auth(self.admin_token))
        self.assertEqual(status, "200 OK")
        items = json.loads(payload)["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["email"], "patient@example.test")
        self.assertNotIn("password_hash", items[0])
        self.assertNotIn("mfa_secret", items[0])

        status, _, payload = invoke(self.app, "GET", "/api/v1/admin/users?role=CLINICIAN", headers=self._auth(self.admin_token))
        self.assertEqual(status, "200 OK")
        items = json.loads(payload)["items"]
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["mfa_enabled"])

    def test_list_users_rejects_invalid_role(self):
        status, _, _ = invoke(self.app, "GET", "/api/v1/admin/users?role=NOT_A_ROLE", headers=self._auth(self.admin_token))
        self.assertEqual(status, "401 Unauthorized")

    def test_relationship_lifecycle_visible_in_listing(self):
        body = json.dumps({"patient_id": self.patient_id, "clinician_id": self.clinician_id}).encode()
        status, _, payload = invoke(self.app, "POST", "/api/v1/admin/relationships", body, self._auth(self.admin_token))
        self.assertEqual(status, "201 Created")
        relationship_id = json.loads(payload)["id"]

        status, _, payload = invoke(self.app, "GET", "/api/v1/admin/relationships?status=ACTIVE", headers=self._auth(self.admin_token))
        self.assertEqual(status, "200 OK")
        items = json.loads(payload)["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["patient_email"], "patient@example.test")
        self.assertEqual(items[0]["clinician_email"], "clinician@example.test")

        invoke(self.app, "POST", f"/api/v1/admin/relationships/{relationship_id}/end", headers=self._auth(self.admin_token))
        _, _, payload = invoke(self.app, "GET", "/api/v1/admin/relationships?status=ACTIVE", headers=self._auth(self.admin_token))
        self.assertEqual(json.loads(payload)["items"], [])
        _, _, payload = invoke(self.app, "GET", "/api/v1/admin/relationships?status=ENDED", headers=self._auth(self.admin_token))
        self.assertEqual(len(json.loads(payload)["items"]), 1)

    def test_clinician_cannot_list_relationships(self):
        status, _, _ = invoke(self.app, "GET", "/api/v1/admin/relationships", headers=self._auth(self.clinician_token))
        self.assertEqual(status, "401 Unauthorized")


if __name__ == "__main__":
    unittest.main()
