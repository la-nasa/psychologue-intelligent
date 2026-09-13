# ADR-010 — Multi-tenancy dès Phase 2 (note redondante)

Date : 2026-09-13
Statut : **REDONDANT — voir [ADR-008](ADR-008-multi-tenancy.md)**. Aucune action requise.
Origine : audit indépendant mené sur la branche `intelligent-psychologist-bdc4b`, fusionné via PR #1. Renuméroté ADR-010 (était `docs/adr/ADR-006-to-010-stack-architecture.md` §2, portait le numéro ADR-007 dans son document d'origine — collision avec l'ADR-007 déjà accepté de ce dossier).

## Note de réconciliation (2026-09-13)

Cette proposition (isolation `organization_id` sur toutes les tables, RBAC scopé par organisation, secrets/config par organisation) est **déjà décidée, implémentée et testée** par [ADR-008](ADR-008-multi-tenancy.md) (2026-08-28) : `organization_id NOT NULL` sur chaque table de tenant + RLS PostgreSQL + `TenantScopedRepository`, vérifié par `server/tests/test_tenant_isolation.py`. Ce document est conservé tel quel ci-dessous uniquement pour la traçabilité de l'audit du 2026-09-13 (branche `intelligent-psychologist-bdc4b`), qui a été produit sans connaissance de l'état réel de `server/`. **Ne pas ré-implémenter.**

## Contenu original (inchangé)

### Contexte
Le système doit supporter plusieurs organisations (cliniques, hôpitaux, cabinets) avec isolation stricte des données.

### Décision
Implémenter le multi-tenancy dès la Phase 2 (Foundation) avec :

```text
Niveau d'isolation: Database-level isolation logique
Clé de partitionnement: organization_id sur toutes les tables
RBAC: Rôles scoped par organisation
Secrets: Séparés par organisation
Configuration: Par organisation
```

### Schéma d'isolation

```sql
organizations (id, name, slug, settings, created_at)
users (id, organization_id, email, role, ...)
patients (id, organization_id, user_id, ...)
conversations (id, organization_id, patient_id, ...)
alerts (id, organization_id, patient_id, ...)
...
```

### Middleware d'isolation
Chaque requête API valide :
1. Authentification utilisateur
2. Récupération organisation depuis token/session
3. Injection organization_id dans tous les queries
4. Vérification accès resource-specific

### Conséquences

Positives : isolation forte dès le début, pas de refactor majeur ultérieur, ready pour déploiement multi-cliniques, compliance facilitée (RGPD, HIPAA).
Négatives : complexité query accrue, tests plus élaborés, indexation supplémentaire requise.
