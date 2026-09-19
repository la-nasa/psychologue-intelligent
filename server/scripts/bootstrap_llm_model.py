#!/usr/bin/env python
"""Télécharge le GGUF CPU par défaut (Qwen2.5-0.5B Q4_K_M) si absent.

Idempotent. N'importe pas llama.cpp. Taille attendue bornée (pas un hash
cryptographique) : un fichier trop petit est refusé comme troncature.

Usage (depuis server/, extra ``llm`` non requis pour le téléchargement) :

    python -m scripts.bootstrap_llm_model
"""
from __future__ import annotations

import os
import urllib.request
from pathlib import Path

# bartowski, révision épinglée. Apache-2.0 (poids Qwen).
MODEL_URL = (
    "https://huggingface.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF/resolve/"
    "a9e606ce42ee093b20b8d3b3132a827242c03c39/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf"
)
MIN_BYTES = 300_000_000
MAX_BYTES = 500_000_000


def _target_path() -> Path:
    return Path(os.environ.get("PI_LLM_MODEL_PATH", "work/models/qwen2.5-0.5b-instruct-q4_k_m.gguf"))


def main() -> None:
    path = _target_path()
    if path.is_file() and MIN_BYTES <= path.stat().st_size <= MAX_BYTES:
        print(f"bootstrap_llm_model: {path} already present ({path.stat().st_size:,} bytes), skipping.")
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".partial")
    print(f"bootstrap_llm_model: downloading {MODEL_URL} to {path}...")
    urllib.request.urlretrieve(MODEL_URL, tmp_path)  # nosec B310

    actual_size = tmp_path.stat().st_size
    if not (MIN_BYTES <= actual_size <= MAX_BYTES):
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"downloaded file size {actual_size:,} is outside [{MIN_BYTES:,}, {MAX_BYTES:,}]; refusing truncated weights"
        )
    tmp_path.replace(path)
    print(f"bootstrap_llm_model: download complete and verified ({actual_size:,} bytes).")


if __name__ == "__main__":
    main()
