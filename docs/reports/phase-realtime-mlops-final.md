# Phase report — realtime and governed MLOps completion

Implemented:

- FastAPI application with authenticated WebSocket `/ws/conversations/{conversation_id}`;
- token authentication from Bearer header or query parameter;
- conversation ownership and active-session checks;
- streaming tokens and final persisted message;
- shared safety pipeline before generation; GREEN only reaches ModelRouter;
- ORANGE/RED remain fixed policy responses;
- optional `scripts/serve_fastapi.py` runtime;
- corrected optional dependency groups for realtime and MLflow;
- MLflow tracking, artifact logging, registry registration, stage transition and aliases;
- deterministic authenticated WebSocket integration test.

Validation:

```bash
pip install -e ".[dev,realtime,mlops]"
python -m unittest discover -s tests -v
ruff check backend tests scripts ml
mypy backend
python scripts/benchmark_models.py
```

The repository cannot truthfully claim a real target-infrastructure benchmark or clinical quality validation from source changes alone. Those require the deployed model endpoints, target CPU/GPU, representative approved dataset, human reviewers, and an approved clinical protocol. No model is automatically promoted by this commit.
