from __future__ import annotations

import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.ai import KeywordRiskModel, TemplatedSupportiveResponder
from backend.app.auth import AuthService
from backend.app.config import Settings
from backend.app.conversation import get_or_create_active_conversation, send_message
from backend.app.db import connect, migrate
from backend.app.local_llm import LocalGenerativeResponder, _build_messages
from backend.app.notifications import LogNotificationProvider
from backend.app.personalization import build_context, phq9_severity_band
from backend.app.policy import load_crisis_policy, load_crisis_rules, load_response_templates

DEFAULT_POLICY = load_crisis_policy(Path("config/policies/crisis-policy-v1.json"))
DEFAULT_RULES = load_crisis_rules(Path("config/policies/crisis-rules-v1.json"))
DEFAULT_TEMPLATES = load_response_templates(Path("config/policies/response-templates-v1.json"))


class FakeEngine:
    """Stands in for llama_cpp.Llama: records what it was called with and
    returns a scripted reply, so tests never need the real dependency."""

    def __init__(self, reply: str = "Merci de partager cela avec moi.", raise_error: bool = False):
        self.reply = reply
        self.raise_error = raise_error
        self.calls: list[list[dict[str, str]]] = []

    def create_chat_completion(self, messages, max_tokens, temperature):
        self.calls.append(messages)
        if self.raise_error:
            raise RuntimeError("simulated model failure")
        return {"choices": [{"message": {"content": self.reply}}]}


class PromptConstructionTests(unittest.TestCase):
    def test_personalization_is_woven_into_the_system_message_not_invented_facts(self):
        context = {"display_name": "Alex", "phq9_severity_band": "modérée", "recent_messages": []}
        messages = _build_messages("Je me sens un peu mieux aujourd'hui", context)
        system = messages[0]["content"]
        self.assertIn("Alex", system)
        self.assertIn("modérée", system)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[-1], {"role": "user", "content": "Je me sens un peu mieux aujourd'hui"})

    def test_no_context_still_produces_a_valid_minimal_prompt(self):
        messages = _build_messages("Bonjour", None)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[-1], {"role": "user", "content": "Bonjour"})

    def test_recent_conversation_history_is_carried_in_chronological_order(self):
        context = {
            "recent_messages": [
                {"author_type": "PATIENT", "content": "Bonjour"},
                {"author_type": "ASSISTANT", "content": "Bonjour, comment allez-vous ?"},
                {"author_type": "PATIENT", "content": "Un peu fatigué"},  # this is "the current message" duplicate
            ]
        }
        messages = _build_messages("Un peu fatigué", context)
        # The last recent_messages entry is the current message itself (already
        # appended once by conversation.py's own insert before this is built) --
        # it must not appear twice.
        roles_and_content = [(m["role"], m["content"]) for m in messages[1:]]
        self.assertEqual(roles_and_content, [
            ("user", "Bonjour"),
            ("assistant", "Bonjour, comment allez-vous ?"),
            ("user", "Un peu fatigué"),
        ])


class Phq9SeverityBandTests(unittest.TestCase):
    def test_bands_match_the_published_phq9_thresholds(self):
        self.assertEqual(phq9_severity_band(0), "minimale")
        self.assertEqual(phq9_severity_band(4), "minimale")
        self.assertEqual(phq9_severity_band(5), "légère")
        self.assertEqual(phq9_severity_band(9), "légère")
        self.assertEqual(phq9_severity_band(10), "modérée")
        self.assertEqual(phq9_severity_band(15), "modérément sévère")
        self.assertEqual(phq9_severity_band(20), "sévère")
        self.assertEqual(phq9_severity_band(27), "sévère")

    def test_out_of_range_score_defensively_falls_back_to_the_top_band(self):
        # total_score is constrained to 0-27 by the phq9_assessments table's own
        # CHECK constraint, so this should be unreachable in practice -- but the
        # function must still degrade sanely rather than return nothing for any
        # caller that doesn't go through that table (defensive, not dead code).
        self.assertEqual(phq9_severity_band(99), "sévère")


