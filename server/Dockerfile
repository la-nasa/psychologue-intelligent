FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dépendances d'abord (cache de couche) — pyproject seul.
# Le montage de cache BuildKit (`RUN --mount=type=cache`, qui protégeait des
# coupures réseau PyPI sur le runner local) a été retiré 2026-09-13 : le
# builder distant de Railway le rejette (« missing an id argument », puis
# « missing the cacheKey prefix from its id » avec un id explicite — une
# convention interne non documentée). Sans lui, un pip install interrompu doit
# retélécharger entièrement au lieu de reprendre — régression acceptée pour
# rester déployable sur les deux builders avec un seul Dockerfile.
# Compilateur uniquement si la roue CPU llama-cpp-python est absente.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --upgrade pip setuptools wheel
# Wheels CPU précompilées (extra-index) ; repli compilation locale si besoin.
ENV CMAKE_ARGS="-DGGML_NATIVE=OFF -DGGML_BLAS=OFF"
RUN pip install -e ".[dev,llm]" \
        --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
# PyJWT 2.x est typé nativement — retirer un éventuel stub obsolète (ne doit pas
# faire échouer le build s'il est absent).
RUN pip uninstall -y types-PyJWT || true

COPY . .

# Re-résout le finder editable maintenant que le code est présent (le layer
# ci-dessus l'a installé sans package sur disque). PYTHONPATH=/app couvre le
# cas du montage de volume en développement.
RUN pip install -e ".[dev,llm]" --no-deps

# GGUF CPU embarqué : sans ce fichier, HybridLocalProvider retombe sur les gabarits
# (« Merci pour ce message. Y a-t-il un aspect… »).
ENV PI_LLM_MODEL_PATH=/app/work/models/qwen2.5-0.5b-instruct-q4_k_m.gguf \
    PI_LLM_N_GPU_LAYERS=0 \
    PI_LLM_CONTEXT_TOKENS=2048 \
    PI_LLM_THREADS=2 \
    PI_LLM_MAX_REPLY_TOKENS=220
RUN python -m scripts.bootstrap_llm_model

# Utilisateur non-root
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Le healthcheck du conteneur interroge la liveness, jamais la readiness
# (la liveness ne doit pas dépendre de la base — voir app/api/health.py)
HEALTHCHECK --interval=10s --timeout=3s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request,os,sys; p=os.environ.get('PORT','8000'); sys.exit(0 if urllib.request.urlopen(f'http://localhost:{p}/health/live').status==200 else 1)"

# Commande par défaut : conteneur autonome (ex. déploiement Railway par upload
# CLI, qui n'honore pas `railway.toml`/startCommand pour ce mode de déploiement
# — vérifié 2026-09-13). `docker-compose.yml` (dev local) et le service
# `worker` définissent leur propre `command:` qui écrase celle-ci, donc ce
# changement ne les affecte pas. Migrations obligatoires (&&) ; amorçage de
# l'organisation/compte de démonstration best-effort et idempotent (;), piloté
# par PI_BOOTSTRAP_ADMIN_EMAIL/PI_BOOTSTRAP_ADMIN_PASSWORD (no-op silencieux si
# absents, ex. en local hors compose).
CMD ["sh", "-c", "python -m alembic upgrade head && (python -m scripts.bootstrap --org-slug demo --org-name \"Demonstration\" --email \"$PI_BOOTSTRAP_ADMIN_EMAIL\" --password \"$PI_BOOTSTRAP_ADMIN_PASSWORD\" --role ADMIN; exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000})"]
