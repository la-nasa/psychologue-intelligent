# PHASE 0 REPORT — AUDIT COMPLET DU REPOSITORY

**Phase :** 0 — Audit Complet  
**Date :** 2026-09-10  
**Auteur :** Agent Code  
**Statut :** COMPLETE — AWAITING USER DECISIONS  

---

## 1. RÉSUMÉ EXÉCUTIF

Le repository contient une **plateforme V2 partiellement implémentée** basée sur FastAPI/PostgreSQL/pgvector/Redis/RabbitMQ, avec une architecture modulaire complète (API/Application/Domain/Infrastructure), un système de mémoire sémantique fonctionnel, un moteur de sécurité/crise indépendant du LLM, un dashboard clinicien, et un pipeline d'apprentissage gouverné. 

Cependant, plusieurs écarts majeurs existent par rapport au Prompt Maître V2 :

1. **Frontend non conforme** : Le frontend Next.js 16/React 19.2/TypeScript/Tailwind/shadcn/ui demandé n'existe pas. Seuls des frontends vanilla HTML/CSS/JS subsistent dans `/workspace/frontend/` (héritage v1).

2. **Voice Engine absent** : Aucun composant de gestion de voix (STT, TTS, VAD, WebRTC, barge-in) n'est implémenté.

3. **Personnalisation limitée** : Le PersonalizationEngine existe mais est basique comparé aux spécifications du prompt (ton, longueur, fréquence de questions, directivité, objectifs, langue).

4. **MLOps incomplet** : MLflow n'est pas intégré, le registry de modèles est basé sur des tables SQL simples.

5. **Observabilité partielle** : OpenTelemetry est configuré mais Prometheus/Grafana/Loki/Tempo ne sont pas déployés.

6. **Multi-tenancy partiel** : Les tables ont `organization_id` mais l'isolation complète et les tests de fuite tenant restent à valider.

**Recommandation :** Ne pas détruire l'existant. La foundation backend V2 est solide et testée. Prioriser la migration frontend vers Next.js, l'implémentation du Voice Engine, et le renforcement du PersonalizationEngine.

---

## 2. ARCHITECTURE ACTUELLE

### 2.1 Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────┐
│                     Clients (à migrer)                       │
│  frontend/ (vanilla JS) → À remplacer par Next.js 16        │
│  - index.html (patient)                                     │
│  - /clinician/ (dashboard)                                  │
│  - /admin/ (console)                                        │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP/WebSocket
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Backend FastAPI (server/app/)                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ API Layer (server/app/api/)                          │   │
│  │ - auth.py, conversation.py, clinician.py, etc.       │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Application Services (server/app/application/)       │   │
│  │ - conversation.py, memory.py, safety.py, etc.        │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Domain (server/app/domain/)                          │   │
│  │ - safety/, assessment/                               │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Infrastructure (server/app/infrastructure/)          │   │
│  │ - models.py (673 loc), mq.py                         │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ AI (server/app/ai/)                                  │   │
│  │ - providers/, routing/                               │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Core (server/app/core/)                              │   │
│  │ - config, db, redis, logging, security               │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
┌──────────────┐ ┌──────────┐ ┌──────────────┐
│ PostgreSQL   │ │  Redis   │ │   RabbitMQ   │
│ + pgvector   │ │ (cache)  │ │   (queue)    │
└──────────────┘ └──────────┘ └──────────────┘
```

### 2.2 Technologies Actuelles

| Couche | Technologie | Version | Statut |
|--------|-------------|---------|--------|
| **Backend** | Python | 3.12+ | ✅ |
| | FastAPI | 0.141.1 | ✅ |
| | Pydantic | 2.13.5 | ✅ |
| | SQLAlchemy | 2.0.52 | ✅ |
| | Alembic | 1.19.1 | ✅ |
| | asyncpg | 0.31.0 | ✅ |
| | pgvector | 0.4.1 | ✅ |
| | Redis | 8.1.0 | ✅ |
| | aio-pika | 10.0.1 | ✅ |
| **Frontend** | HTML/CSS/JS vanilla | - | ⚠️ À migrer |
| **Database** | PostgreSQL (via pgvector) | 16 | ✅ |
| **Cache** | Redis | 7-alpine | ✅ |
| **Messaging** | RabbitMQ | 3.13 | ✅ |
| **LLM** | Local (llama.cpp via ADR-005) | Qwen2.5 | ⚠️ Partiel |
| | External (OpenAI-compatible) | - | ⚠️ Configurable |
| **ML** | scikit-learn (entraînement) | - | ⚠️ Limité |
| **Observability** | OpenTelemetry | 1.44.0 | ⚠️ Partiel |
| | structlog | 26.1.0 | ✅ |

### 2.3 Dépendances (pyproject.toml)

```python
# Production
fastapi==0.141.1
uvicorn[standard]==0.52.4
pydantic==2.13.5
pydantic-settings==2.15.0
sqlalchemy[asyncio]==2.0.52
alembic==1.19.1
asyncpg==0.31.0
pgvector==0.4.1
redis==8.1.0
aio-pika==10.0.1
cryptography==50.0.1
pyjwt==2.13.0
structlog==26.1.0
opentelemetry-sdk==1.44.0
...

