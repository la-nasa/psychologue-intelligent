# PHASE REPORT

Phase : 1 (V2) — Architecture détaillée, ADR, design system, threat model
Date : 2026-08-28
Objectif : Transformer les décisions D-1 à D-4 (Phase 0 V2) en une architecture cible détaillée, actée par ADR, avec un design system spécifié et un threat model étendu aux nouvelles frontières de confiance. **Aucun code applicatif.**

## 1. Objectif

Après validation par l'utilisateur des recommandations de `phase-0-audit-v2.md` (« go with your recommendations »), produire les artefacts de conception qui permettront à la Phase 2 de démarrer l'implémentation sans ambiguïté d'architecture :

- décisions structurantes tracées en ADR ;
- architecture cible détaillée (modules, ports, flux d'un message, orchestrateur, mémoire, safety) ;
- modèle de données PostgreSQL avec tenant et RLS ;
- design system Next.js spécifié (tokens, composants, états) ;
- threat model couvrant LLM externe, voix, multi-tenant, Redis/RabbitMQ, mémoire.

## 2. Décisions retenues (D-1 à D-4)

| # | Décision | Choix |
| --- | --- | --- |
| D-1 | Portée / rythme | **Cœur de sûreté d'abord** : migration + invariants portés et re-testés avant les fonctionnalités avancées |
| D-2 | Stratégie LLM | **Hybride** : petit modèle local (FAST) + API externe (DEEP) conditionnée à un consentement `AI_EXTERNAL` |
| D-3 | Modules | **Multi-tenancy dès la Phase 2** ; voix et MLflow complet plus tard |
| D-4 | Stack | **Stack V2 complète** (Next.js, FastAPI, PostgreSQL+pgvector, Redis, RabbitMQ, OTel) ; vLLM/Triton/K8s/DVC conditionnels |

## 3. Fichiers créés

- `docs/architecture/decision-records/ADR-006-v2-stack-adoption.md` — supersede ADR-003
- `docs/architecture/decision-records/ADR-007-hybrid-llm-strategy.md` — étend ADR-005
- `docs/architecture/decision-records/ADR-008-multi-tenancy.md`
- `docs/architecture/overview-v2.md` — architecture cible détaillée (15 sections)
- `docs/architecture/data-model-v2.md` — schéma PostgreSQL, tenant + RLS, mapping migration v1→v2
- `docs/design-system/v2-foundations.md` — tokens, inventaire de composants, états, a11y, responsive, i18n
- `docs/security/threat-model-v2.md` — 15 nouvelles menaces (TV-01…TV-15), OWASP LLM Top 10, NIST AI RMF
- `docs/reports/phase-1-architecture-v2.md` — ce rapport

## 4. Fichiers modifiés

- Aucun fichier de code. Aucun document v1 modifié (ADR-003 est marqué *superseded* **par** ADR-006, dans ADR-006 ; le fichier ADR-003 lui-même est laissé tel quel pour l'historique — à annoter d'un en-tête « Superseded by ADR-006 » en Phase 2 lors du premier commit de code).

## 5. Architecture impactée

Voir `docs/architecture/overview-v2.md`. Points structurants :

- **Monolithe modulaire conservé** (ADR-001 tient) : un déployable, frontières de module dans le code, extraction sur besoin démontré.
- **Séparation stricte transport / application / domaine / infrastructure** — la logique métier sort des routes (défaut majeur de la v1 où `http.py` mélange routage et décisions).
- **Safety Engine indépendant, exécuté avant tout LLM** — invariant v1 conservé et renforcé (chemin externe inclus).
- **Model Router FAST/DEEP** + port `LLMProvider` multi-adaptateurs — aucun couplage fournisseur.
- **Multi-tenant à 3 couches** : `organization_id` partout + RLS PostgreSQL + `TenantScopedRepository`.
- **9 invariants de sûreté** (6 repris de v1 + 3 nouveaux : pas de donnée ORANGE/RED vers l'externe ; DEEP exige consentement ; mémoire révoquée jamais réinjectée).

## 6. Fonctionnalités terminées

Aucune fonctionnalité produit (phase de conception). Livrables de conception terminés : ADR (3), architecture (1), modèle de données (1), design system (1), threat model (1).

## 7. Tests exécutés

Aucun (pas de code). La suite v1 reste verte et inchangée.

## 8. Résultats des tests

Sans objet.

## 9. Bugs détectés / corrigés

Aucun (pas de code). Défauts de conception v1 identifiés et adressés dans la cible :
- logique métier dans les routes → couches App/Domain/Infra ;
- rate limiting en mémoire non distribué → Redis ;
- pas d'observabilité → OTel dès Phase 2 ;
- tout le texte frontend en français en dur → i18n dès Phase 2 ;
- cas résiduel TM-08 (notification orpheline) → outbox transactionnelle stricte.

## 10. Vulnérabilités détectées

15 menaces nouvelles cataloguées (`threat-model-v2.md` TV-01…TV-15), toutes au statut `PLANIFIÉ` avec un test nommé à livrer dans la phase qui implémente le composant concerné. Les plus critiques :
- TV-01 fuite inter-tenant ;
- TV-02 exfiltration vers LLM externe sans consentement / au-delà du nécessaire ;
- TV-05 mémoire révoquée réinjectée ;
- TV-06 sortie LLM non sûre (diagnostic, fausse réassurance) ;
- TV-08 rétention abusive d'audio voix ;
- TV-15 promotion de modèle non approuvée.

## 11. Vulnérabilités corrigées

Aucune (pas de code). Les mitigations sont des exigences de conception intégrées à l'architecture cible, pas des contrôles implémentés.

## 12. Dette technique

- ADR-003 à annoter d'un en-tête « Superseded » au premier commit Phase 2.
- Le design system est spécifié, pas implémenté (Phase 2).
- Le threat model V2 doit être maintenu synchrone du code à **chaque** phase (règle de projet v1 conservée).
- Coût d'infrastructure V2 (Postgres, Redis, RabbitMQ, OTel, API LLM externe) : à chiffrer avant Phase 2 (R-10).
- Choix précis de l'`EmbeddingModel` et du petit modèle local FAST : à trancher en Phase 2 / Phase 5 sur mesure réelle.

## 13. Décisions techniques (résumé, détail dans les ADR)

- Stack V2 adoptée, ADR-003 superseded (ADR-006).
- LLM hybride, consentement `AI_EXTERNAL` séparé et révocable comme condition du chemin externe (ADR-007).
- Multi-tenant hiérarchique org→clinique→clinicien→patient, isolation par RLS + `organization_id` + repository scopé (ADR-008).
- Monolithe modulaire conservé ; séparation transport/app/domaine/infra.
- Argon2id remplace PBKDF2 dès la Phase 2 (dépendance désormais permise).
- Rate limiting distribué Redis ; outbox transactionnelle stricte pour les notifications.
- i18n fr/en dès la Phase 2, chaînes externalisées à 100 %.

## 14. Risques restants

Repris du registre Phase 0 (R-01…R-13), inchangés. Nouveaux points d'attention issus de la Phase 1 :
- **R-02 (scope)** reste le risque dominant : la roadmap par gates est le seul garde-fou ; aucune phase livrée « à moitié ».
- **R-10 (coût infra)** : à chiffrer avant d'engager la Phase 2.
- La qualification réglementaire (AI Act, produit probablement « haut risque ») exige un conseil juridique — hors périmètre de l'agent, à porter par l'utilisateur.
- Aucune validation clinique : inchangé, bloquant pour un déploiement avec de vrais patients, jamais pour l'implémentation.

## 15. Métriques

- 3 ADR, 5 documents d'architecture/sécurité/design, 1 rapport.
- 9 invariants de sûreté formalisés (6 repris + 3 nouveaux).
- 15 menaces V2 cataloguées, 0 vérifiée (attendu à ce stade).
- ~20 modules de domaine délimités avec leurs dépendances autorisées.
- 0 ligne de code applicatif produite ou modifiée.

## 16. Critères de sortie — Gate Phase 1

- [x] Décisions D-1 à D-4 tracées en ADR.
- [x] Architecture cible détaillée (modules, ports, flux, orchestrateur, mémoire, safety, temps réel, déploiement, structure de dépôt).
- [x] Modèle de données PostgreSQL avec tenant + RLS + mapping depuis v1.
- [x] Design system spécifié : tokens, inventaire, états obligatoires, a11y WCAG 2.2 AA, responsive, i18n, mode sombre.
- [x] Threat model étendu : nouvelles frontières de confiance, OWASP LLM Top 10, NIST AI RMF, chaque menace avec un test nommé à livrer.
- [x] Invariants de sûreté v1 repris et complétés.
- [x] Aucun code produit.
- [ ] **Revue humaine du design system et validation du budget infra** — recommandé avant d'engager la Phase 2 (non bloquant pour préparer le socle, bloquant pour provisionner de l'infra payante).

## 17. Conclusion

L'architecture cible est posée et tracée. Les trois décisions structurantes sont actées en ADR, le modèle de données est prêt à être écrit en Alembic, le design system est spécifié au niveau où un ingénieur front peut commencer, et le threat model couvre les six nouvelles surfaces (tenant, LLM externe, voix, mémoire, cache, messaging) avec un test nommé pour chacune.

La Phase 2 (Fondation) peut démarrer : socle FastAPI + PostgreSQL + Alembic + Redis + RabbitMQ + OTel + Docker Compose + auth/RBAC/audit multi-tenant + CI étendue. Elle ne porte encore aucune logique métier — c'est la Phase B (portage du cœur de sûreté) qui suit, avec les tests d'invariants portés **en premier**.

STATUS : **PASS** — prêt pour la Phase 2, sous réserve de la revue design + budget infra (point 16, non bloquant pour commencer le socle).
