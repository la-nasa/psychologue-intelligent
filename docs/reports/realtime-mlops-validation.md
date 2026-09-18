# Realtime and MLOps validation

Install and validate locally:

```bash
python -m pip install -e ".[dev,realtime,mlops]"
python -m unittest discover -s tests -v
ruff check backend tests scripts ml
mypy backend
python scripts/benchmark_real_models.py --base-url "$PI_LLM_BASE_URL" --model fast-local --model deep-local
```

Run the realtime server with:

```bash
python scripts/serve_fastapi.py
```

The authenticated WebSocket endpoint is `/ws/conversations/{conversation_id}`. It accepts a JSON object `{ "text": "..." }` and emits `started`, `token`, `completed`, or `error` events. Authentication is required through `Authorization: Bearer` or the development-only query token.

MLflow production lifecycle:

1. log an evaluated run and artifacts;
2. register the model;
3. tag `shadow` and observe safety/latency;
4. promote to `Staging` and then controlled `canary` metadata;
5. promote to `Production` with alias `champion`;
6. use `rollback()` to move the previous approved version back to production.

The repository cannot perform clinical validation or a target-hardware benchmark by itself. Those outputs require real deployed endpoints, approved evaluation data, human reviewers, and a clinical governance decision. No model is automatically declared superior or clinically validated.