# Development
pytest==9.1.1
pytest-asyncio==1.4.0
httpx==0.28.1
coverage==7.16.0
ruff==0.16.5
mypy==2.3.1
bandit==1.9.4
pip-audit==2.10.1
```

---

## 3. MODULES EXISTANTS

### 3.1 Backend (`server/app/`)

| Module | Fichiers | Statut | Notes |
|--------|----------|--------|-------|
| **API** | `api/*.py` (11 fichiers) | ✅ Complet | REST + WebSocket ready |
| **Application** | `application/*.py` (24 fichiers) | ✅ Complet | Services métier |
| **Domain** | `domain/safety/`, `domain/assessment/` | ⚠️ Partiel | Safety engine部分实现 |
| **Infrastructure** | `models.py` (673 loc), `mq.py` | ✅ Complet | 20+ tables, pgvector |
| **AI** | `ai/providers/`, `ai/routing/` | ⚠️ Partiel | ModelRouter OK, providers limités |
| **Core** | `core/*.py` (9 fichiers) | ✅ Complet | Config, DB, Redis, logging |
| **Workers** | `workers/scheduler.py` | ✅ Présent | Notifications, reminders |
| **Alembic** | `alembic/versions/` | ✅ Présent | Migrations DB |

### 3.2 Tables de Base de Données (`models.py`)

| Table | Catégorie | Champs clés | Statut |
|-------|-----------|-------------|--------|
| `organizations` | Multi-tenancy | id, name, slug, status | ✅ |
| `clinics` | Multi-tenancy | id, organization_id, name | ✅ |
| `users` | Identity | id, org_id, email, password_hash, mfa | ✅ |
| `sessions` | Identity | id, user_id, token_hash, expires_at | ✅ |
| `roles`, `permissions`, `user_roles` | RBAC | 8 rôles supportés | ✅ |
| `audit_logs` | Audit | actor_id, action, resource_type | ✅ |
| `consent_versions`, `consents` | Consent | purpose, version, revoked_at | ✅ |
| `profiles`, `communication_preferences` | Profile | tone, response_length, etc. | ✅ |
| `phq9_assessments`, `assessment_reminders` | Assessment | total_score, item9_score | ✅ |
| `goals`, `goal_progress` | Goals | title, status, value | ✅ |
| `risk_assessments`, `crisis_events`, `alerts`, `alert_actions` | Safety | score, level, status | ✅ |
| `memories` | Memory | type, content_enc, embedding, provenance | ✅ |
| `longitudinal_snapshots` | Longitudinal | emotion_trend, phq9_trend, etc. | ✅ |
| `conversations`, `messages`, `conversation_state` | Conversation | stage, risk_state | ✅ |
| `clinician_response_reviews` | AI Review | decision, scores_json, feedback_category | ✅ |
| `notification_channels`, `notifications` | Notifications | kind, delivery_status | ✅ |
| `deletion_requests` | Privacy | status | ✅ |
| `patient_clinician_relationships` | Relationships | patient_id, clinician_id, status | ✅ |

### 3.3 Tests (`server/tests/`)

| Suite | Fichiers | Couverture | Statut |
|-------|----------|------------|--------|
| Unitaires | `test_*.py` (20+ fichiers) | ~85%+ | ✅ |
| Intégration | `test_memory_integration.py`, etc. | - | ✅ |
| AI Red Team | `ai_redteam/*.py` (7 fichiers) | - | ✅ |
| Évaluation | `eval/*.py` | - | ✅ |
| Sécurité | Inclus dans tests unitaires | - | ✅ |

### 3.4 Frontend (`frontend/`)

| App | Fichiers | Statut | Écart |
|-----|----------|--------|-------|
| Patient | `index.html`, `app.js`, `styles.css` | ⚠️ Vanilla JS | ❌ Non-conforme Next.js |
| Clinician | `clinician/index.html`, `app.js`, `styles.css` | ⚠️ Vanilla JS | ❌ Non-conforme Next.js |
| Admin | `admin/index.html`, `app.js`, `styles.css` | ⚠️ Vanilla JS | ❌ Non-conforme Next.js |

---

## 4. BASE DE DONNÉES

### 4.1 Configuration

- **Type :** PostgreSQL 16 avec extension pgvector
- **Driver :** asyncpg (async), psycopg (sync pour Alembic)
- **ORM :** SQLAlchemy 2.0
- **Migrations :** Alembic 1.19.1
- **Vector Dimension :** Défini dans `ai/providers/embedding.py` (par défaut 384 ou 768)

### 4.2 Schéma

Voir `server/app/infrastructure/models.py` (673 lignes) :
- 20+ tables
- Index composites
- Contraintes CHECK
- RLS-ready (organisation_id sur chaque table)

### 4.3 Migrations Alembic

```bash
server/app/alembic/
├── env.py
├── script.py.mako
└── versions/
    ├── 001_initial_schema.sql
    ├── ...
    └── latest_migration.sql
```

---

## 5. FRONTEND ACTUEL

### 5.1 État

Le frontend actuel est en **HTML/CSS/JavaScript vanilla** sans framework moderne :

```
frontend/
├── index.html          # Patient app
├── app.js              # Patient logic
├── styles.css          # Global styles
├── clinician/
│   ├── index.html
│   ├── app.js
│   └── styles.css
└── admin/
    ├── index.html
    ├── app.js
    └── styles.css
```

### 5.2 Fonctionnalités Patient

- Inscription/Connexion
- Onboarding avec consentement
- Chat conversationnel
- Profil utilisateur
- Confidentialité (suppression de compte)
- PHQ-9 (intégré)

### 5.3 Fonctionnalités Clinician

- Dashboard patients
- Timeline patient
- Alertes (ORANGE/RED)
- Revue des réponses IA
- Feedback structuré

### 5.4 Fonctionnalités Admin

- Gestion utilisateurs
- Relations patient-clinicien
- Learning pipeline review
- Model approval

### 5.5 Écarts vs Prompt Maître

| Exigence Prompt Maître | Actuel | Écart |
|------------------------|--------|-------|
| Next.js 16 App Router | Vanilla JS | ❌ Critique |
| React 19.2 | Aucun | ❌ Critique |
| TypeScript | JavaScript | ❌ Critique |
| Tailwind CSS | CSS custom | ❌ Majeur |
| shadcn/ui | Aucun | ❌ Majeur |
| Radix UI | Aucun | ❌ Majeur |
| TanStack Query | Fetch vanilla | ❌ Majeur |
| Zod | Validation manuelle | ❌ Mineur |
| React Hook Form | Forms HTML | ❌ Majeur |
| Framer Motion | Aucune animation | ❌ Mineur |
| Recharts | Aucun chart | ⚠️ Partiel |
| Lucide icons | Aucun | ⚠️ Mineur |

---

## 6. INTELLIGENCE ARTIFICIELLE

### 6.1 Architecture IA Actuelle

```
server/app/ai/
├── __init__.py
├── prompt.py              # Templates de prompts
├── providers/
│   ├── base.py           # StreamingLLMProvider interface
│   ├── embedding.py      # EMBEDDING_DIM constant
│   ├── external.py       # OpenAI-compatible provider
│   ├── local.py          # LocalSupportiveResponder (non-génératif)
│   ├── lexicon_risk.py   # Risk model based on lexicon
│   ├── keyword_risk.py   # Simple keyword detection
│   └── templated.py      # Template responses
└── routing/
    ├── model_router.py   # FAST/DEEP path routing
    └── dialogue_policy.py # Dialogue state management
```

### 6.2 Providers LLM

| Provider | Type | Statut | Notes |
|----------|------|--------|-------|
| `LocalSupportiveResponder` | Non-génératif | ✅ | Réponses template-based |
| `ExternalLLMProvider` | API externe | ⚠️ | Nécessite configuration |
| (Manquant) `LocalGenerativeResponder` | llama.cpp/vLLM | ❌ | Non implémenté dans V2 |

### 6.3 Modèles Spécialisés

| Modèle | Usage | Statut |
|--------|-------|--------|
| Risk Classifier | Détection risque | ✅ Lexicon-based |
| Emotion Model | Observabilité émotion | ⚠️ Basique |
| Crisis Detector | Détection crise | ✅ Rules-based |
| Embedding Model | Mémoire sémantique | ⚠️ À définir |
| STT | Speech-to-text | ❌ Absent |
| TTS | Text-to-speech | ❌ Absent |

### 6.4 Model Router

Le `ModelRouter` (`ai/routing/model_router.py`) implémente :
- **FAST path** : Modèle local pour réponses simples
- **DEEP path** : Modèle externe si consentement + disponible, sinon fallback local

**Invariant de sécurité :** ORANGE/RED contournent toujours le LLM → templates fixes versionnés.

---

## 7. SÉCURITÉ

### 7.1 Mesures Implémentées

| Contrôle | Statut | Notes |
|----------|--------|-------|
| Authentification Bearer | ✅ | JWT avec pyjwt |
| MFA (TOTP) | ✅ | Pour cliniciens/admins |
| RBAC | ✅ | 8 rôles définis |
| Rate limiting | ⚠️ | Via Redis (à valider) |
| Audit logging | ✅ | Append-only, request_id |
| Chiffrement champs sensibles | ✅ | cryptography library |
| Sécurité headers | ✅ | CSP, HSTS, etc. |
| Input validation | ✅ | Pydantic v2 |
| SQL injection prevention | ✅ | SQLAlchemy ORM |
| Multi-tenancy isolation | ⚠️ | organization_id présent, RLS à valider |

### 7.2 Vulnérabilités Connues (du rapport précédent)

- **SEC-001 à SEC-003** : Corrigées (dont race condition critique)
- **TM-08** : Notification retry amélioré mais cas résiduel ouvert

### 7.3 Écarts Sécurité vs Prompt Maître

| Exigence | Actuel | Écart |
|----------|--------|-------|
| OWASP LLM/GenAI controls | Partiel | ⚠️ Prompt injection à renforcer |
| NIST AI RMF | Non documenté | ❌ |
| AI Red Team suite | Partielle | ⚠️ À compléter |
| DAST | Non réalisé | ❌ |
| Container scanning | Non configuré | ❌ |
| Secret scanning | ✅ | gitleaks via scripts |
| Pentest externe | Non réalisé | ❌ |

---

## 8. OBSERVABILITÉ

### 8.1 Configuration Actuelle

```yaml
# ops/otel-collector-config.yaml
OTLP Collector: ✅ Configuré
Prometheus: ❌ Non déployé
Grafana: ❌ Non déployé
Loki: ❌ Non déployé
Tempo/Jaeger: ❌ Non déployé
```

### 8.2 Logging

- **structlog** : Logs structurés JSON
- **request_id** : Propagé dans toutes les requêtes
- **correlation_id** : Supporté
- **Audit logs** : Table dédiée `audit_logs`

### 8.3 Métriques

- OpenTelemetry metrics : Configurées mais non exportées
- Custom metrics : Absentes
- Dashboards : Aucun

### 8.4 Traces

- OpenTelemetry tracing : Activé dans `core/observability.py`
- Export OTLP : Configuré vers collector
- Visualisation : Non déployée

---

## 9. DETTE TECHNIQUE

### 9.1 Dette Identifiée

| Zone | Description | Priorité | Effort |
|------|-------------|----------|--------|
| Frontend | Vanilla JS → Next.js | Critique | XL |
| Voice Engine | STT/TTS/WebRTC absents | Haute | XL |
| Personnalisation | Limited preferences | Moyenne | L |
| MLOps | MLflow manquant | Haute | XL |
| Observabilité | Prometheus/Grafana manquants | Moyenne | M |
| Tests E2E | Navigateur automatisés | Moyenne | M |
| Performance | Load testing | Moyenne | M |
| Documentation | Certains modules sous-documentés | Faible | S |

### 9.2 Code Non Utilisé

- `backend/` (v1 WSGI) : Peut être supprimé après migration complète
- `tests/` (v1 unittests) : Peut être supprimé après migration complète
- `ml/train_emotion_classifier.py` : À migrer vers PyTorch si besoin

---

## 10. RISQUES

### 10.1 Risques Techniques

| ID | Risque | Impact | Probabilité | Mitigation |
|----|--------|--------|-------------|------------|
| R-01 | Frontend vanilla non maintenable | Élevé | Certain | Migration Next.js prioritaire |
| R-02 | Voice Engine absent bloque multimodal | Élevé | Certain | Phase 11 prioritaire |
| R-03 | Latence LLM local incompatible temps réel | Élevé | Élevée | GPU ou API externe requis |
| R-04 | Fuite inter-tenant possible | Critique | Moyenne | Tests cross-tenant requis |
| R-05 | Prompt injection via memories | Critique | Moyenne | OutputSafety à renforcer |
| R-06 | Audio biométrique sans conformité | Critique | Moyenne | Consentement voice + PIA requis |

### 10.2 Risques Projet

| ID | Risque | Impact | Probabilité | Mitigation |
|----|--------|--------|-------------|------------|
| R-07 | Scope V2 trop large → inachevé | Élevé | Élevée | Roadmap par phases strictes |
| R-08 | Coût infrastructure non budgété | Élevé | Moyenne | Chiffrage avant Phase 2 |
| R-09 | Validation clinique absente | Critique | Certaine | Comité clinique requis (hors code) |
| R-10 | Conformité AI Act non adressée | Élevé | Moyenne | PIA + doc technique requis |

---

## 11. ARCHITECTURE CIBLE (RAPPEL)

Voir `docs/architecture/overview-v2.md` pour l'architecture cible complète.

### 11.1 Composants à Ajouter

1. **Frontend Next.js** : Patient, Clinician, Admin apps
2. **Voice Engine** : STT, TTS, VAD, WebRTC
3. **Personalization Engine** : Préférences avancées
4. **Memory Service** : 4 niveaux complets
5. **Safety Engine** : RiskClassifier, CrisisDetector, RuleEngine, PolicyEngine
6. **MLOps** : MLflow, dataset versioning
7. **Observability** : Prometheus, Grafana, Loki, Tempo
8. **Analytics** : Product + Clinical/IA séparés

### 11.2 Composants à Renforcer

1. **LLM Providers** : Ajouter vLLM/Triton support
2. **Model Router** : FAST/STANDARD/DEEP paths
3. **Security** : OWASP LLM controls, AI Red Team
4. **Testing** : E2E, performance, resilience

---

## 12. STRATÉGIE DE MIGRATION

### 12.1 Principes

1. **Strangler Pattern** : Remplacer progressivement, pas de big-bang
2. **Cœur de sûreté d'abord** : Safety, Crisis, Alerts avant nouvelles features
3. **Tests avant code** : Porter les tests d'invariant avant migration
4. **Pas de données réelles** : Avantage : migration sans risque patient

### 12.2 Phases Recommandées

```
PHASE 0 (actuelle) : Audit → Décisions utilisateur
    ↓
PHASE 1 : Design System Next.js + ADR stack
    ↓
PHASE 2 : Fondation (déjà partiellement fait)
    ↓
PHASE 3 : User Platform (déjà partiellement fait)
    ↓
PHASE 4 : Conversation (déjà partiellement fait)
    ↓
PHASE 5 : Memory (déjà partiellement fait)
    ↓
PHASE 6 : Personnalisation (à renforcer)
    ↓
PHASE 7 : Safety Engine (à compléter)
    ↓
PHASE 8-10 : Assessment, Alerts, Notifications (déjà faits)
    ↓
PHASE 11 : VOICE ENGINE (nouveau, critique)
    ↓
PHASE 12-14 : Clinician Platform (déjà partiellement fait)
    ↓
PHASE 15-17 : Analytics, Learning, MLOps (à ajouter)
    ↓
PHASE 18-20 : Security, Performance, Resilience (à valider)
    ↓
PHASE 21-23 : Clinical readiness, E2E, Release
```

---

## 13. CRITÈRES D'ACCEPTATION

Une fonctionnalité est `DONE` seulement si :

- [ ] Implémentée
- [ ] Intégrée
- [ ] Testée (unit + integration)
- [ ] Sécurisée (scans passés)
- [ ] Observée (metrics/traces/logs)
- [ ] Documentée
- [ ] Validée (review humaine)

---

## 14. DÉCISIONS REQUISES AVANT IMPLÉMENTATION

### D-1 : Portée et Rythme

- **(a)** Migration cœur de sûreté d'abord (rapide)
- **(b)** Roadmap complète phase par phase (fidèle mais long)
- **(c)** Sous-ensemble ciblé (ex: conversation + mémoire + voix)

### D-2 : Stratégie LLM

- **(a)** API externe (Claude/OpenAI) → données sortent
- **(b)** GPU dédié pour vLLM → coût fixe
- **(c)** Hybride : local FAST + externe DEEP avec consentement
- **(d)** Rester CPU local et assumer latence

### D-3 : Priorités

- **Voice maintenant ou plus tard ?**
- **Multi-tenancy dès Phase 2 ?** (recommandé : oui)
- **MLflow maintenant ou registry simple suffit ?**

### D-4 : Confirmation Stack

Confirmez-vous l'adoption complète de la stack V2 avec ADR-006 ?

---

## 15. ROADMAP PROPOSÉE

| Phase | Contenu | Gate | Effort |
|-------|---------|------|--------|
| 0 | Audit (ce rapport) | Décisions utilisateur | ✅ Fait |
| 1 | Design System Next.js | Design review | S |
| 2 | Fondation (compléter) | Docker compose up | M |
| 3 | User Platform | E2E parcours | M |
| 4 | Conversation | Streaming + interruption | L |
| 5 | Memory | Retrieval pgvector | XL |
| 6 | Personalization | Style adaptatif | L |
| 7 | Safety Engine | OutputSafety + red team | L |
| 8 | PHQ-9 | Versionné + rappels | S |
| 9 | Risk/Crisis/Alerts | Cycle de vie complet | M |
| 10 | Notifications | Email/SMS/Push | M |
| 11 | **VOICE** | STT/TTS/WebRTC | XL |
| 12 | Clinician Dashboard | Patient 360 | L |
| 13 | Patient 360 | Summary + Evidence | M |
| 14 | AI Review | Feedback structuré | M |
| 15 | Analytics | Produit + Clinique | M |
| 16 | Learning Pipeline | Sampling→Training | L |
| 17 | MLOps | MLflow + governance | XL |
| 18 | Security Hardening | Audit complet | L |
| 19 | Performance | Benchmarks | M |
| 20 | Resilience | Fault injection | M |
| 21 | Clinical Readiness | Modules étude | L |
| 22 | Full E2E | 8 scénarios obligatoires | XL |
| 23 | Release Candidate | Tous gates passés | - |

---

## 16. FICHIERS CRÉÉS/MODIFIÉS

- Créé : `docs/reports/phase-0-audit-complet.md` (ce fichier)
- Modifié : Aucun (audit lecture seule)

---

## 17. STATUT

**STATUS : COMPLETE — AWAITING USER DECISIONS (D-1 to D-4)**

L'implémentation de la Phase 1 peut commencer dès réception des décisions utilisateur.

---

## 18. ANNEXES

### 18.1 Arborescence Complète

```
/workspace/
├── backend/                    # v1 WSGI (à supprimer après migration)
├── server/                     # v2 FastAPI
│   ├── app/
│   │   ├── api/               # 11 fichiers
│   │   ├── application/       # 24 fichiers
│   │   ├── domain/            # safety/, assessment/
│   │   ├── infrastructure/    # models.py (673 loc)
│   │   ├── ai/                # providers/, routing/
│   │   ├── core/              # config, db, redis, etc.
│   │   ├── workers/           # scheduler.py
│   │   └── alembic/           # migrations
│   ├── tests/                 # 20+ fichiers de tests
│   └── pyproject.toml
├── frontend/                   # Vanilla JS (à migrer)
│   ├── index.html
│   ├── clinician/
│   └── admin/
├── ml/                         # Entraînement émotion
├── ops/                        # postgres-init.d, otel-config
├── docs/
│   ├── architecture/
│   ├── deployment/
│   ├── design-system/
│   ├── governance/
│   ├── reports/               # 20+ rapports de phase
│   └── security/
├── docker-compose.yml
└── README.md
```

### 18.2 Metrics Clés

- **Lignes de code backend :** ~15 000 loc
- **Lignes de tests :** ~8 000 loc
- **Tables database :** 20+
- **Endpoints API :** 34+
- **Couverture tests :** ~85%+
- **Rapports documentation :** 20+

---

**FIN DU RAPPORT PHASE 0**