class LocalGenerativeResponderTests(unittest.TestCase):
    def test_generates_via_the_injected_engine_and_lazy_loads_only_once(self):
        engine = FakeEngine(reply="Je t'entends, et je suis là pour en parler.")
        load_count = {"n": 0}

        def factory(model_path, context_tokens):
            load_count["n"] += 1
            return engine

        responder = LocalGenerativeResponder(Path("fake.gguf"), fallback=TemplatedSupportiveResponder(("ack",)), engine_factory=factory)
        first = responder.generate("Bonjour")
        second = responder.generate("Encore une fois")
        self.assertEqual(first, "Je t'entends, et je suis là pour en parler.")
        self.assertEqual(second, "Je t'entends, et je suis là pour en parler.")
        self.assertEqual(load_count["n"], 1)  # loaded once, reused across calls
        self.assertEqual(len(engine.calls), 2)

    def test_falls_back_to_the_templated_responder_when_the_engine_raises(self):
        engine = FakeEngine(raise_error=True)
        fallback = TemplatedSupportiveResponder(("Merci de me l'avoir partagé.",))
        responder = LocalGenerativeResponder(Path("fake.gguf"), fallback=fallback, engine_factory=lambda p, c: engine)
        reply = responder.generate("Bonjour")
        self.assertEqual(reply, "Merci de me l'avoir partagé.")

    def test_falls_back_when_the_model_returns_an_empty_reply(self):
        engine = FakeEngine(reply="   ")
        fallback = TemplatedSupportiveResponder(("Merci de me l'avoir partagé.",))
        responder = LocalGenerativeResponder(Path("fake.gguf"), fallback=fallback, engine_factory=lambda p, c: engine)
        reply = responder.generate("Bonjour")
        self.assertEqual(reply, "Merci de me l'avoir partagé.")

    def test_falls_back_when_the_engine_itself_fails_to_load(self):
        def failing_factory(model_path, context_tokens):
            raise OSError("model file not found")

        fallback = TemplatedSupportiveResponder(("Merci de me l'avoir partagé.",))
        responder = LocalGenerativeResponder(Path("missing.gguf"), fallback=fallback, engine_factory=failing_factory)
        reply = responder.generate("Bonjour")
        self.assertEqual(reply, "Merci de me l'avoir partagé.")

    def test_concurrent_calls_are_serialized_not_interleaved(self):
        # A real llama.cpp context is not safe for concurrent calls from
        # multiple threads; the lock must genuinely serialize access, not just
        # exist decoratively. A slow fake engine plus a shared mutable counter
        # would catch a broken/missing lock as a race, not just by inspection.
        order: list[str] = []

        class SlowEngine:
            def create_chat_completion(self, messages, max_tokens, temperature):
                order.append("start")
                time.sleep(0.05)
                order.append("end")
                return {"choices": [{"message": {"content": "ok"}}]}

        responder = LocalGenerativeResponder(Path("fake.gguf"), fallback=TemplatedSupportiveResponder(("ack",)), engine_factory=lambda p, c: SlowEngine())
        threads = [threading.Thread(target=responder.generate, args=(f"msg-{i}",)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # Serialized calls must alternate start/end/start/end/...; an
        # interleaved (unsafe) run would show start,start,... before any end.
        self.assertEqual(order, ["start", "end"] * 4)


class PersonalizationContextIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(ignore_cleanup_errors=True)
        self.settings = Settings(database_path=Path(self.temp.name) / "test.db", password_iterations=1_000)
        self.conn = connect(self.settings.database_path)
        migrate(self.conn)
        self.auth = AuthService(self.conn, self.settings)
        self.patient_id = self.auth.register_patient("context@example.test", "correct horse battery", "seed")
        self.auth.grant_consent(self.patient_id, "CARE", "v1", "seed")
        self.auth.save_profile(self.patient_id, "Alex", "seed")

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def test_context_includes_the_saved_display_name(self):
        conversation = get_or_create_active_conversation(self.conn, self.patient_id, "req-1")
        context = build_context(self.conn, self.patient_id, conversation["id"])
        self.assertEqual(context["display_name"], "Alex")
        self.assertIsNone(context["phq9_severity_band"])  # no PHQ-9 submitted yet

    def test_context_missing_profile_degrades_gracefully_instead_of_raising(self):
        other_patient = self.auth.register_patient("noprofile@example.test", "correct horse battery", "seed")
        self.auth.grant_consent(other_patient, "CARE", "v1", "seed")
        conversation = get_or_create_active_conversation(self.conn, other_patient, "req-2")
        context = build_context(self.conn, other_patient, conversation["id"])
        self.assertIsNone(context["display_name"])

    def test_a_query_error_degrades_to_an_empty_context_instead_of_raising(self):
        # Building this context must never be the reason a GREEN reply fails:
        # a broken/closed connection should yield "no extra context", not an
        # exception that propagates out of send_message.
        conversation = get_or_create_active_conversation(self.conn, self.patient_id, "req-5")
        self.conn.close()
        try:
            context = build_context(self.conn, self.patient_id, conversation["id"])
        finally:
            self.conn = connect(self.settings.database_path)  # tearDown expects an open connection
        self.assertEqual(context, {"display_name": None, "phq9_trend": [], "phq9_severity_band": None, "recent_messages": []})

    def test_end_to_end_green_message_uses_the_generative_responder_with_context(self):
        engine = FakeEngine(reply="Merci de me le dire, Alex.")
        responder = LocalGenerativeResponder(Path("fake.gguf"), fallback=TemplatedSupportiveResponder(("ack",)), engine_factory=lambda p, c: engine)
        conversation = get_or_create_active_conversation(self.conn, self.patient_id, "req-3")
        result = send_message(
            self.conn, self.patient_id, conversation["id"], "Ma journée s'est plutôt bien passée",
            KeywordRiskModel(), DEFAULT_POLICY, DEFAULT_RULES, DEFAULT_TEMPLATES,
            responder, LogNotificationProvider(), "req-3",
        )
        self.assertEqual(result["assistant_message"]["content"], "Merci de me le dire, Alex.")
        self.assertEqual(len(engine.calls), 1)
        system_message = engine.calls[0][0]["content"]
        self.assertIn("Alex", system_message)

    def test_orange_and_red_messages_never_reach_the_generative_engine(self):
        # Structural guarantee (ADR-004/ADR-005): the LLM has no path to
        # influence crisis framing. A spy engine that records any call at all
        # would fail this test if that guarantee were ever broken.
        engine = FakeEngine()
        responder = LocalGenerativeResponder(Path("fake.gguf"), fallback=TemplatedSupportiveResponder(("ack",)), engine_factory=lambda p, c: engine)
        conversation = get_or_create_active_conversation(self.conn, self.patient_id, "req-4")
        send_message(
            self.conn, self.patient_id, conversation["id"], "J'ai un plan suicidaire",
            KeywordRiskModel(), DEFAULT_POLICY, DEFAULT_RULES, DEFAULT_TEMPLATES, responder, LogNotificationProvider(), "req-4",
        )
        self.assertEqual(engine.calls, [])


if __name__ == "__main__":
    unittest.main()
