# ADR-006 — Adoption de la stack « V2 » et fin d'ADR-003

Date : 2026-08-28
Statut : **Accepté**. Supersede **ADR-003** (« Fondation sans dépendance réseau »).
Décideur : utilisateur (réponse « go with your recommendations » du 2026-08-28, sur la base de `docs/reports/phase-0-audit-v2.md` Section 11, décision D-4).

## Contexte

ADR-003 (2026-08-24) actait une fondation en bibliothèque standard Python seule, **parce que l'environnement de l'époque ne pouvait ni résoudre ni joindre PyPI/npm**. C'était une contrainte subie, pas un choix d'architecture : ADR-003 lui-même prévoyait explicitement que « la phase de déploiement devra sélectionner et tester PostgreSQL, une limite distribuée et une gestion de secrets avant pilote ».

Le Prompt Maître V2 (2026-08-28) demande une plateforme conversationnelle multimodale : conversation naturelle streamée, mémoire sémantique, personnalisation, voix temps réel, supervision clinique outillée, MLOps, observabilité. `docs/reports/phase-0-audit-v2.md` a mesuré 23 écarts (G-01 à G-23) entre l'existant et cette cible. Aucun de ces écarts ne se comble en restant sur `wsgiref` + SQLite + JS vanilla.

## Décision

Adopter la stack suivante comme socle du projet. ADR-003 est **superseded** : ajouter une dépendance runtime n'est plus un écart à justifier au cas par cas, c'est le mode de fonctionnement normal — mais chaque dépendance reste soumise à `pip-audit`/`npm audit` en CI et à une justification dans le rapport de phase qui l'introduit.

### Socle retenu (attendu, non négociable pour la cible V2)

| Couche | Choix | Rôle |
| --- | --- | --- |
| Frontend | Next.js 16 (App Router, RSC), React 19.2, TypeScript strict, Tailwind CSS, shadcn/ui + Radix, TanStack Query, Zod, React Hook Form, Recharts | 3 surfaces : patient, clinicien, admin |
| API | FastAPI, Pydantic v2, OpenAPI généré, SSE + WebSockets | REST `/api/v1/*`, temps réel `/ws/*` |
| Accès données | SQLAlchemy 2 (core + ORM), Alembic, asyncpg | migrations, sessions async |
| Base transactionnelle | PostgreSQL 16 | **source de vérité unique** de toute donnée clinique |
| Vecteurs | pgvector (extension PostgreSQL) | mémoire sémantique, retrieval, RAG |
| Cache / état éphémère | Redis 7 | cache, presence, locks, rate limiting distribué, état de session technique, coordination d'événements |
| Messaging | RabbitMQ | jobs asynchrones hors chemin critique (embeddings, résumés, analytics, notifications) |
| Observabilité | OpenTelemetry SDK → Prometheus + Grafana + Loki + Tempo | traces, métriques, logs corrélés |
| Conteneurisation | Docker + Docker Compose | environnement dev/test/staging reproductible |
| CI | GitHub Actions (étend l'existant) | lint, typecheck (back + front), tests, coverage, SAST, DAST, scans deps/secrets/conteneurs, éval IA |

### Conditionnel (introduit seulement sur besoin démontré et mesuré — règles 10 et 93 du prompt maître)

- **vLLM / NVIDIA Triton** : uniquement si un modèle auto-hébergé sur GPU dédié est retenu (voir [ADR-007](ADR-007-hybrid-llm-strategy.md)) et si plusieurs modèles doivent être mutualisés / le batching apporte une valeur mesurée.
- **Kubernetes / Helm** : uniquement à partir d'une charge ou d'un besoin de résilience que Docker Compose + un orchestrateur simple ne couvrent plus. Pas dans le MVP.
- **DVC** (ou équivalent) : uniquement quand les datasets d'entraînement dépassent ce qu'un stockage objet versionné par hash gère proprement.
- **PostGIS** : uniquement si une fonctionnalité géographique réelle apparaît (aucune prévue).
- **Celery** : uniquement si le modèle de tâches de RabbitMQ seul devient insuffisant.

### Ce qui NE change PAS

Les invariants de sûreté d'ADR-002 et ADR-004 restent **strictement en vigueur et re-testés sur la nouvelle stack avant toute nouvelle fonctionnalité** :

1. Le moteur de crise est indépendant du LLM ; ORANGE/RED ne passent jamais par un modèle génératif.
2. Les politiques cliniques vivent hors du code, versionnées, bloquées tant que `approved_by` est nul.
3. Toute décision de risque référence les versions de politique, de règles et de modèle.
4. L'apprentissage continu exige consentement révocable + anonymisation + revue humaine + double approbation.
5. Les logs techniques ne contiennent jamais de contenu clinique brut ni de secret.
6. L'autorisation est vérifiée côté serveur, deny-by-default.

## Stratégie de transition

**Strangler pattern** (détaillé dans `docs/reports/phase-0-audit-v2.md` Section 7 et `docs/architecture/overview-v2.md`) :

- Le code stdlib/SQLite existant et son déploiement Railway restent la « démo v1 » et ne sont **pas supprimés** tant que leur remplacement n'est pas au moins à parité fonctionnelle et de test.
- Aucune donnée patient réelle n'existe → **migration de schéma uniquement, aucune migration de données**, aucun risque pour des personnes réelles.
- Le cœur de sûreté (`crisis.py`, `policy.py`, `pipeline.py`, `alerts.py`, `responder.py`) est porté et re-testé **en premier** (Phase B de la roadmap), avant les fonctionnalités nouvelles.

## Conséquences

- **Positif** : la cible V2 devient atteignable ; observabilité, résilience multi-instance, mémoire sémantique et temps réel deviennent possibles ; l'écosystème (FastAPI/Pydantic/SQLAlchemy) apporte validation, typage et doc générée « gratuitement ».
- **Négatif** : surface de dépendances et de configuration bien plus large ; coût d'infrastructure réel (Postgres, Redis, RabbitMQ, stack observabilité) ; environnement de dev désormais dépendant de Docker (certaines briques ML sont mal supportées nativement sous Windows — le dev se fait dans des conteneurs Linux, la CI est Linux).
- **Négatif** : la propriété « la suite de tests complète tourne sans aucune dépendance » d'ADR-003 est perdue. Contrepartie : `docker compose up` + `pytest` devient le contrat reproductible, vérifié en CI.
- **Risque** (R-02 du registre Phase 0) : le scope V2 peut dépasser la capacité de livraison. Mitigation : roadmap par gates, aucune phase livrée « à moitié », priorisation explicite avec l'utilisateur à chaque gate.

## Alternatives rejetées

- **Rester sur la fondation stdlib/SQLite et l'étendre** (option D-4c du Phase 0) : rejetée par l'utilisateur ; contredit la majeure partie du prompt V2 et rend la voix, la mémoire sémantique et le multi-instance structurellement hors d'atteinte.
- **Stack minimale FastAPI + Postgres + Next.js seulement** (option D-4b) : rejetée ; Redis et RabbitMQ sont nécessaires dès la Phase 2 pour le rate limiting distribué et le traitement hors chemin critique, et les ajouter après coup coûte plus cher que les poser dès le socle.
