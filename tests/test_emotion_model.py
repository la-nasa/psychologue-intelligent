from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.ai import KeywordRiskModel
from backend.app.auth import AuthService
from backend.app.config import Settings
from backend.app.db import connect, migrate
from backend.app.emotion import TfidfLogisticEmotionModel, top_prediction
from backend.app.notifications import LogNotificationProvider
from backend.app.pipeline import handle_incoming_message
from backend.app.policy import load_crisis_policy, load_crisis_rules

ARTIFACT_PATH = Path("ml/artifacts/emotion-classifier-v1.json")


class FailingEmotionModel:
    version = "failing-dev-1"
    def predict(self, text: str) -> dict[str, float]:
        raise RuntimeError("model backend unavailable")


@unittest.skipUnless(ARTIFACT_PATH.exists(), "run ml/train_emotion_classifier.py first")
class EmotionModelTests(unittest.TestCase):
    def setUp(self):
        self.model = TfidfLogisticEmotionModel(ARTIFACT_PATH)

    def test_distribution_sums_to_one(self):
        distribution = self.model.predict("I am so happy today, this is wonderful news!")
        self.assertAlmostEqual(sum(distribution.values()), 1.0, places=6)
        self.assertEqual(set(distribution.keys()), set(self.model.labels))

    def test_confident_joy_example_is_recognized(self):
        prediction = top_prediction(self.model, "I am so happy today, this is wonderful news!")
        self.assertEqual(prediction.label, "joy")
        self.assertGreater(prediction.confidence, 0.3)

    def test_empty_text_does_not_crash(self):
        distribution = self.model.predict("")
        self.assertAlmostEqual(sum(distribution.values()), 1.0, places=6)

    def test_out_of_vocabulary_text_does_not_crash(self):
        distribution = self.model.predict("asdkjhaskjdh qwoeiuqwoe zzxczxc")
        self.assertAlmostEqual(sum(distribution.values()), 1.0, places=6)


class EmotionObservabilityIsNeverDecisiveTests(unittest.TestCase):
    """The emotion signal must be recorded for review but must never influence
    the crisis decision, and a failure in it must never break the pipeline
    that has no dependency on it (Section 14: fail-safe, never a single
    source of truth for a safety-critical outcome)."""

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.settings = Settings(database_path=Path(self.temp.name) / "test.db", password_iterations=1_000)
        self.conn = connect(self.settings.database_path)
        migrate(self.conn)
        self.patient_id = AuthService(self.conn, self.settings).register_patient(
            "emotion@example.test", "correct horse battery", "seed",
        )
        self.policy = load_crisis_policy(Path("config/policies/crisis-policy-v1.json"))
        self.rules = load_crisis_rules(Path("config/policies/crisis-rules-v1.json"))

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def test_failing_emotion_model_does_not_break_the_crisis_pipeline(self):
        outcome = handle_incoming_message(
            self.conn, self.patient_id, "plan suicidaire", "msg-1", KeywordRiskModel(),
            self.policy, self.rules, LogNotificationProvider(), "req-1",
            emotion_model=FailingEmotionModel(),
        )
        self.assertEqual(outcome.decision.level, "RED")
        row = self.conn.execute("SELECT emotion_label FROM risk_assessments").fetchone()
        self.assertIsNone(row["emotion_label"])

    @unittest.skipUnless(ARTIFACT_PATH.exists(), "run ml/train_emotion_classifier.py first")
    def test_emotion_prediction_is_recorded_without_affecting_the_decision(self):
        emotion_model = TfidfLogisticEmotionModel(ARTIFACT_PATH)
        outcome = handle_incoming_message(
            self.conn, self.patient_id, "Ma journee etait plutot calme", "msg-2", KeywordRiskModel(),
            self.policy, self.rules, LogNotificationProvider(), "req-2",
            emotion_model=emotion_model,
        )
        self.assertEqual(outcome.decision.level, "GREEN")
        row = self.conn.execute("SELECT emotion_label,emotion_model_version FROM risk_assessments").fetchone()
        self.assertIn(row["emotion_label"], emotion_model.labels)
        self.assertEqual(row["emotion_model_version"], emotion_model.version)


if __name__ == "__main__":
    unittest.main()
