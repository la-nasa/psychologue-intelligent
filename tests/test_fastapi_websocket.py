from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.config import Settings
from backend.app.db import connect, migrate
from backend.app.auth import AuthService
from backend.app.ai import TemplatedSupportiveResponder


class FastAPIWebSocketTests(unittest.TestCase):
    def test_authenticated_socket_smoke(self):
        try:
            from fastapi.testclient import TestClient
            from backend.app.fastapi_app import create_app
        except ImportError:
            self.skipTest("realtime extra not installed")
        with TemporaryDirectory() as directory:
            settings = Settings(database_path=Path(directory) / "test.db", password_iterations=1_000)
            conn = connect(settings.database_path); migrate(conn)
            auth = AuthService(conn, settings)
            patient = auth.register_patient("socket@example.test", "correct horse battery", "test")
            auth.grant_consent(patient, "CARE", "v1", "test")
            token = auth.authenticate("socket@example.test", "correct horse battery", "test")
            conversation = __import__("backend.app.conversation", fromlist=["get_or_create_active_conversation"]).get_or_create_active_conversation(conn, patient, "test")
            conn.close()
            with TestClient(create_app(settings)) as client:
                with client.websocket_connect(f"/ws/conversations/{conversation['id']}?token={token}") as socket:
                    socket.send_json({"text": "Bonjour"})
                    self.assertEqual(socket.receive_json()["type"], "started")
                    types = []
                    while True:
                        message = socket.receive_json(); types.append(message["type"])
                        if message["type"] == "completed":
                            break
                    self.assertIn("completed", types)


if __name__ == "__main__":
    unittest.main()
