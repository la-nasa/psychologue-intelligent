# ADR-008 — Multi-tenancy dès la Phase 2 (organisation → clinique → clinicien → patient)

Date : 2026-08-28
Statut : **Accepté**.
Décideur : utilisateur (décision D-3 de `docs/reports/phase-0-audit-v2.md`).

## Contexte

Le Prompt Maître V2 (règle 69) demande de concevoir « dès le début » pour plusieurs établissements, avec isolation des données, même si un premier déploiement n'utilise qu'une organisation. La fondation v1 n'a aucune notion d'organisation : ajouter le multi-tenant après coup imposerait de toucher chaque table, chaque requête et chaque test.

Comme la migration vers PostgreSQL réécrit de toute façon toute la couche d'accès données (ADR-006), c'est le moment le moins cher pour poser le tenant.

## Décision

**Modèle de tenant hiérarchique, isolation par `organization_id` partout, appliquée par une couche transverse — pas laissée à la discipline de chaque requête.**

### Hiérarchie

```text
Organization        (l'établissement / le client — la frontière d'isolation)
   └── Clinic        (un site, un service ; optionnel — une org peut n'avoir qu'une clinique implicite)
        └── Clinician (rattaché à une ou plusieurs cliniques de son organisation)
             └── Patient (rattaché à une organisation ; suivi par des cliniciens de cette organisation)
```

- `Patient` et `Clinician` appartiennent à **exactement une** `Organization`.
- Une relation `patient_clinician_relationship` ne peut lier qu'un patient et un clinicien **de la même organisation** (contrainte vérifiée en base et en application).
- `ADMIN` est rattaché à une organisation. `SUPER_ADMIN` (rôle plateforme) est le seul à opérer cross-organisation, pour l'exploitation uniquement, avec audit renforcé.

### Mise en œuvre de l'isolation (défense en profondeur, 3 couches)

1. **Schéma** : toute table portant de la donnée de tenant a une colonne `organization_id NOT NULL` avec clé étrangère. Les tables réellement globales (catalogue de rôles/permissions, versions de politique de crise, registre de modèles plateforme) n'en ont pas et sont documentées comme telles.
2. **PostgreSQL Row-Level Security (RLS)** : politiques `RLS` sur les tables de tenant, filtrant sur `current_setting('app.current_organization')`. La session applicative pose ce paramètre à partir du contexte de requête authentifié, avant toute requête métier. Une requête sans contexte de tenant ne voit rien (deny-by-default au niveau du moteur, pas seulement de l'ORM).
3. **Couche application** : un `TenantContext` dérivé du jeton à chaque requête ; un `TenantScopedRepository` de base qui injecte le filtre ; revue de code interdisant l'accès direct à une session non scopée hors d'un petit nombre de chemins explicitement globaux.

### Tests d'isolation obligatoires à chaque phase (critère d'acceptation transverse, Phase 0 Section 9)

- Un utilisateur de l'organisation A ne peut lire/écrire aucune ressource de l'organisation B (patient, conversation, alerte, PHQ-9, feedback, dataset…).
- Un `ADMIN` de A ne voit pas les utilisateurs de B.
- Une relation patient-clinicien cross-organisation est refusée.
- Un jeton sans `organization_id` (forgé, ancien schéma) est rejeté.
- Les identifiants étant des UUID non devinables, l'énumération ne suffit pas — mais l'isolation ne doit pas *reposer* sur la non-devinabilité (BOLA classique).

## Conséquences

- **Positif** : passer d'un à plusieurs établissements ne demande pas de réécriture ; l'isolation est vérifiée par le moteur de base, pas seulement par le code.
- **Positif** : la RLS PostgreSQL fournit un filet même si une requête applicative oublie le filtre (défense en profondeur réelle).
- **Négatif** : chaque migration, chaque requête et chaque fixture de test porte désormais un tenant ; légère surcharge cognitive constante.
- **Négatif** : la RLS complexifie le debug de requêtes (une ligne « manquante » peut être une ligne filtrée) → helper de test qui exécute en `SET LOCAL app.bypass_rls` sous un rôle de superviseur dédié, jamais accessible à l'API.
- **Risque R-05** : fuite inter-tenant. Mitigation : les 3 couches ci-dessus + la suite de tests d'isolation exécutée à chaque phase.

## Alternatives rejetées

- **Base de données par organisation** : isolation la plus forte, mais coût opérationnel (migrations × N, connexions × N, sauvegardes × N) disproportionné pour un pilote et les premières organisations. Reste une trajectoire possible pour un très gros client sous exigence contractuelle — le code scopé par `organization_id` n'empêche pas ce basculement ultérieur.
- **Schéma PostgreSQL par organisation** : intermédiaire, mais complexifie les migrations et le pooling sans apporter beaucoup plus que la RLS pour ce contexte.
- **Filtrage applicatif seul (pas de RLS)** : rejeté — un seul `WHERE` oublié = fuite clinique cross-établissement. Inacceptable pour cette classe de données.
