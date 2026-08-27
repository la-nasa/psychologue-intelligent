# PHASE REPORT

Phase: 3 — Plateforme patient  
Date: 2026-08-24  
Objectif: Fournir une base patient navigable, avec compte, session, consentements, profil et confidentialité, sans présenter prématurément un dialogue IA clinique.

## 1. Travaux réalisés

- Ajout de la migration patient : profil, consentements versionnés et demandes de suppression.
- Ajout d’API protégées pour le profil, le consentement et la demande de suppression.
- Création de l’interface web patient responsive : inscription, connexion, onboarding, consentement de soin, opt-in d’apprentissage facultatif, confidentialité et déconnexion.
- Création d’une coque conversationnelle explicitement désactivée jusqu’à la phase IA/sécurité.

## 2. Fichiers créés

- `frontend/index.html`, `frontend/styles.css`, `frontend/app.js`
- `docs/reports/phase-3-user-platform.md`

## 3. Fichiers modifiés

- `backend/app/db.py`, `backend/app/auth.py`, `backend/app/http.py`, `tests/test_foundation.py`

## 4. Architecture impactée

Le domaine Consent et les données de confidentialité sont maintenant persistés séparément. Les finalités `CARE` et `LEARNING` exigent une décision distincte et versionnée.

## 5. Fonctionnalités terminées

- Inscription, connexion, session, déconnexion.
- Saisie profil, consentement de soin et opt-in facultatif d’apprentissage.
- Demande de suppression traçable.
- Interface patient responsive, accessible au clavier et non alarmiste.

## 6. Tests exécutés

- `python -m unittest discover -s tests -v`
- `python -m compileall -q backend`

## 7. Résultats des tests

- 6 tests réussis : migrations, santé, validation, sessions, MFA, RBAC, audit, consentement, profil et demande de suppression.

## 8. Bugs détectés

- Le test de migration supposait une seule migration après l’ajout de la migration patient.

## 9. Bugs corrigés

- Test rendu compatible avec le nombre de migrations et fermeture garantie de la connexion SQLite sur erreur.

## 10. Vulnérabilités détectées

- Aucune nouvelle vulnérabilité critique dans le périmètre testé. Les limites SQLite/rate limiting mémoire restent ouvertes.

## 11. Vulnérabilités corrigées

- Sans objet.

## 12. Dette technique

- Le frontend suppose que l’API est servie sur la même origine ; le serveur statique/proxy de développement sera ajouté avec l’infrastructure.
- Le chat ne doit être activé qu’avec le moteur de crise de phase 5–6.

## 13. Décisions techniques

- Consentement d’amélioration dissocié du consentement de soin et opt-in par défaut.
- Aucune réponse IA simulée avant les garde-fous nécessaires.

## 14. Risques restants

- Les textes juridiques et les politiques de rétention doivent être validés par les responsables locaux avant pilote.

## 15. Métriques

- 1 migration patient, 3 routes protégées et 6 tests de fondation passent.

## 16. Critères de sortie

- [x] Compte et session.
- [x] Consentements séparés et traçables.
- [x] Profil et demande de suppression.
- [x] Coque de chat sans promesse IA trompeuse.
- [x] Tests automatisés passent.

## 17. Conclusion

La phase 3 passe avec avertissements. Le prochain gate est la phase 4 : PHQ-9 versionné, calcul indépendant de l’UI, permissions et historique.

STATUS: PASS WITH WARNINGS
