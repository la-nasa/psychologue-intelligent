# PHASE 2 — FOUNDATION

## Objectif

Implémenter les fondations techniques critiques pour une plateforme multi-tenant, sécurisée et observable.

## Périmètre (Prompt Maître §129)

### 2.1 Multi-Tenancy (Priorité D-3)
- [ ] Middleware d'isolation par organisation
- [ ] RLS (Row Level Security) PostgreSQL
- [ ] Contexte tenant dans toutes les requêtes
- [ ] Tests d'isolation cross-tenant

### 2.2 Configuration MLflow (Priorité D-3)
- [ ] Docker Compose MLflow
- [ ] Tracking server configuré
- [ ] Model Registry prêt
- [ ] Intégration avec backend Python

### 2.3 Observabilité (Prometheus + Grafana)
- [ ] Docker Compose Prometheus
- [ ] Docker Compose Grafana
- [ ] Dashboards de base
- [ ] Métriques custom exposées

### 2.4 Renforcement Authentification
- [ ] JWT refresh tokens
- [ ] MFA obligatoire pour cliniciens
- [ ] Rate limiting distribué (Redis)
- [ ] Audit logging complet

### 2.5 Health Checks & Metrics
- [ ] Endpoints `/health`, `/ready`, `/metrics`
- [ ] Checks dépendances (DB, Redis, RabbitMQ, LLM)
- [ ] Métriques Prometheus exposées

### 2.6 CI/CD de Base
- [ ] GitHub Actions workflow
- [ ] Lint + Typecheck + Tests
- [ ] Build Docker
- [ ] Security scan (Bandit, pip-audit)

### 2.7 Backups Automatisés
- [ ] Script backup PostgreSQL
- [ ] Rotation des backups
- [ ] Test de restauration documenté

---

## Architecture Multi-Tenancy

### Approche choisie: Schema-per-Organization + RLS

```
PostgreSQL
├── schema: public (tables partagées)
│   ├── organizations
│   └── users (référence organization_id)
├── schema: org_{id} (données isolées)
│   ├── patients
│   ├── conversations
│   ├── memories
│   ├── alerts
│   └── ...
```

**Avantages:**
- Isolation forte des données cliniques
- Backup/restore par organisation possible
- Performance (moins de filtres WHERE)
- Compliance RGPD facilitée

**Invariants:**
1. Jamais de jointure cross-schema sauf tables publiques
2. `organization_id` toujours vérifié côté serveur
3. Tests penetration obligatoires avant production

---

## Livrables Attendus

### Code
- `/workspace/server/app/core/tenant.py` — Middleware multi-tenancy
- `/workspace/server/app/application/organization.py` — Service organisations
- `/workspace/infrastructure/mlflow/docker-compose.yml` — MLflow stack
- `/workspace/infrastructure/monitoring/prometheus.yml` — Config Prometheus
- `/workspace/infrastructure/monitoring/grafana/dashboards/` — Dashboards
- `/workspace/ops/backup.sh` — Script backup
- `/workspace/.github/workflows/ci.yml` — CI pipeline

### Tests
- Tests isolation multi-tenancy (cross-org access = forbidden)
- Tests rate limiting (Redis)
- Tests health checks
- Tests MFA flow

### Documentation
- ADR-011: Multi-Tenancy Architecture
- ADR-012: MLflow Model Registry
- Runbook: Backup/Restore procedure
- Runbook: Monitoring dashboards guide

---

## Critères d'Acceptation

- [ ] Deux organisations ne peuvent jamais accéder aux données l'une de l'autre
- [ ] MLflow tracke les expériences localement
- [ ] Prometheus scrape les métriques API
- [ ] Grafana affiche latency p50/p95/p99, error rate, throughput
- [ ] MFA fonctionne pour rôles cliniciens
- [ ] Rate limiting bloque après N tentatives
- [ ] Health check échoue si DB/Redis/RabbitMQ down
- [ ] Backup PostgreSQL testé et restauré avec succès
- [ ] CI passe sur chaque commit (lint, typecheck, tests)

---

## Risques Identifiés

| Risque | Impact | Mitigation |
|--------|--------|------------|
| Fuite cross-tenant | Critique | Tests penetration, audit code, RLS |
| Complexité schema-per-org | Moyen | Scripts migration auto-generated |
| MLflow non utilisé | Faible | Documentation claire, exemples |
| Prometheus trop gourmand | Faible | Sampling, retention policy |

---

## Timeline Estimée

- J1-2: Multi-tenancy middleware + tests
- J3: MLflow configuration
- J4: Prometheus + Grafana
- J5: Health checks + metrics endpoints
- J6: CI/CD pipeline
- J7: Backups + documentation

**Total: 7 jours (1 semaine)**

---

## Dépendances

- PostgreSQL 16+ avec pgvector ✅ (existant)
- Redis 7+ ✅ (existant)
- RabbitMQ ✅ (existant)
- Docker Compose ✅ (existant)
- Frontend Next.js ✅ (Phase 1 terminée)

---

## Prochaine Étape Après Phase 2

**PHASE 3 — USER PLATFORM**
- Registration avec consentement
- Login + MFA
- Profile management
- Onboarding
- Privacy settings
- Account deletion (RGPD)
