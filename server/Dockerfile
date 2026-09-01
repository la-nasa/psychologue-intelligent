FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dépendances d'abord (cache de couche) — pyproject seul. Le cache pip est monté
# en cache BuildKit : les téléchargements survivent aux rebuilds et reprennent
# après une coupure réseau (registre PyPI parfois instable depuis ce runner).
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip pip install --upgrade pip setuptools wheel
RUN --mount=type=cache,target=/root/.cache/pip pip install -e ".[dev]"
# PyJWT 2.x est typé nativement — retirer un éventuel stub obsolète (ne doit pas
# faire échouer le build s'il est absent).
RUN pip uninstall -y types-PyJWT || true

COPY . .

# Re-résout le finder editable maintenant que le code est présent (le layer
# ci-dessus l'a installé sans package sur disque). PYTHONPATH=/app couvre le
# cas du montage de volume en développement.
RUN --mount=type=cache,target=/root/.cache/pip pip install -e ".[dev]" --no-deps

# Utilisateur non-root
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Le healthcheck du conteneur interroge la liveness, jamais la readiness
# (la liveness ne doit pas dépendre de la base — voir app/api/health.py)
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health/live').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
