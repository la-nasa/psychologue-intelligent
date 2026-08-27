from __future__ import annotations

import json
import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.ai import KeywordRiskModel
from backend.app.auth import AuthService, utc_now
from backend.app.config import Settings
from backend.app.crisis import CrisisDetector
from backend.app.db import connect, migrate
from backend.app.notifications import (
    MAX_ATTEMPTS,
    MAX_TOTAL_ATTEMPTS,
    LogNotificationProvider,
    retry_pending_notifications,
)
from backend.app.pipeline import handle_incoming_message
from backend.app.policy import (
    CrisisPolicy,
    load_crisis_policy,
    load_crisis_rules,
)

POLICY_PATH = Path("config/policies/crisis-policy-v1.json")
RULES_PATH = Path("config/policies/crisis-rules-v1.json")
DEFAULT_POLICY = load_crisis_policy(POLICY_PATH)
DEFAULT_RULES = load_crisis_rules(RULES_PATH)


class BrokenModel:
    version = "broken-dev-1"
    def predict(self, text: str) -> tuple[float, float]:
        raise RuntimeError("model backend unavailable")


class OverconfidentSafeModel:
    """A model that always claims perfect safety; must never override the rule engine."""
    version = "overconfident-dev-1"
    def predict(self, text: str) -> tuple[float, float]:
        return 0.0, 1.0


class PolicyLoadingTests(unittest.TestCase):
    def _write(self, tmp: Path, data: dict) -> Path:
        path = tmp / "policy.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def valid_policy_dict(self) -> dict:
        return json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    def test_rejects_inverted_thresholds(self):
        with TemporaryDirectory() as tmp:
            data = self.valid_policy_dict()
            data["alert_thresholds"]["orange_score"] = 0.9
            data["alert_thresholds"]["red_score"] = 0.5
            with self.assertRaises(ValueError):
                load_crisis_policy(self._write(Path(tmp), data))

    def test_rejects_unapproved_policy_outside_development(self):
        with TemporaryDirectory() as tmp:
            data = self.valid_policy_dict()
            data["environment"] = "production"
            with self.assertRaises(ValueError):
                load_crisis_policy(self._write(Path(tmp), data))

    def test_accepts_approved_policy_outside_development(self):
        with TemporaryDirectory() as tmp:
            data = self.valid_policy_dict()
            data["environment"] = "production"
            data["approved_by"] = "clinician-lead"
            data["approved_at"] = "2026-01-01T00:00:00+00:00"
            policy = load_crisis_policy(self._write(Path(tmp), data))
            self.assertEqual(policy.approved_by, "clinician-lead")

    def test_rejects_missing_file(self):
        with self.assertRaises(ValueError):
            load_crisis_policy(Path("does/not/exist.json"))


class CrisisDetectorFailSafeTests(unittest.TestCase):
    def test_model_failure_falls_back_conservatively_never_crashes(self):
        detector = CrisisDetector(DEFAULT_POLICY, DEFAULT_RULES)
        decision = detector.evaluate("Une journée plutôt calme", BrokenModel())
        self.assertFalse(decision.model_available)
        self.assertIn("model_unavailable", decision.reasons)
        self.assertEqual(decision.level, "ORANGE")  # degraded confidence forces caution, not GREEN

    def test_rule_engine_cannot_be_overridden_by_an_overconfident_model(self):
        detector = CrisisDetector(DEFAULT_POLICY, DEFAULT_RULES)
        decision = detector.evaluate("J'ai un plan suicidaire", OverconfidentSafeModel())
        self.assertEqual(decision.level, "RED")
        self.assertTrue(decision.model_available)

    def test_accented_and_case_variants_are_still_detected(self):
        detector = CrisisDetector(DEFAULT_POLICY, DEFAULT_RULES)
        decision = detector.evaluate("Je suis DÉSESPÉRÉ", KeywordRiskModel())
        self.assertIn(decision.level, ("ORANGE", "RED"))

    def test_confident_safe_text_with_available_model_is_green(self):
        detector = CrisisDetector(DEFAULT_POLICY, DEFAULT_RULES)
        decision = detector.evaluate("Ma séance de sport s'est bien passée", OverconfidentSafeModel())
        self.assertEqual(decision.level, "GREEN")


class PipelineIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.settings = Settings(database_path=Path(self.temp.name) / "test.db", password_iterations=1_000)
        self.conn = connect(self.settings.database_path)
        migrate(self.conn)
        self.patient_id = AuthService(self.conn, self.settings).register_patient(
            "pipeline@example.test", "correct horse battery", "seed"
        )
        self.provider = LogNotificationProvider()

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def test_red_message_opens_alert_and_records_the_full_trail(self):
        outcome = handle_incoming_message(
            self.conn, self.patient_id, "J'ai un plan suicidaire", "msg-1",
            KeywordRiskModel(), DEFAULT_POLICY, DEFAULT_RULES, self.provider, "req-1",
        )
        self.assertEqual(outcome.decision.level, "RED")
        self.assertTrue(outcome.alert_created)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM risk_assessments").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM crisis_events").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM alerts").fetchone()[0], 1)
        # no channel configured in the default policy -> honestly recorded as skipped, never faked as sent
        self.assertEqual(len(outcome.notifications), 1)
        self.assertEqual(outcome.notifications[0].status, "SKIPPED_NO_CHANNEL")

    def test_green_message_never_opens_an_alert(self):
        outcome = handle_incoming_message(
            self.conn, self.patient_id, "Ma séance de sport s'est bien passée", "msg-2",
            OverconfidentSafeModel(), DEFAULT_POLICY, DEFAULT_RULES, self.provider, "req-2",
        )
        self.assertEqual(outcome.decision.level, "GREEN")
        self.assertIsNone(outcome.alert)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM alerts").fetchone()[0], 0)

    def test_retried_message_reference_does_not_duplicate_alert_or_notification(self):
        for _ in range(2):
            handle_incoming_message(
                self.conn, self.patient_id, "plan suicidaire", "msg-3",
                KeywordRiskModel(), DEFAULT_POLICY, DEFAULT_RULES, self.provider, "req-3",
            )
        self.assertEqual(self.conn.execute("SELECT count(*) FROM alerts").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM notifications").fetchone()[0], 1)

    def test_notification_uses_configured_channel_when_present(self):
        policy = CrisisPolicy(
            version=DEFAULT_POLICY.version, country=DEFAULT_POLICY.country, environment="development",
            red_score=DEFAULT_POLICY.red_score, orange_score=DEFAULT_POLICY.orange_score,
            orange_confidence_floor=DEFAULT_POLICY.orange_confidence_floor,
            response_sla_minutes=DEFAULT_POLICY.response_sla_minutes,
            human_review_required=DEFAULT_POLICY.human_review_required,
            notification_channels=("clinician-console",), emergency_contacts=(),
            approved_by=None, approved_at=None,
        )
        outcome = handle_incoming_message(
            self.conn, self.patient_id, "plan suicidaire", "msg-4",
            KeywordRiskModel(), policy, DEFAULT_RULES, self.provider, "req-4",
        )
        self.assertEqual(len(outcome.notifications), 1)
        self.assertEqual(outcome.notifications[0].status, "SENT")
        self.assertIsNotNone(outcome.notifications[0].provider_ref)


class FlakyProvider:
    """Fails every call until (and including) call number `succeed_on`; never
    succeeds if `succeed_on` is None. Used to simulate a real channel outage
    followed by recovery, without any real network dependency."""

    def __init__(self, succeed_on: int | None = None):
        self.succeed_on = succeed_on
        self.calls = 0

    def send(self, channel: str, target: str, payload: dict) -> str:
        self.calls += 1
        if self.succeed_on is not None and self.calls >= self.succeed_on:
            return f"flaky-ref-{self.calls}"
        raise RuntimeError("simulated provider outage")


class NotificationRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.settings = Settings(database_path=Path(self.temp.name) / "test.db", password_iterations=1_000)
        self.conn = connect(self.settings.database_path)
        migrate(self.conn)
        self.patient_id = AuthService(self.conn, self.settings).register_patient(
            "retry@example.test", "correct horse battery", "seed"
        )
        self.policy = CrisisPolicy(
            version=DEFAULT_POLICY.version, country=DEFAULT_POLICY.country, environment="development",
            red_score=DEFAULT_POLICY.red_score, orange_score=DEFAULT_POLICY.orange_score,
            orange_confidence_floor=DEFAULT_POLICY.orange_confidence_floor,
            response_sla_minutes=DEFAULT_POLICY.response_sla_minutes,
            human_review_required=DEFAULT_POLICY.human_review_required,
            notification_channels=("clinician-console",), emergency_contacts=(),
            approved_by=None, approved_at=None,
        )

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def _create_failed_alert(self, provider) -> None:
        handle_incoming_message(
            self.conn, self.patient_id, "plan suicidaire", "msg-retry-1",
            KeywordRiskModel(), self.policy, DEFAULT_RULES, provider, "req-retry-seed",
        )

    def test_failed_notification_past_backoff_window_is_retried_and_can_succeed(self):
        always_failing = FlakyProvider(succeed_on=None)
        self._create_failed_alert(always_failing)
        row = self.conn.execute("SELECT * FROM notifications").fetchone()
        self.assertEqual(row["delivery_status"], "FAILED")
        self.assertEqual(row["attempt_count"], MAX_ATTEMPTS)
        self.assertIsNotNone(row["next_retry_at"])

        # backoff window has not elapsed yet: retrying "now" must change nothing
        outcomes = retry_pending_notifications(self.conn, always_failing, "req-retry-too-soon")
        self.assertEqual(outcomes, [])

        # once the window has passed, a now-healthy provider succeeds
        future = utc_now() + timedelta(hours=1)
        succeeding = FlakyProvider(succeed_on=1)
        outcomes = retry_pending_notifications(self.conn, succeeding, "req-retry-recovered", now=future)
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].status, "SENT")
        row = self.conn.execute("SELECT * FROM notifications").fetchone()
        self.assertEqual(row["delivery_status"], "SENT")
        self.assertIsNone(row["next_retry_at"])

    def test_notification_failing_past_max_total_attempts_is_dead_lettered_not_retried_forever(self):
        always_failing = FlakyProvider(succeed_on=None)
        self._create_failed_alert(always_failing)

        moment = utc_now() + timedelta(days=1)
        for _ in range(MAX_TOTAL_ATTEMPTS - MAX_ATTEMPTS):
            outcomes = retry_pending_notifications(self.conn, always_failing, "req-retry-loop", now=moment)
            self.assertEqual(len(outcomes), 1)
            moment += timedelta(days=1)

        row = self.conn.execute("SELECT * FROM notifications").fetchone()
        self.assertEqual(row["delivery_status"], "FAILED")
        self.assertEqual(row["attempt_count"], MAX_TOTAL_ATTEMPTS)
        self.assertIsNone(row["next_retry_at"])  # dead-lettered: no further schedule

        # a dead-lettered row is never picked up again, no matter how far in the future
        outcomes = retry_pending_notifications(
            self.conn, always_failing, "req-retry-after-dead-letter", now=moment + timedelta(days=365)
        )
        self.assertEqual(outcomes, [])


if __name__ == "__main__":
    unittest.main()
