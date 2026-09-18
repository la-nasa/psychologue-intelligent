# Phase 1 — streaming, routing, voice and MLOps

Implemented on branch `feat/streaming-router-voice-mlflow`:

- dependency-light `StreamingLLMProvider` with ordered OpenAI-compatible → in-process GGUF → template fallback;
- `ModelRouter` with explicit FAST_PATH and DEEP_PATH model IDs;
- settings for endpoint, timeout, backend order, model paths and token budgets;
- SSE parsing compatible with vLLM and llama.cpp server;
- deterministic streaming/router tests;
- local model benchmark manifest and honest report (no model is promoted without hardware measurements and clinical approval);
- browser voice page with explicit LISTENING/PROCESSING/SPEAKING/INTERRUPTED/ERROR states, interruption and microphone failure handling, without WebRTC or GPU Whisper;
- optional MLflow adapter with JSONL fallback through `MLOpsTracker`.

The existing crisis pipeline is untouched: this provider is intended for GREEN responses only and cannot alter ORANGE/RED policy framing. FastAPI/WebSocket transport remains an integration step because the current runtime is WSGI; it must be wired behind authentication and conversation ownership before enabling `PI_REALTIME_ENABLED`.

Validation commands:

```bash
pip install -e ".[dev]"
python -m unittest discover -s tests -v
python scripts/benchmark_models.py
```

For a real comparison, configure a local vLLM/llama.cpp server and rerun the benchmark on target hardware. The checked-in smoke benchmark intentionally does not claim a winner.
