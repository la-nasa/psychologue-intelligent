"""Concurrency and resilience tests (master prompt Sections 8/17 Niveaux 8-9).

wsgiref's default server is single-threaded, so these scenarios never occur
under `python -m backend.app` or `scripts/dev_server.py` as configured today.
They matter anyway: any real deployment (gunicorn --threads, waitress, a
threading WSGI mixin) is one config change away, and the failure mode found
here (every request 500ing except by luck of thread id) would be a total
outage of the crisis pipeline, not a cosmetic bug.
"""
from __future__ import annotations

import json
import threading
import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.config import Settings
from backend.app.http import application


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


class ConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.settings = Settings(database_path=Path(self.temp.name) / "test.db", password_iterations=1_000)
        self.app = application(self.settings)

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def test_health_ready_survives_concurrent_calls_from_different_threads(self):
        """Regression guard for the connection-thread-affinity bug: a shared
        sqlite3.Connection (check_same_thread=True by default) raises
        ProgrammingError the moment a second thread touches it. Each request
        must open and close its own connection."""
        results: dict[int, str] = {}

        def call(index: int) -> None:
            status, _, _ = invoke(self.app, "GET", "/health/ready")
            results[index] = status

        threads = [threading.Thread(target=call, args=(i,)) for i in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(set(results.values()), {"200 OK"})
        self.assertEqual(len(results), 20)

    def test_concurrent_registrations_of_distinct_accounts_all_succeed(self):
        # Stay under the per-IP registration rate limit (10/hour, see http.py):
        # this test is about connection concurrency, not rate limiting -- that
        # is covered separately in test_security.py::RateLimitingTests.
        results: dict[int, str] = {}

        def register(index: int) -> None:
            body = json.dumps({"email": f"concurrent{index}@example.test", "password": "correct horse battery"}).encode()
            status, _, _ = invoke(self.app, "POST", "/api/v1/auth/register", body, {"Content-Type": "application/json"})
            results[index] = status

        threads = [threading.Thread(target=register, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(set(results.values()), {"201 Created"})

    def test_concurrent_registration_with_the_same_email_only_one_succeeds(self):
        """The UNIQUE constraint on users.email is the real safeguard here, not
        application-level locking -- this proves it holds under real concurrent
        writers, not just sequential calls."""
        results: dict[int, str] = {}
        body = json.dumps({"email": "same-email@example.test", "password": "correct horse battery"}).encode()

        def register(index: int) -> None:
            status, _, _ = invoke(self.app, "POST", "/api/v1/auth/register", body, {"Content-Type": "application/json"})
            results[index] = status

        threads = [threading.Thread(target=register, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        statuses = list(results.values())
        self.assertEqual(statuses.count("201 Created"), 1)
        self.assertEqual(statuses.count("401 Unauthorized"), 7)


class CrashRecoveryTests(unittest.TestCase):
    """Simulates the process dying mid-write (kill -9 / power loss), not a
    clean shutdown. WAL mode exists precisely so this doesn't corrupt data."""

    def test_wal_mode_recovers_committed_writes_after_an_unclean_connection_close(self):
        from backend.app.auth import AuthService
        from backend.app.db import connect, migrate

        # ignore_cleanup_errors: on Windows, SQLite's WAL side files (-wal/-shm)
        # can remain briefly locked by the OS after an unclean close, which is
        # exactly the scenario under test -- that timing quirk shouldn't fail
        # the test itself, only the temp-directory teardown.
        temp = TemporaryDirectory(ignore_cleanup_errors=True)
        try:
            settings = Settings(database_path=Path(temp.name) / "test.db", password_iterations=1_000)
            conn = connect(settings.database_path)
            migrate(conn)
            AuthService(conn, settings).register_patient("crash@example.test", "correct horse battery", "seed")
            # isolation_level=None means autocommit: this row is already durably
            # committed. Dropping the reference without calling close() simulates
            # a process crash rather than a clean shutdown.
            del conn

            reconnected = connect(settings.database_path)
            row = reconnected.execute("SELECT email FROM users WHERE email=?", ("crash@example.test",)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["email"], "crash@example.test")
            reconnected.close()
        finally:
            temp.cleanup()


if __name__ == "__main__":
    unittest.main()
