# Plan de rollback

Trois choses différentes peuvent avoir besoin d'un rollback dans ce projet : le code applicatif, le schéma de base de données, et un modèle d'IA déployé via le registre. Ce document couvre les trois séparément — les confondre est une source classique d'incidents.

## 1. Rollback du code applicatif

Le code n'a pas encore de mécanisme de déploiement réel (voir `production-readiness.md`) : à ce stade, un rollback de code signifie revenir à un commit ou tag Git antérieur.

```bash
git log --oneline                 # identifier le dernier commit sain
git revert <commit-problematique>  # préféré : garde l'historique, ne réécrit rien
```

Éviter `git reset --hard` sur une branche déjà partagée/déployée : cela réécrit l'historique et complique la coordination avec quiconque a déjà tiré les commits concernés.

Après un rollback de code, toujours revérifier :
```bash
python -m unittest discover -s tests -v
```
Un rollback qui ne repasse pas la suite de tests n'est pas terminé.

## 2. Rollback de schéma de base de données

**Limite assumée et documentée, pas cachée : les migrations de ce projet (`backend/app/db.py::MIGRATIONS`) sont uniquement à sens unique (« forward-only »). Il n'existe aucune migration descendante automatisée.**

En cas de besoin de revenir en arrière sur un changement de schéma :
1. Si le déploiement est encore en développement/pilote restreint : restaurer une sauvegarde antérieure du fichier de base SQLite (ou, en PostgreSQL de production, une sauvegarde/point-in-time-recovery). C'est pourquoi des sauvegardes testées sont listées comme obligatoires dans `production-readiness.md`, pas optionnelles.
2. Si la donnée créée après la migration doit être conservée : écrire une migration corrective explicite (une nouvelle entrée dans `MIGRATIONS`, jamais une modification d'une migration déjà appliquée — `db.py::migrate` s'appuie sur `schema_migrations` pour ne jamais rejouer une migration, donc modifier une migration existante après coup n'a aucun effet sur une base déjà migrée et ne fait que créer une divergence entre environnements).

Ne jamais éditer une entrée existante du tuple `MIGRATIONS` une fois qu'elle a été appliquée quelque part : c'est le principe même qui garantit `test_migration_is_idempotent`.

## 3. Rollback d'un modèle d'IA déployé

C'est le seul rollback qui est réellement automatisé et testé dans ce projet (Phase 8b) :

```bash
POST /api/v1/admin/learning/models/{id}/rollback
```

Exige que le modèle soit actuellement `DEPLOYED` ; fait passer son statut à `ROLLED_BACK`. Voir `tests/test_learning_pipeline.py` et `tests/test_e2e_journeys.py::LearningJourneyTest` pour la vérification.

**Limite assumée** : ceci ne fait que changer l'état du registre — il n'y a pas d'infrastructure de déploiement réelle à l'heure actuelle pour effectivement retirer un modèle du trafic (voir `production-readiness.md`). Avant qu'un vrai modèle ne soit un jour réellement servi en production, ce rollback devra aussi déclencher une action d'infrastructure réelle, pas seulement une mise à jour de base de données.

## 4. Rollback d'une politique clinique ou d'un gabarit de réponse

Les fichiers `config/policies/*.json` sont versionnés par leur propre champ `version` et par leur présence dans le dépôt Git. Un rollback consiste à :
1. Restaurer la version précédente du fichier via Git (`git checkout <commit-precedent> -- config/policies/crisis-policy-v1.json`).
2. Redémarrer l'application : `policy.py` charge et valide la politique au démarrage (voir ADR-002/ADR-004), donc une politique invalide ou non approuvée empêche le démarrage plutôt que de s'appliquer silencieusement.

## Ce qui n'est pas encore couvert

- Rollback automatisé de schéma (voir Section 2) : reste manuel, documenté comme tel.
- Aucun mécanisme de bascule de trafic (blue/green, canary) puisqu'aucune infrastructure de déploiement réelle n'existe encore.
