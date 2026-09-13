# ADR-014 — Architecture multi-tenant par schéma PostgreSQL (schema-per-organization)

Date : 2026-09-13
Statut : **REJETÉ — contredit [ADR-008](ADR-008-multi-tenancy.md), déjà accepté, implémenté et testé.**
Origine : audit indépendant mené sur la branche `intelligent-psychologist-bdc4b`, fusionné via PR #1. Renuméroté ADR-014 (était `docs/adr/ADR-011-multi-tenancy-architecture.md`, statut d'origine « PROPOSED »).

## Note de réconciliation (2026-09-13) — IMPORTANT

Cette proposition (« Schema-per-Organization + RLS », un schéma PostgreSQL `org_{uuid}` par organisation, `SET search_path`) a été produite sans connaissance de l'état réel de `server/`, où le multi-tenancy est **déjà implémenté** selon une approche différente : `organization_id` + RLS sur schéma unique ([ADR-008](ADR-008-multi-tenancy.md), 11 migrations, `server/tests/test_tenant_isolation.py`).

Plus significatif : **ADR-008 a explicitement examiné et écarté cette même option** sous le nom « Schéma PostgreSQL par organisation », avec la justification suivante (citée telle quelle) : *« intermédiaire, mais complexifie les migrations et le pooling sans apporter beaucoup plus que la RLS pour ce contexte »*. Ce document ADR-014 arrive donc à la conclusion inverse d'ADR-008 sur le même choix, sans le citer ni le réfuter.

**Conséquence pratique** : basculer vers ce schéma nécessiterait de réécrire les 11 migrations Alembic existantes, le middleware de tenant (`TenantContext`/RLS), et de re-passer toute la suite `test_tenant_isolation.py` — un coût de migration majeur pour un gain non démontré, et contraire à la règle du Prompt Maître §128 (« Ne détruis rien. Ne réécris rien sans nécessité »).

**Ce document est conservé ci-dessous pour traçabilité uniquement. Ne pas implémenter sans une nouvelle décision explicite de l'utilisateur qui rouvre spécifiquement ADR-008.**

## Contenu original (inchangé)

### Status d'origine
PROPOSED

### Contexte
Le Prompt Maître (§69) exige une architecture multi-tenant dès la conception pour supporter plusieurs organisations, l'isolation stricte des données cliniques, la conformité RGPD, la scalabilité horizontale.

### Décision d'origine
**Architecture hybride : Schema-per-Organization + Row Level Security (RLS)**

```text
PostgreSQL
├── schema: public
│   ├── organizations (id, name, slug, created_at, status)
│   └── users (id, organization_id, email, password_hash, roles)
│
├── schema: org_{uuid}
│   ├── patients
│   ├── conversations
│   ├── messages
│   ├── memories
│   ├── alerts
│   ├── assessments (PHQ-9)
│   ├── goals
│   └── clinician_notes
```

### Middleware Tenant Resolution
1. Extraire `organization_id` du JWT token
2. Valider que l'utilisateur appartient à cette organisation
3. Définir le schema PostgreSQL via `SET search_path TO org_{id}, public`
4. Ajouter `organization_id` au contexte de requête pour audit

### Alternatives considérées dans le document d'origine
- Database-per-Organization : rejetée (coût infra élevé, migrations complexes)
- Discriminator Column (`organization_id` sur chaque table) : rejetée par ce document (« risque de fuite si WHERE oublié ») — **c'est pourtant exactement l'approche qu'ADR-008 a retenue, avec RLS en filet de sécurité au niveau moteur plutôt qu'au niveau applicatif, ce qui répond directement à l'objection soulevée ici.**
- Schema-per-Organization : choisie par ce document.

## Références (document d'origine)
- Prompt Maître §69, §67, §63
- OWASP ASVS V2.10
