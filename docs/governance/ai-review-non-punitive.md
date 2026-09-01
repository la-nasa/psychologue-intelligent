# Revue clinicienne de l'IA — usage non punitif

_Gouvernance — Phase 14. S'applique à `app/application/ai_review.py`, la table
`clinician_response_reviews` et les endpoints `/api/v1/clinician/ai-review/*`._

## Principe

Les revues qu'un clinicien produit sur les réponses de l'assistant
(`APPROVE` / `EDIT` / `REJECT` / `FLAG_SAFETY`, notes 1–5, catégorie de retour,
correction proposée, commentaire) servent **exclusivement** à :

1. mesurer la qualité de l'IA (taux d'approbation, notes moyennes par dimension,
   répartition des catégories de retour) **par version de modèle** ;
2. constituer un signal d'amélioration (corrections proposées, drapeaux
   sécurité) pour les phases d'apprentissage (16) et de politique (9).

Elles **ne doivent jamais** servir à :

- évaluer, classer, noter ou sanctionner un clinicien ;
- alimenter un entretien d'évaluation, une décision RH, une mesure de
  productivité individuelle ;
- comparer des cliniciens entre eux.

## Garanties techniques

| Garantie | Mise en œuvre | Vérifié par |
| --- | --- | --- |
| Aucune agrégation par relecteur exposée | Aucune fonction de `ai_review.py` ne groupe/filtre par `reviewer_id` à des fins de statistiques ; `model_quality_report` agrège par `model_version` / `decision` / `feedback_category` / dimension. | `tests/test_ai_review.py::test_module_exposes_no_per_reviewer_aggregation`, `::test_quality_report_carries_no_reviewer_identity` |
| Le rapport qualité ne contient aucun identifiant de relecteur | La sortie de `model_quality_report` n'a que des compteurs et des moyennes. | idem |
| L'audit ne cadre pas la revue comme une performance individuelle | `ai_review.submit` journalise `decision` + `feedback_category` + `model_version` ; jamais de score agrégé par personne. | revue de code |
| `FLAG_SAFETY` ne modifie jamais automatiquement une politique de crise | `list_safety_flags` est en lecture seule ; le moteur de crise reste indépendant (invariant Phase 7/9). | `tests/test_ai_review.py::test_safety_flag_is_recorded_and_listed` |

## Accès

- Soumettre / lire une revue : `PSYCHOLOGIST` ou `CLINICAL_SUPERVISOR`, **et** relation `ACTIVE` avec le patient concerné.
- Rapport qualité IA : `CLINICAL_SUPERVISOR` ou `SUPER_ADMIN`.
- Liste des drapeaux sécurité : `CLINICAL_SUPERVISOR` ou `SUPER_ADMIN`.
