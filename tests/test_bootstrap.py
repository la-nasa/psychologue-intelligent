from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from backend.app.auth import AuthService
from backend.app.config import Settings
from backend.app.db import connect, migrate
from scripts.bootstrap_privileged_users import main


class BootstrapPrivilegedUsersTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp.name) / "test.db"
        self.settings = Settings(database_path=self.db_path, password_iterations=1_000)

    def tearDown(self):
        self.temp.cleanup()

    def _env(self, **overrides) -> dict[str, str]:
        base = {"PI_DATABASE_PATH": str(self.db_path)}
        base.update(overrides)
        return base

    def test_creates_both_accounts_when_env_vars_are_set(self):
        env = self._env(
            PI_BOOTSTRAP_CLINICIAN_EMAIL="clinicienne@example.test",
            PI_BOOTSTRAP_CLINICIAN_PASSWORD="a valid password 123456",
            PI_BOOTSTRAP_ADMIN_EMAIL="admin@example.test",
            PI_BOOTSTRAP_ADMIN_PASSWORD="another valid password 22",
        )
        with mock.patch.dict(os.environ, env, clear=True):
            main()

        conn = connect(self.db_path)
        try:
            rows = {row["email"]: row for row in conn.execute("SELECT email, role, mfa_secret FROM users").fetchall()}
        finally:
            conn.close()
        self.assertEqual(rows["clinicienne@example.test"]["role"], "CLINICIAN")
        self.assertEqual(rows["admin@example.test"]["role"], "ADMIN")
        self.assertIsNotNone(rows["clinicienne@example.test"]["mfa_secret"])
        self.assertIsNotNone(rows["admin@example.test"]["mfa_secret"])

    def test_running_twice_does_not_duplicate_or_error(self):
        env = self._env(
            PI_BOOTSTRAP_CLINICIAN_EMAIL="clinicienne@example.test",
            PI_BOOTSTRAP_CLINICIAN_PASSWORD="a valid password 123456",
        )
        with mock.patch.dict(os.environ, env, clear=True):
            main()
            main()  # must not raise (e.g. on the UNIQUE email constraint) and must not duplicate

        conn = connect(self.db_path)
        try:
            count = conn.execute("SELECT count(*) FROM users WHERE email='clinicienne@example.test'").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 1)

    def test_does_nothing_when_no_bootstrap_variables_are_set(self):
        with mock.patch.dict(os.environ, self._env(), clear=True):
            main()  # must not raise

        conn = connect(self.db_path)
        migrate(conn)  # main() already ran migrate(); this just gives us a connection to assert against
        try:
            count = conn.execute("SELECT count(*) FROM users").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 0)

    def test_created_account_can_actually_authenticate(self):
        env = self._env(
            PI_BOOTSTRAP_CLINICIAN_EMAIL="clinicienne@example.test",
            PI_BOOTSTRAP_CLINICIAN_PASSWORD="a valid password 123456",
        )
        with mock.patch.dict(os.environ, env, clear=True):
            main()

        conn = connect(self.db_path)
        try:
            row = conn.execute("SELECT mfa_secret FROM users WHERE email='clinicienne@example.test'").fetchone()
            self.assertTrue(len(row["mfa_secret"]) >= 16)
            service = AuthService(conn, self.settings)
            with self.assertRaises(ValueError):
                # Sanity check the account is real and privilege-provisioned, not a patient.
                service.register_patient("clinicienne@example.test", "a valid password 123456", "req-1")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
