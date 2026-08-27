# PHASE REPORT

Phase: 4 — Assessment (PHQ-9)
Date: 2026-08-26 (rédigé rétroactivement — voir addendum)
Objectif: Fournir un questionnaire PHQ-9 versionné, un calcul indépendant de l'UI, un historique et des permissions.

## 0. Addendum de transparence

Ce rapport est écrit après coup. Le code, les migrations et les tests de cette phase existaient déjà dans le dépôt au début de la session actuelle, mais aucun rapport de phase n'avait été produit et le `README.md` affirmait encore un statut de phase 2. C'est une dette de documentation, pas une dette de code : le calcul, la persistance et les tests ont été vérifiés comme fonctionnels avant d'écrire ce rapport, et non pris sur la foi de commentaires préexistants.

## 1. Travaux réalisés

- Calcul PHQ-9 pur, séparé de l'UI (`backend/app/phq9.py`) : validation stricte (9 réponses entières entre 0 et 3), score total et item 9 isolé.
- Migration `003_phq9` : table `phq9_assessments` versionnée par `instrument_version`, contrainte `total_score BETWEEN 0 AND 27`, `item9_score BETWEEN 0 AND 3`, index patient/date.
- Endpoints protégés par session : `POST /api/v1/assessments/phq9` (soumission) et `GET /api/v1/assessments/phq9` (historique), tous deux exigeant un token valide.
- Audit systématique de la soumission (`assessment.phq9.submit`).

## 2. Fichiers créés

- `backend/app/phq9.py`
- `docs/reports/phase-4-assessment.md` (ce rapport)

## 3. Fichiers modifiés

- `backend/app/db.py` (migration `003_phq9`)
- `backend/app/auth.py` (`submit_phq9`, `phq9_history`)
- `backend/app/http.py` (routes `/api/v1/assessments/phq9`)
- `tests/test_foundation.py` (`test_phq9_score_validation_and_history`)

## 4. Architecture impactée

Le domaine Assessment est isolé du domaine Identity : le calcul ne dépend d'aucune route HTTP et peut être testé, réutilisé ou remplacé (autre instrument) sans toucher à l'API.

## 5. Fonctionnalités terminées

- Calcul, validation, persistance, historique et audit du PHQ-9.
- Permissions : uniquement le patient authentifié peut soumettre ou consulter son propre historique (portée par le token de session, aucun paramètre d'identité de patient n'est accepté depuis le client).

## 6. Tests exécutés

- `python -m unittest discover -s tests -v`
- `python -m compileall -q backend`

## 7. Résultats des tests

- `test_phq9_score_validation_and_history` : calcul valide, rejet d'un tableau de 8 réponses, soumission et lecture d'historique via l'API — passent.
- Suite complète (21 tests après les ajouts de la phase 5–6) : OK.

## 8. Bugs détectés

- Aucun bug fonctionnel constaté dans le module lui-même lors de cette vérification rétroactive.

## 9. Bugs corrigés

- Sans objet pour le code du module ; voir Phase 5–6 pour les corrections liées au reste du système.

## 10. Vulnérabilités détectées

- Les réponses au questionnaire sont actuellement stockées en clair (`answers_json`) dans une base SQLite de développement. Le modèle de données cible (`docs/architecture/data-model.md`) prévoit des réponses chiffrées ; ce n'est pas encore le cas ici.

## 11. Vulnérabilités corrigées

- Sans objet.

## 12. Dette technique

- Chiffrement au repos des réponses PHQ-9 non implémenté (dépend du choix de gestion de secrets, différé tant que SQLite de développement est utilisé).
- Pas encore d'export, de tendance visualisée ni de seuil d'alerte relié au score PHQ-9 : c'est prévu par le prompt maître (Section 12, seuils >10 et >15) mais doit passer par le même mécanisme de politique versionnée que le moteur de crise (voir ADR-002 et ADR-004), pas être codé en dur séparément. Ce lien reste à faire.
- Aucune interface frontend pour remplir le questionnaire : le frontend patient s'arrête à l'onboarding et au tableau de bord minimal (Phase 3).

## 13. Décisions techniques

- Le score PHQ-9 n'entraîne aujourd'hui aucune action automatique (pas d'alerte). Une décision explicite de rattacher un seuil PHQ-9 à la politique de crise est reportée pour éviter une deuxième source de vérité clinique parallèle à `config/policies/crisis-policy-v1.json`.

## 14. Risques restants

- Les seuils cliniques (10, 15) mentionnés dans le document source restent des hypothèses à valider, pas des règles actives.

## 15. Métriques

- 1 migration, 2 routes protégées, 1 test dédié, 0 dépendance externe.

## 16. Critères de sortie

- [x] Instrument versionné et calcul testé avec cas limites.
- [x] Historique et permissions.
- [ ] Lien avec le moteur de politique de crise (reporté, voir Section 13).
- [ ] Interface de saisie frontend (reportée).

## 17. Conclusion

Le cœur du module PHQ-9 est solide et déjà couvert par des tests, mais la phase n'était pas formellement close faute de rapport et de lien explicite avec le moteur de politique. Elle est déclarée passée avec réserves, la dette étant documentée plutôt que masquée.

STATUS: PASS WITH WARNINGS
