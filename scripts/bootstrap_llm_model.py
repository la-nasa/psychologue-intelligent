#!/usr/bin/env python
"""Idempotently download the GGUF model weights for the local generative
responder (ADR-005) into PI_LLM_MODEL_PATH, if PI_RESPONDER_MODE=local-llm.

Safe to run on every container start: does nothing if the mode isn't
local-llm, and does nothing if a file of the expected size already exists at
the target path (in particular, the persistent volume from a prior run --
without this check, every restart would re-download ~2 GB for nothing).

Deliberately stdlib-only (urllib), unlike the responder itself: downloading a
file must not depend on the same optional `llm` extra it is fetching weights
for, and this only ever runs once per fresh volume, not on a request path.
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import Settings

# Pinned to an exact repo revision, not "main", for the same reason
# ml/train_emotion_classifier.py pins its dataset source: reproducibility.
# Apache-2.0 licensed (see https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF).
MODEL_URL = (
    "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/"
    "7dabda4d13d513e3e842b20f0d435c732f172cbe/qwen2.5-3b-instruct-q4_k_m.gguf"
)
EXPECTED_SIZE_BYTES = 2_104_932_768


def main() -> None:
    settings = Settings.from_env()
    if settings.responder_mode != "local-llm":
        print("bootstrap_llm_model: PI_RESPONDER_MODE is not local-llm, skipping.")
        return

    path = settings.llm_model_path
    if path.exists() and path.stat().st_size == EXPECTED_SIZE_BYTES:
        print(f"bootstrap_llm_model: {path} already present ({EXPECTED_SIZE_BYTES:,} bytes), skipping download.")
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".partial")
    print(f"bootstrap_llm_model: downloading {MODEL_URL} to {path} ({EXPECTED_SIZE_BYTES:,} bytes expected)...")
    # MODEL_URL is a fixed, pinned-revision constant above, never user input.
    urllib.request.urlretrieve(MODEL_URL, tmp_path)  # nosec B310

    actual_size = tmp_path.stat().st_size
    if actual_size != EXPECTED_SIZE_BYTES:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"downloaded file size {actual_size:,} does not match expected {EXPECTED_SIZE_BYTES:,} bytes; refusing to use a possibly-truncated model")
    tmp_path.replace(path)
    print(f"bootstrap_llm_model: download complete and verified ({actual_size:,} bytes).")


if __name__ == "__main__":
    main()
