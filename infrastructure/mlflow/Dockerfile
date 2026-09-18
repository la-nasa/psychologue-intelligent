FROM python:3.12-slim

RUN pip install --no-cache-dir mlflow==2.20.1 psycopg2-binary==2.9.10
RUN mkdir -p /mlflow-artifacts

# Réseau privé Railway uniquement (pas de domaine public) — la gouvernance MLOps
# reste derrière l'authentification applicative, jamais exposée directement.
EXPOSE 5000

# --artifacts-destination (plutôt que --default-artifact-root) + --serve-artifacts :
# les clients (l'API) uploadent les artefacts via le proxy HTTP du serveur MLflow
# au lieu d'écrire sur un chemin local — sans ça, un client distant essaie
# d'écrire directement sur SON PROPRE système de fichiers, jamais celui-ci.
CMD ["sh", "-c", "mlflow server --host 0.0.0.0 --port 5000 --backend-store-uri \"$MLFLOW_BACKEND_STORE_URI\" --artifacts-destination \"$MLFLOW_ARTIFACT_ROOT\" --serve-artifacts"]
