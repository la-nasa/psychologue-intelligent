# ADR-011: Multi-Tenancy Architecture

## Status
PROPOSED

## Context
Le Prompt Maître (§69) exige une architecture multi-tenant dès la conception pour supporter :
- Plusieurs organisations (cliniques, hôpitaux, cabinets)
- Isolation stricte des données cliniques
- Conformité RGPD (data residency, suppression par organisation)
- Scalabilité horizontale

## Décision
**Architecture hybride: Schema-per-Organization + Row Level Security (RLS)**

### Schéma d'isolation
```
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
Chaque requête HTTP/WebSocket doit :
1. Extraire `organization_id` du JWT token
2. Valider que l'utilisateur appartient à cette organisation
3. Définir le schema PostgreSQL via `SET search_path TO org_{id}, public`
4. Ajouter `organization_id` au contexte de requête pour audit

### Invariants de Sécurité
1. **Jamais de jointure cross-schema** sauf tables publiques (`organizations`, `users`)
2. **Toujours vérifier `organization_id`** côté serveur, jamais faire confiance au client
3. **RLS activé** même avec isolation schema (défense en profondeur)
4. **Audit logging** inclut toujours `organization_id`

## Alternatives Considérées

### Option 1: Database-per-Organization
**Avantages:**
- Isolation physique totale
- Backup/restore indépendant
- Data residency facile

**Inconvénients:**
- Coût infrastructure élevé (N bases de données)
- Migrations complexes (N bases à mettre à jour)
- Connection pooling inefficace
- Monitoring fragmenté

**Rejeté car:** Trop coûteux pour MVP, complexité opérationnelle excessive.

### Option 2: Discriminator Column (organization_id sur chaque table)
**Avantages:**
- Simple à implémenter
- Requêtes SQL standards
- Une seule base de données

**Inconvénients:**
- Risque de fuite si WHERE oublié
- Performance (index plus larges)
- Audit complexe
- Moins conforme RGPD (données mélangées)

**Rejet car:** Risque de fuite cross-tenant inacceptable pour données cliniques.

### Option 3: Schema-per-Organization (choisie)
**Avantages:**
- Isolation forte au niveau DB
- Backup possible par organisation
- Performance (schemas plus petits)
- Migrations gérables (Alembic supporte)
- Conforme RGPD (suppression = DROP SCHEMA)

**Inconvénients:**
- Complexité migrations (créer schema par org)
- Connection pool par schema nécessaire
- Requêtes dynamiques (search_path)

**Accepté car:** Meilleur compromis isolation/coût/conformité.

## Conséquences

### Positives
✅ Isolation clinique forte (requirement Prompt Maître §69)  
✅ Compliance RGPD facilitée (data minimization, suppression)  
✅ Performance acceptable (schemas < 1GB typiquement)  
✅ Backup différentiel possible  

### Négatives
⚠️ Complexité accrue des migrations Alembic  
⚠️ Need script création organisation (schema + tables)  
⚠️ Connection pooling plus complexe (search_path)  
⚠️ Tests penetration obligatoires avant production  

### Requirements Impacts
- **Prompt Maître §67 (RBAC):** Rôles scoped à organisation
- **Prompt Maître §68 (Audit):** Logs incluent organization_id
- **Prompt Maître §69 (Multi-Tenancy):** Isolation testée E2E
- **Prompt Maître §95 (Secrets):** Secrets par organisation si nécessaire

## Implementation Plan

### Phase 2.1: Core Multi-Tenancy
1. Table `organizations` (schema public)
2. Middleware `TenantMiddleware` (extraction JWT → search_path)
3. Service `OrganizationService` (création, activation, suspension)
4. Migration Alembic pour schema template

### Phase 2.2: Testing & Security
1. Tests unitaires isolation (cross-org = forbidden)
2. Tests integration (requêtes concurrentes org A/B)
3. Penetration testing (tentative fuite cross-schema)
4. Audit code review

### Phase 2.3: Operations
1. Script backup par organisation
2. Script restore schema
3. Monitoring queries lentes par schema
4. Documentation runbook

## References
- Prompt Maître §69: Multi-Tenancy requirement
- Prompt Maître §67: RBAC scoped organisation
- Prompt Maître §63: Privacy Architecture
- ADR-006: Stack PostgreSQL + pgvector
- OWASP ASVS V2.10: Multi-tenancy security
