#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.streaming import LatencySample, measure_stream


def _remote_provider(base_url: str, api_key: str, model: str, timeout: float):
    from backend.app.streaming import OpenAICompatibleStreamingProvider
    return OpenAICompatibleStreamingProvider(base_url, api_key, timeout, model)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark a real OpenAI-compatible local endpoint")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default="local")
    parser.add_argument("--model", action="append", required=True)
    parser.add_argument("--prompts", type=Path, default=Path("config/models.local.json"))
    parser.add_argument("--output", type=Path, default=Path("docs/reports/model-benchmark-real.json"))
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    base_url = args.base_url or os.environ.get("PI_LLM_BASE_URL")
    if not base_url:
        raise SystemExit("--base-url or PI_LLM_BASE_URL is required; no synthetic winner is produced")
    manifest = json.loads(args.prompts.read_text(encoding="utf-8"))
    prompts = manifest.get("prompts", [])
    results = []
    for model in args.model:
        provider = _remote_provider(base_url, args.api_key, model, args.timeout)
        samples = [measure_stream(provider, prompt, model) for prompt in prompts for _ in range(args.repetitions)]
        results.append({"model": model, "n": len(samples), "ttft_ms_p50": statistics.median(x.ttft_ms for x in samples), "ttft_ms_p95": _percentile([x.ttft_ms for x in samples], .95), "ttlt_ms_p50": statistics.median(x.ttlt_ms for x in samples), "ttlt_ms_p95": _percentile([x.ttlt_ms for x in samples], .95), "tokens": sum(x.tokens for x in samples), "measured_at": time.time()})
    report = {"endpoint": base_url, "models": results, "winner": None, "promotion": "manual safety and clinical review required"}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8"); print(json.dumps(report, indent=2))


def _percentile(values: list[float], p: float) -> float:
    return sorted(values)[min(int(len(values) * p), len(values) - 1)]


if __name__ == "__main__":
    import os
    main()
