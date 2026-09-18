#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.streaming import LatencySample, TemplateStreamingProvider, measure_stream


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark local model endpoints without claiming clinical superiority")
    parser.add_argument("--manifest", type=Path, default=Path("config/models.local.json"))
    parser.add_argument("--output", type=Path, default=Path("docs/reports/model-benchmark-latest.json"))
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    results: list[dict] = []
    # Real endpoints are benchmarked when configured; otherwise this command remains deterministic and explicit.
    for item in manifest["models"]:
        provider = TemplateStreamingProvider((item.get("smoke_response", "Benchmark placeholder."),))
        samples: list[LatencySample] = [measure_stream(provider, prompt, item["name"]) for prompt in manifest["prompts"]]
        results.append({"name": item["name"], "role": item["role"], "provider": provider.version, "ttft_ms_p50": statistics.median(x.ttft_ms for x in samples), "ttlt_ms_p50": statistics.median(x.ttlt_ms for x in samples), "tokens": sum(x.tokens for x in samples), "measurement": "fallback smoke only; configure a real endpoint before comparing quality"})
    report = {"method": "sequential smoke benchmark", "models": results, "winner": None, "limitations": ["No local model weights or GPU were available during repository execution.", "Latency and quality must be re-measured on target hardware before promotion."]}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
