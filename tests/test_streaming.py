from __future__ import annotations

import json
import threading
import time
import unittest
from pathlib import Path

from backend.app.streaming import ModelRouter, StreamingLLMProvider, TemplateStreamingProvider


class Broken:
    version = "broken"
    def stream(self, text, context=None, model=None):
        raise OSError("offline")


class StreamingTests(unittest.TestCase):
    def test_provider_falls_back_in_order(self):
        template = TemplateStreamingProvider(("fallback",))
        provider = StreamingLLMProvider({"remote": Broken(), "template": template}, ("remote", "template"))
        self.assertEqual(provider.generate("hello"), "fallback")

    def test_router_selects_fast_and_deep_models(self):
        template = TemplateStreamingProvider(("ok",))
        provider = StreamingLLMProvider({"template": template}, ("template",))
        router = ModelRouter(provider, "small", "large")
        self.assertEqual(router.route("simple"), "small")
        self.assertEqual(router.route("deep"), "large")

    def test_templates_are_streamed(self):
        template = TemplateStreamingProvider(("one", "two"))
        self.assertEqual(list(template.stream("a")), ["two"])


if __name__ == "__main__":
    unittest.main()
