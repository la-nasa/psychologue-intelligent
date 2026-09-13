# ADR-011 — MLflow pour Model Registry & MLOps

Date : 2026-09-13
Statut : **Proposé** — pas encore implémenté (correspond à la Phase 17 de la roadmap originale, `server/` est actuellement à la Phase 14 ; le module `mlops/` n'existe pas encore dans `server/app/`).
Origine : audit indépendant mené sur la branche `intelligent-psychologist-bdc4b`, fusionné via PR #1. Renuméroté ADR-011 (était `docs/adr/ADR-006-to-010-stack-architecture.md` §3, portait le numéro ADR-008 dans son document d'origine — collision avec l'ADR-008 déjà accepté de ce dossier, qui traite d'un tout autre sujet : le multi-tenancy).

## Contexte
Le système nécessite un suivi rigoureux des modèles IA : versioning, expérimentation, évaluation, approbation clinique, déploiement contrôlé, rollback.

## Décision
Utiliser MLflow comme plateforme MLOps centrale :

```text
MLflow Tracking: Expériences, paramètres, métriques
MLflow Models: Packaging, formats, dependencies
MLflow Registry: Versioning, stages, transitions
MLflow Projects: Pipelines reproductibles
```

## Stages du Model Registry

```text
EXPERIMENTAL → STAGING → SHADOW → CANARY → PRODUCTION → RETIRED
```

## Intégration Backend (à adapter au layout réel de `server/app/`, pas `backend/app/`)

```python
# server/app/mlops/registry.py  (module à créer en Phase 17)
class ModelRegistry:
    async def register_model(...)
    async def promote_model(...)
    async def get_production_model(...)
    async def rollback(...)

# server/app/mlops/tracking.py
class ExperimentTracker:
    async def log_experiment(...)
    async def log_metrics(...)
    async def compare_models(...)
```

## Pipeline MLOps

```text
Entraînement
 ↓
Évaluation offline
 ↓
MLflow Logging
 ↓
Validation sécurité
 ↓
Validation clinique
 ↓
Shadow deployment
 ↓
Canary (5% traffic)
 ↓
Production (100%)
 ↓
Monitoring continu
```

## Infrastructure

```yaml
# infrastructure/mlflow/docker-compose.yml
mlflow-tracking-server:
  image: ghcr.io/mlflow/mlflow
  ports: ["5000:5000"]
  environment:
    - MLFLOW_S3_ENDPOINT_URL
    - AWS_ACCESS_KEY_ID
    - AWS_SECRET_ACCESS_KEY
  volumes:
    - mlflow_data:/opt/mlflow/data

mlflow-registry:
  depends_on: [mlflow-tracking-server]
```

## Conséquences

### Positives
- Traçabilité complète
- Reproductibilité
- Gouvernance clinique facilitée
- Rollback rapide
- Comparaison modèles

### Négatives
- Infrastructure supplémentaire
- Courbe d'apprentissage équipe
- Stockage artifacts (S3/MinIO requis)

## Alternatives rejetées
- **Weights & Biases** : Cloud-only, moins de contrôle
- **Neptune** : Coût élevé à l'échelle
- **Solution maison** : trop complexe, réinvente la roue

## Note de réconciliation (2026-09-13)
Décision non contredite par l'existant — `server/` n'a pas encore de module `mlops/`, `learning/` ou `analytics/` (Phases 15-17 non commencées). Reste à valider au moment de la Phase 17 réelle, notamment le choix du stockage d'artefacts (S3/MinIO non présent dans `docker-compose.yml` actuel).
