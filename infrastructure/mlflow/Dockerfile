FROM python:3.12-slim

RUN pip install --no-cache-dir mlflow==2.20.1 psycopg2-binary==2.9.10

# Réseau privé Railway uniquement (pas de domaine public) — la gouvernance MLOps
# reste derrière l'authentification applicative, jamais exposée directement.
EXPOSE 5000

CMD ["sh", "-c", "mlflow server --host 0.0.0.0 --port 5000 --backend-store-uri \"$MLFLOW_BACKEND_STORE_URI\" --default-artifact-root \"$MLFLOW_ARTIFACT_ROOT\""]
