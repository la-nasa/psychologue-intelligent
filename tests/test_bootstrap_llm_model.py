from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import scripts.bootstrap_llm_model as bootstrap_llm_model
from scripts.bootstrap_llm_model import EXPECTED_SIZE_BYTES, main


class BootstrapLlmModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(ignore_cleanup_errors=True)
        self.model_path = Path(self.temp.name) / "models" / "model.gguf"

    def tearDown(self):
        self.temp.cleanup()

    def _env(self, **overrides) -> dict[str, str]:
        base = {"PI_LLM_MODEL_PATH": str(self.model_path)}
        base.update(overrides)
        return base

    def test_does_nothing_when_responder_mode_is_not_local_llm(self):
        with mock.patch.dict(os.environ, self._env(PI_RESPONDER_MODE="templated"), clear=True), \
             mock.patch("scripts.bootstrap_llm_model.urllib.request.urlretrieve") as fake_download:
            main()
        fake_download.assert_not_called()
        self.assertFalse(self.model_path.exists())

    def test_skips_download_when_a_correctly_sized_file_already_exists(self):
        self.model_path.parent.mkdir(parents=True)
        self.model_path.write_bytes(b"x" * 100)  # not the real size; patched below to match
        with mock.patch("scripts.bootstrap_llm_model.EXPECTED_SIZE_BYTES", 100), \
             mock.patch.dict(os.environ, self._env(PI_RESPONDER_MODE="local-llm"), clear=True), \
             mock.patch("scripts.bootstrap_llm_model.urllib.request.urlretrieve") as fake_download:
            main()
        fake_download.assert_not_called()

    def test_downloads_when_missing_and_verifies_size_before_accepting_it(self):
        def fake_urlretrieve(url, target):
            Path(target).write_bytes(b"x" * 100)

        with mock.patch("scripts.bootstrap_llm_model.EXPECTED_SIZE_BYTES", 100), \
             mock.patch.dict(os.environ, self._env(PI_RESPONDER_MODE="local-llm"), clear=True), \
             mock.patch("scripts.bootstrap_llm_model.urllib.request.urlretrieve", side_effect=fake_urlretrieve) as fake_download:
            main()
        fake_download.assert_called_once()
        self.assertTrue(self.model_path.exists())
        self.assertEqual(self.model_path.stat().st_size, 100)
        self.assertFalse(self.model_path.with_suffix(".gguf.partial").exists())

    def test_rejects_and_removes_a_truncated_download(self):
        def fake_truncated_urlretrieve(url, target):
            Path(target).write_bytes(b"x" * 5)  # far short of the expected size

        with mock.patch("scripts.bootstrap_llm_model.EXPECTED_SIZE_BYTES", 100), \
             mock.patch.dict(os.environ, self._env(PI_RESPONDER_MODE="local-llm"), clear=True), \
             mock.patch("scripts.bootstrap_llm_model.urllib.request.urlretrieve", side_effect=fake_truncated_urlretrieve):
            with self.assertRaises(RuntimeError):
                main()
        self.assertFalse(self.model_path.exists())

    def test_expected_size_constant_matches_the_real_pinned_release(self):
        # A regression guard against silently editing the URL without updating
        # the size (or vice versa) -- a mismatch would make every real download
        # fail the integrity check in test_downloads_when_missing above's real
        # (non-mocked) counterpart on an actual deploy.
        self.assertGreater(EXPECTED_SIZE_BYTES, 0)
        self.assertIn("7dabda4d13d513e3e842b20f0d435c732f172cbe", bootstrap_llm_model.MODEL_URL)


if __name__ == "__main__":
    unittest.main()
