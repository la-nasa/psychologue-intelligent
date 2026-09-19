#!/usr/bin/env python
"""Mesure le TTFT du fournisseur local hybride. Hors CI. N'invente aucun chiffre.

Depuis la racine du dépôt, avec l'API ou un GGUF configuré :

    cd server
    python ../scripts/benchmark_llm_ttft.py

Imprime p50/p95 des tours réussis, ou échoue si aucun backend génératif n'est
joignable (gabarits seuls = hors périmètre de cette mesure).
"""
from __future__ import annotations

import asyncio
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from app.ai.providers.generative_local import HybridLocalProvider  # noqa: E402
from app.core.config import get_settings  # noqa: E402

MESSAGES = [
    {"role": "system", "content": "Tu es un accompagnant de soutien. Réponds en une phrase."},
    {"role": "user", "content": "Bonjour, je voudrais juste un mot d'accueil."},
]


async def one_turn(provider: HybridLocalProvider, max_tokens: int) -> tuple[float, float]:
    started = time.perf_counter()
    ttft = None
    async for _fragment in provider.stream(MESSAGES, max_tokens=max_tokens):  # type: ignore[arg-type]
        if ttft is None:
            ttft = time.perf_counter() - started
    if ttft is None:
        raise RuntimeError("aucun token émis")
    total = time.perf_counter() - started
    return ttft, total


async def main() -> int:
    settings = get_settings()
    provider = HybridLocalProvider(settings=settings)
    if not await provider.health_check():
        print("benchmark_llm_ttft: aucun backend génératif (HTTP ou GGUF). Rien à mesurer.")
        print("Configurez PI_LLM_BASE_URL ou PI_LLM_MODEL_PATH + extra llm.")
        return 2
    samples: list[tuple[float, float]] = []
    for i in range(3):
        ttft, total = await one_turn(provider, settings.llm_max_reply_tokens)
        samples.append((ttft, total))
        print(f"  tour {i + 1}: TTFT={ttft * 1000:.0f} ms  total={total * 1000:.0f} ms  version={provider.version}")
    ttfts = [s[0] * 1000 for s in samples]
    totals = [s[1] * 1000 for s in samples]
    print(
        f"p50 TTFT={statistics.median(ttfts):.0f} ms  "
        f"p50 total={statistics.median(totals):.0f} ms  "
        f"(n={len(samples)}; objectifs d'ingénierie, pas des garanties)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
