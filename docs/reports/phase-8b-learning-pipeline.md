# PHASE REPORT

Phase: 8b — Pipeline d'apprentissage continu (échantillonnage, anonymisation, revue humaine, dataset, registre de modèles)
Date: 2026-08-27
Objectif: Construire la chaîne complète Production → Échantillonnage → Filtre de confidentialité → Anonymisation → Revue humaine → Version de dataset → Registre de modèles avec double approbation clinique (Section 15 du prompt maître), en s'appuyant sur les conversations réelles et le modèle d'émotion livrés en Phase 8/8a.

## 1. Travaux réalisés

- **Correction d'un prérequis manquant** : il n'existait aucun moyen de révoquer un consentement (`AuthService.revoke_consent`, `POST /api/v1/consents/revoke`). Sans cela, la garde « seuls les patients avec un consentement d'apprentissage actif sont échantillonnés » aurait été invérifiable — un consentement aurait pu être accordé mais jamais retiré.
- Migration `009_continuous_learning` : `human_feedback`, `training_datasets`, `training_dataset_items`, `model_versions`, `model_approvals`.
- `backend/app/learning.py` :
  - `sample_and_queue_for_review` : n'échantillonne que les messages de patients avec un consentement `LEARNING` actif au moment de l'appel, jamais deux fois le même message.
  - `anonymize_text` : rédaction par motifs (e-mails, téléphones) — explicitement documentée comme un premier filtre automatique, pas une garantie ; la revue humaine qui suit reste le vrai garde-fou (fidèle à l'ordre de la Section 15).
  - `list_pending_feedback` / `review_feedback` : file de revue accessible à *tout* clinicien (pas seulement le clinicien traitant), délibérément — un clinicien qui reconnaîtrait l'écriture de son propre patient serait lui-même un risque de réidentification.
  - `create_dataset_version` : snapshot immuable des éléments approuvés non encore inclus ; un dataset déjà créé n'est jamais modifié.
  - `register_model_version` / `decide_model_version` / `deploy_model_version` / `rollback_model_version` : registre de modèles avec machine à états, exigeant **deux clinicien·ne·s distinct·e·s** pour approuver (contrainte `UNIQUE(model_version_id, approver_id)` empêchant qu'un même clinicien compte double), conformément à l'exigence explicite du prompt maître (« validation de nouveaux modèles par deux psychologues avant déploiement »). Un seul rejet bloque immédiatement.
- 12 nouvelles routes HTTP, RBAC vérifié pour chacune (ADMIN pour l'échantillonnage/les datasets/le registre/déploiement, CLINICIAN pour la revue et les décisions de modèle).
- Interfaces : nouvelle section « Apprentissage » dans le tableau de bord clinicien (file de revue anonymisée, décisions sur les modèles en attente) et dans la console d'administration (déclenchement de l'échantillonnage, création de dataset, enregistrement/déploiement/rollback de modèle).
- **Vérifié de bout en bout par de vrais appels API et une vraie session navigateur**, pas seulement par des tests unitaires : un message contenant un e-mail a été échantillonné, anonymisé (`[REDACTED_EMAIL]`), approuvé par un clinicien, inclus dans un dataset, un modèle a été enregistré et a nécessité l'approbation de **deux comptes clinicien distincts réels** avant que le bouton « Déployer » n'apparaisse dans la console d'administration.
- Un signalement `bandit` réel (`B110 try/except/pass`) sur le traitement d'échec du modèle d'émotion en Phase 8 a été corrigé ici en ajoutant une journalisation, au lieu d'avaler l'erreur silencieusement.

## 2. Fichiers créés

- `backend/app/learning.py`
- `tests/test_learning_pipeline.py`
- `docs/reports/phase-8b-learning-pipeline.md`

## 3. Fichiers modifiés

- `backend/app/auth.py` (`revoke_consent`), `backend/app/http.py` (12 routes, import `learning`, endpoint de révocation de consentement)
- `backend/app/db.py` (migration 009)
- `backend/app/pipeline.py` (journalisation de l'échec du modèle d'émotion au lieu de `pass` silencieux)
- `frontend/clinician/index.html`, `frontend/clinician/app.js` (section Apprentissage)
- `frontend/admin/index.html`, `frontend/admin/app.js` (section Apprentissage)
- `tests/test_foundation.py` (test de révocation de consentement)

## 4. Architecture impactée

Le domaine Continuous Learning existe et s'appuie sur les domaines Conversation (Phase 8a) et AI Model Management (Phase 8) sans dupliquer leur logique. Aucune donnée clinique brute n'est jamais retournée par les endpoints de revue : `human_feedback` ne porte aucune colonne d'identité patient, seulement une référence au message (accessible séparément, sous RBAC, pour l'audit).

## 5. Fonctionnalités terminées

- Chaîne complète production → échantillonnage consenti → anonymisation → revue humaine → dataset versionné → registre de modèles → double approbation clinique → déploiement (état du registre) → rollback.
- Interfaces clinicien et admin fonctionnelles, vérifiées dans un navigateur réel avec deux comptes clinicien distincts.
- Révocation de consentement, prérequis manquant, ajoutée et testée.

## 6. Tests exécutés

- `ruff check backend tests scripts ml`, `mypy backend`, `bandit -r backend scripts -q`, `pip-audit`, `python scripts/scan_secrets.py`
- `coverage run` + `coverage report`
- `python -m unittest discover -s tests -v`
- Vérification manuelle : appels HTTP réels (échantillonnage, revue, dataset, enregistrement de modèle, décision, tentative de déploiement prématurée) puis session navigateur complète avec deux comptes clinicien réels et un compte admin, jusqu'au déploiement et au rollback effectifs dans l'interface.

## 7. Résultats des tests

- 56 tests automatisés, tous verts (9 nouveaux). Aucune régression.
- Couverture : 91 % sur `backend/app`, au-dessus du seuil CI de 85 %.
- Tests négatifs explicites : un clinicien ne peut pas déclencher l'échantillonnage ni créer de dataset ; un même clinicien ne peut pas approuver deux fois le même modèle ; un déploiement est refusé tant que deux approbations distinctes ne sont pas réunies ; un seul rejet bloque un modèle.
- Vérification navigateur : le bouton « Déployer » n'apparaît qu'après la seconde approbation par un clinicien réellement différent (pas simulé) ; « Retirer (rollback) » apparaît après déploiement.
- 1 signalement `bandit` réel trouvé et corrigé (Section 1).

## 8. Bugs détectés

- **Absence de route de révocation de consentement**, découverte en concevant la garde d'éligibilité à l'échantillonnage (Section 1) — un vrai manque fonctionnel préexistant, pas une régression de cette phase.
- **`try/except/pass` silencieux** sur l'échec de prédiction d'émotion (introduit en Phase 8, détecté ici par `bandit`) : masquait toute défaillance du modèle sans laisser de trace.

## 9. Bugs corrigés

- Ajout de `revoke_consent` + route `/api/v1/consents/revoke`, testé.
- Remplacement du `pass` silencieux par une journalisation (`LOGGER.exception`), cohérent avec le traitement des échecs ailleurs dans le code (`crisis.py`, `notifications.py`).

## 10. Vulnérabilités détectées

| ID | Menace | Impact | Probabilité | Risque | Mitigation | Test |
| --- | --- | --- | --- | --- | --- | --- |
| TM-11 | Réidentification via le style d'écriture par un clinicien reconnaissant son propre patient dans la file de revue | Vie privée | Faible-moyenne | Moyen | File de revue non scopée par relation patient-clinicien (choix délibéré, Section 1) | Revue de conception ; pas de test automatisable directement |
| TM-12 | Anonymisation par motifs insuffisante (PII non structurée, ex. un nom propre) | Vie privée | Moyenne | Moyen | Documenté explicitement comme un premier filtre, pas une garantie ; la revue humaine reste obligatoire avant inclusion dans un dataset | Revue humaine systématique avant approbation |

## 11. Vulnérabilités corrigées

- Sans objet pour cette phase au-delà des Sections 8–9 (pas des vulnérabilités de sécurité au sens strict, mais des manques fonctionnels/d'observabilité corrigés).

## 12. Dette technique

- `anonymize_text` reste un filtre par motifs (e-mail, téléphone) : aucune détection de noms propres, adresses ou autres identifiants non structurés. Documenté comme limite assumée, pas caché.
- La révocation de consentement arrête l'échantillonnage *futur* mais ne retire pas rétroactivement les messages déjà échantillonnés ou déjà inclus dans un dataset finalisé (l'immutabilité du dataset est délibérée pour la reproductibilité, mais entre en tension avec un droit de retrait rétroactif total). Documenté comme limite assumée depuis la Phase 8a, non résolue ici.
- `deploy_model_version` ne fait que changer un état en base : aucune infrastructure de déploiement réel (pas de bascule de trafic, pas de shadow/canary). Ce report a toujours été honnête sur ce point plutôt que de le simuler.
- Aucune pagination sur les listes (`human_feedback`, `training_datasets`, `model_versions`) : acceptable au volume actuel, à revoir si besoin.

## 13. Décisions techniques

- File de revue non scopée par relation patient-clinicien, à l'inverse du dashboard clinique (Phase 7) : la logique d'accès aux données de gouvernance de l'IA est distincte de la logique d'accès aux soins, et les confondre aurait recréé un risque de réidentification.
- Deux approbations distinctes obligatoires avant déploiement, appliquées par une contrainte de base de données (`UNIQUE`), pas seulement par une vérification applicative : plus robuste contre un bug futur qui oublierait le contrôle.
- Un rejet unique bloque immédiatement un modèle plutôt que d'attendre un vote majoritaire : cohérent avec la posture systématiquement conservatrice du reste du projet (moteur de crise, engagement de fail-safe).

## 14. Risques restants

- L'anonymisation par motifs n'est pas suffisante seule ; elle dépend structurellement de la vigilance humaine en revue, ce qui est un choix de conception assumé mais reste un point de défaillance humaine possible.
- Aucun psychologue réel n'a encore utilisé cette file de revue ; son ergonomie et la pertinence du contenu présenté restent à valider.

## 15. Métriques

- 1 migration ajoutée (009), 5 nouvelles tables.
- 12 nouvelles routes HTTP, toutes couvertes par au moins un test positif et un test négatif d'autorisation.
- 9 nouveaux tests (56 au total), 0 nouvelle dépendance externe.
- 1 bug fonctionnel préexistant corrigé (révocation de consentement), 1 signalement de sécurité statique réel corrigé.

## 16. Critères de sortie

- [x] Échantillonnage consenti, révocable, non dupliqué.
- [x] Anonymisation de premier niveau, documentée comme limite, pas comme garantie.
- [x] Revue humaine obligatoire avant inclusion dans un dataset.
- [x] Dataset versionné, immuable une fois créé.
- [x] Registre de modèles avec double approbation clinique obligatoire avant déploiement.
- [x] Interfaces clinicien et admin fonctionnelles, vérifiées avec de vrais comptes distincts dans un navigateur réel.
- [ ] Anonymisation de PII non structurée (noms propres, adresses) — non résolu, dette assumée.
- [ ] Infrastructure de déploiement réel (shadow/canary) — hors de portée, honnêtement documenté comme tel.

## 17. Conclusion

La chaîne d'apprentissage continu décrite par la Section 15 du prompt maître existe maintenant de bout en bout, de l'échantillonnage consenti jusqu'au déploiement soumis à une double approbation clinique réellement appliquée par une contrainte de base de données, pas seulement par convention. Chaque étape a été vérifiée avec de vraies données et de vrais comptes, pas seulement simulée. Deux défauts réels (une lacune de révocation de consentement et un échec silencieux) ont été trouvés et corrigés en cours de construction plutôt que découverts plus tard. La dette restante (anonymisation non structurée, absence d'infrastructure de déploiement réelle) est documentée avec la même rigueur que le reste du projet.

STATUS: PASS WITH WARNINGS
