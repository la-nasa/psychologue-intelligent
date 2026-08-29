# PHASE REPORT

Phase : 2 (V2) — Fondation
Date : 2026-08-29
Objectif : Poser le socle exécutable de la stack V2 (ADR-006) — API FastAPI en couches, PostgreSQL + Alembic + RLS multi-tenant (ADR-008), Redis (rate limiting distribué), RabbitMQ, OpenTelemetry, Docker Compose, authentification + RBAC + audit, health checks, CI étendue — **sans encore aucune logique métier clinique** (c'est la Phase B qui suit).

STATUS : **PASS** — gate franchie. `docker compose up` + `pytest` vérifiés de bout en bout sur cette machine (Docker Desktop, moteur linux).

---

## 1. Périmètre livré

### Socle infrastructure
- `docker-compose.yml` : `postgres` (pgvector/pgvector:pg16 + script d'init `pi_app`), `redis:7`, `rabbitmq:3.13`, `otel-collector` (profil `observability`, non démarré par défaut), `mailpit`, `api`. Healthchecks partout. Ports hôte décalés (`55432`, `56379`, …) pour cohabiter avec d'autres stacks.
- `server/Dockerfile` : Python 3.12-slim, utilisateur non-root, healthcheck liveness.
- `ops/postgres-init.d/01-app-role.sql` : crée le rôle applicatif `pi_app` (`NOSUPERUSER NOBYPASSRLS`) + `ALTER DEFAULT PRIVILEGES`.
- `ops/otel-collector-config.yaml` : pipeline traces/metrics/logs avec processeur de redaction (TV-12).
- `.env.example`, `.dockerignore`, `.gitignore` étendu.

### `server/` — API (monolithe modulaire, couches api → application → domain → infrastructure)
- `app/core/config.py` — `Settings` via `pydantic-settings`, préfixe `PI_`.
- `app/core/db.py` — moteur async SQLAlchemy 2 + `tenant_session()` / `system_session()`. **RLS positionnée par `set_config('app.current_organization', …, is_local=true)`** en début de transaction (`SET` ne prend pas de paramètre lié — `set_config` si). `NullPool` en environnement `testing` (boucle par test pytest-asyncio).
- `app/core/redis.py` — client async + **rate limiter distribué** (script Lua fenêtre glissante), remplace le limiteur en mémoire de la v1 (TH-10).
- `app/core/security.py` — **Argon2id** (remplace PBKDF2, TH-01 ; coût réduit en `testing`), jetons de session opaques (SHA-256 stocké), comparaison à temps constant, TOTP RFC 6238 stdlib.
- `app/core/crypto.py` — chiffrement applicatif par champ (Fernet ; clé dérivée du signing key — **limite Phase 2 assumée**, KMS requis en prod).
- `app/core/errors.py` — hiérarchie `DomainError` + handlers **RFC 9457** (`application/problem+json`), aucune stack trace / SQL / chemin interne exposé.
- `app/core/logging.py` — `structlog` JSON + **filtre de redaction** (mots de passe, jetons, contenu clinique, `about_me`, réponses PHQ-9 jamais journalisés — TH-09).
- `app/core/observability.py` — OpenTelemetry (traces) ; no-op en `testing`, désactivable par `PI_OTEL_ENABLED`.
- `app/core/context.py` — `Principal` (dérivé du jeton, jamais du corps de requête).
- `app/infrastructure/models.py` — 9 tables : `organizations` (globale), `clinics`, `users`, `sessions`, `roles`/`permissions`/`role_permissions` (globales), `user_roles`, `audit_logs`.
- `app/alembic/versions/0001_foundation.py` — DDL explicite ; **RLS activée + `FORCE ROW LEVEL SECURITY`** sur les 5 tables de tenant ; `audit_logs` append-only (politiques SELECT + INSERT seulement — pas d'UPDATE/DELETE hors bypass) ; seed des **8 rôles RBAC** (`PATIENT`…`SUPER_ADMIN`) et de leurs permissions. `downgrade` complet (réversibilité vérifiée en CI).
- `app/application/` — `audit.record()` (métadonnées filtrées), `rbac` (`require_role`, `require_permission`, `permissions_for_roles`, deny-by-default), `auth_service` (register patient, authenticate + **MFA obligatoire pour les rôles cliniques**, resolve principal, revoke).
- `app/api/` — `health` (`/health/live` sans dépendance DB, `/health/ready` avec DB+Redis), `auth` (`POST /api/v1/auth/register|sessions|logout`, `GET /api/v1/me`), middleware `request_id` + log d'accès structuré + **en-têtes de sécurité sur toutes les réponses** (repris v1 SEC-002), CORS sans credentials (jeton Bearer, jamais de cookie — TH-12).
- `app/main.py` — app factory FastAPI, OpenAPI généré (6 opérations).
- `server/scripts/bootstrap.py` — création idempotente organisation + compte privilégié.

### Tests (`server/tests/`, pytest + httpx ASGI) — **28 tests, 87 % de couverture**
- `test_health.py` (4) — liveness, readiness, en-têtes de sécurité, 404 en `problem+json`.
- `test_auth.py` (11) — register→login→me, 401 générique, indistinguabilité e-mail inconnu / mauvais mot de passe, anti-énumération de comptes, révocation de session, jeton trafiqué, absence de cookie, **champ `role` injecté ignoré**, organisation inconnue → 404, **login clinicien exige TOTP**.
- `test_tenant_isolation.py` (5) — **RLS masque les lignes d'une autre organisation**, écriture cross-org bloquée par `WITH CHECK`, pas de fuite de GUC entre connexions du pool, audit scopé en lecture, contexte de tenant absent → 0 ligne (**TV-01**).
- `test_core_units.py` (8) — Argon2 aller-retour + rehash, hash de jeton, temps constant, TOTP, chiffrement de champ (aller-retour + falsification), `require_role` refuse l'accès clinique à un `PATIENT`, résolution des permissions RBAC seedées.

### CI
- `.github/workflows/ci-v2.yml` — job `server` (services `postgres` + `redis`, création du rôle `pi_app`, ruff, mypy, `alembic upgrade head`, **`downgrade base && upgrade head`**, pytest + coverage 85 %, bandit, pip-audit) ; job `compose-smoke` (`docker compose up` + `/health/ready` + bootstrap).
- Le workflow v1 (`.github/workflows/ci.yml`) est **inchangé**.

## 2. Résultats de vérification (exécutés sur cette machine)

| Contrôle | Résultat |
| --- | --- |
| `docker compose up` (postgres, redis, api) | api **healthy** ; `/health/live` → `{"status":"live"}` ; `/health/ready` → `{"status":"ready"}` |
| `alembic upgrade head` | OK |
| `alembic downgrade base && alembic upgrade head` | OK (réversible) |
| `pytest` | **28 passed** |
| `coverage report` | **87 %** (seuil 85 %) |
| `ruff check .` | All checks passed |
| `mypy app` | Success: no issues found in 24 source files |
| `bandit -r app scripts` | aucun problème |
| `pip-audit` | **No known vulnerabilities found** (stack alignée sur les versions d'août 2026) |
| `scripts.bootstrap` | crée org + admin + rôle, idempotent |

## 3. Ce qui n'est PAS fait (et pourquoi)

- **Pas de worker RabbitMQ** : broker dans la stack, URL configurée, mais aucun consommateur (rien à traiter avant la Phase 5). L'API ne dépend pas de RabbitMQ au démarrage. TV-10 reste `PLANIFIÉ`.
- **Pas d'enrôlement MFA** : `authenticate` **exige** un TOTP valide pour les rôles cliniques, mais l'endpoint qui génère le secret/QR arrive en Phase 3. Un compte clinicien créé par `bootstrap.py` ne peut donc pas encore se connecter — attendu, documenté.
- **Couverture `auth_service.py` à 54 %** (chemins non testés : audit d'échec MFA, rehash de mot de passe, cas limites de `resolve_principal`, `revoke`, `IntegrityError`). Le total (87 %) passe la gate ; dette explicite à combler en Phase B/3 quand ces chemins seront exercés par des tests de bout en bout.
- **`disallow_untyped_defs` mypy** désactivé temporairement (à réactiver une fois la base stabilisée).
- **Chiffrement de champ** : clé dérivée de `PI_JWT_SIGNING_KEY`, pas un KMS (limite Phase 2 assumée, notée dans `crypto.py`).
- **otel-collector** : image contrib refuse de s'exécuter sur cette machine (`exec /otelcol-contrib: no such file or directory` — probable incompatibilité binaire Docker Desktop) ; placée derrière le profil `observability`, non bloquante (l'API tolère un collector injoignable). À réévaluer en Phase 15 (observabilité).
- **v1 intacte** : `backend/` et `frontend/` non touchés (strangler pattern, ADR-006).

## 4. Vulnérabilités / menaces adressées (vérifiées par test)

| Menace | Traitement | Test |
| --- | --- | --- |
| **TV-01** (fuite inter-tenant) | RLS + `FORCE ROW LEVEL SECURITY` + rôle `pi_app` `NOBYPASSRLS` + `tenant_session` | `test_tenant_isolation.py` (5) — **VÉRIFIÉ** |
| TH-01 (credential stuffing) | Argon2id, rate limit distribué login | `test_core_units.py`, `test_auth.py` |
| TH-09 (logs sensibles) | filtre de redaction structlog + processeur OTel | revue de code + filtre testé indirectement |
| TH-10 (DoS) | rate limiter distribué Redis | `test_auth.py` (indirect), à renforcer Phase 10 |
| TH-12 (CSRF) | jeton Bearer, `allow_credentials=False`, aucun cookie | `test_auth.py::test_login_response_never_sets_a_cookie` |
| v1 SEC-002 (en-têtes) | CSP/HSTS/Permissions-Policy/X-* sur toutes les réponses | `test_health.py::test_security_headers_on_every_response` |
| privilege escalation (champ `role`) | schéma Pydantic strict, rôle `PATIENT` forcé à l'inscription | `test_auth.py::test_role_field_in_body_is_ignored` |

## 5. Décisions techniques de la phase

- **Rôle PostgreSQL à moindre privilège (`pi_app`)** : l'app se connecte avec un rôle `NOSUPERUSER NOBYPASSRLS` ; les migrations avec le propriétaire (`pi`). Sans ça, la RLS serait contournée en silence (les superusers ignorent RLS même avec `FORCE`). Le « bypass » contrôlé (`system_session`) passe par le paramètre de session `app.bypass_rls`, jamais par un attribut de rôle.
- **`set_config(..., is_local=true)`** au lieu de `SET LOCAL` (ce dernier n'accepte pas de paramètre lié).
- **`NullPool` + coût Argon2 réduit + OTel no-op** en environnement `testing` : pytest-asyncio recrée une boucle par test (un pool lierait ses connexions à la première).
- **`email-validator`** actif : les e-mails en `.test` sont refusés (TLD réservé) — les fixtures utilisent `*.example.com`.
- Stack alignée sur les versions d'août 2026 (fastapi 0.141, sqlalchemy 2.0.52, cryptography 50, pyjwt 2.13, pytest 9.1, …) — `pip-audit` propre.

## 6. Comment reproduire

```bash
docker compose up -d postgres redis
docker compose run --rm --no-deps api alembic upgrade head
docker compose run --rm --no-deps api sh -c "ruff check . && mypy app && bandit -r app scripts -q && pip-audit && coverage run -m pytest && coverage report"
docker compose up -d api && curl -s localhost:8000/health/ready
docker compose run --rm --no-deps api python -m scripts.bootstrap --org-slug demo --org-name Demo --email admin@demo.example.com --password 'change-me-123456' --role ADMIN
```

## 7. Critères de sortie — Gate Phase 2

- [x] Socle FastAPI en couches.
- [x] PostgreSQL + Alembic + RLS multi-tenant, réversible.
- [x] Redis (rate limiting distribué).
- [x] RabbitMQ dans la stack (consommateurs en Phase 5).
- [x] OpenTelemetry câblé.
- [x] Docker Compose fonctionnel.
- [x] Auth + RBAC (8 rôles) + audit.
- [x] Health checks (liveness sans DB, readiness avec DB+Redis).
- [x] CI étendue écrite (2 jobs).
- [x] `docker compose up` fonctionne.
- [x] `pytest` vert (28), couverture 87 % ≥ 85 %.
- [x] ruff + mypy + bandit + pip-audit propres.
- [x] Migrations réversibles.
- [x] Tests d'isolation de tenant (TV-01) verts.

## 8. Conclusion

Le socle Phase 2 est en place, exécuté et vérifié de bout en bout : la stack V2 démarre, la RLS multi-tenant isole réellement (rôle à moindre privilège), l'authentification et l'audit fonctionnent, la CI couvre lint/types/tests/sécurité/migrations/fumée. Aucune logique métier clinique n'a encore été portée — c'est l'objet de la **Phase B** : porter le cœur de sûreté v1 (`crisis.py`, `policy.py`, `pipeline.py`, `alerts.py`, `responder.py`) dans `server/app/`, avec ses tests d'invariants **écrits en premier**, puis retirer le code v1 correspondant une fois la parité atteinte.

STATUS : **PASS** — prêt pour la Phase B.
