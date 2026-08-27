# PHASE REPORT

Phase: 14+ — Mission d'audit de sécurité complet, remédiation et re-test
Date: 2026-08-27
Objectif: Exécuter la mission d'audit de sécurité demandée explicitement par l'utilisateur (OWASP Top 10/ASVS/API Security Top 10, CWE, STRIDE) sur l'ensemble du dépôt, corriger les vulnérabilités réellement exploitables trouvées, ajouter des tests de régression, et re-tester.

## 0. Cadrage honnête du périmètre applicable

La majorité des 40 phases de la mission d'audit demandée ne s'appliquent pas à ce projet : pas de paiement, pas d'upload de fichier, pas de JWT, pas de Docker/Kubernetes, pas de webhooks, pas de XML, pas de service tiers, pas de WebSockets, pas de GraphQL. Ceci a été **vérifié par lecture du code** (grep systématique de chaque catégorie), pas supposé. Voir `docs/security/security-assessment-report.md` pour le détail complet de chaque catégorie, applicable ou non.

## 1. Travaux réalisés

- Vérification systématique par catégorie (secrets, désérialisation, XML, SSRF, upload, CORS, headers, Docker) — confirmé : aucun appel réseau sortant, aucune désérialisation dangereuse, aucune de ces surfaces d'attaque n'existe dans ce projet.
- **SEC-001 (High, CWE-362/367)** : race condition (TOCTOU) trouvée et **reproduite de manière déterministe** (deux connexions SQLite séparées simulant deux requêtes concurrentes réelles, sans dépendre du hasard du threading) dans trois fonctions : `learning.py::decide_model_version`, `learning.py::review_feedback`, `alerts.py::transition`. Un modèle IA explicitement rejeté par un clinicien pouvait voir son statut silencieusement écrasé en `APPROVED` par une approbation concurrente d'un autre clinicien. Corrigé par un motif de verrouillage optimiste (`UPDATE ... WHERE status=<état lu>` + vérification de `rowcount`).
- **SEC-002 (Medium, CWE-693)** : absence totale de `Content-Security-Policy`, `Strict-Transport-Security`, `Permissions-Policy` sur l'API et les trois frontends statiques. Corrigé, puis **vérifié dans un navigateur réel** que la CSP stricte ne casse aucune fonctionnalité (aucun script/style inline n'existait déjà dans les trois frontends).
- **SEC-003 (Low, CWE-770)** : incohérence de rate limiting — l'endpoint PHQ-9 n'avait aucune limite alors que l'endpoint de message équivalent en était doté depuis la Phase 10. Corrigé (20/heure/patient).
- **Second passage adversarial contre les correctifs eux-mêmes** (Phase 38 de la mission) : recherche active de contournement de SEC-001. Trouvé un cas limite bénin (INFO-002) où deux approbations légitimes simultanées au seuil exact peuvent produire un message d'erreur trompeur pour l'un des deux votants, sans jamais corrompre l'état final ni le journal d'audit — documenté et accepté comme compromis raisonnable plutôt que sur-ingénieré.
- Un point de configuration de déploiement documenté sans être corrigé (INFO-001) : le rate limiting par IP suppose l'absence de reverse proxy non configuré ; faire confiance à `X-Forwarded-For` sans connaître la chaîne de proxys de confiance créerait une nouvelle vulnérabilité de contournement, donc ce n'est pas corrigé maintenant, seulement documenté comme décision à prendre au moment du déploiement réel.
- `docs/security/security-assessment-report.md` créé : rapport structuré complet par vulnérabilité, avec traçabilité FOUND → ANALYZED → FIXED → REGRESSION TEST ADDED → RE-TESTED → VERIFIED pour chacune.
- `docs/security/threat-model.md` mis à jour (TH-14, TH-15, TH-16).

## 2. Fichiers créés

- `docs/security/security-assessment-report.md`
- `docs/reports/phase-14-security-audit-mission.md`

## 3. Fichiers modifiés

- `backend/app/learning.py` (SEC-001 : `decide_model_version`, `review_feedback`)
- `backend/app/alerts.py` (SEC-001 : `transition`)
- `backend/app/http.py` (SEC-002 : en-têtes de sécurité ; SEC-003 : rate limiting PHQ-9)
- `scripts/dev_server.py` (SEC-002 : en-têtes de sécurité sur les fichiers statiques)
- `tests/test_security.py` (nouvelle classe `BusinessLogicRaceConditionTests`, `SecurityHeadersTests`, test PHQ-9)
- `docs/security/threat-model.md`

## 4. Architecture impactée

Aucun changement de contrat d'API ni de schéma de données. Changement de comportement pour les appelants concurrents des trois fonctions corrigées : un conflit produit désormais une erreur explicite (`ValueError`, traduite en `401` par le gestionnaire d'erreurs existant) au lieu d'un écrasement silencieux — un changement de comportement strictement plus sûr, jamais plus permissif.

## 5. Fonctionnalités terminées

- Les trois transitions d'état critiques du projet (décision de modèle, revue de feedback, transition d'alerte) sont désormais protégées contre les écrasements concurrents silencieux.
- En-têtes de sécurité complets sur toutes les réponses, API et frontends, sans exception (un seul point d'appel `start_response` vérifié).
- Rate limiting cohérent sur tous les endpoints d'écriture patient à risque d'abus (login, inscription, message, PHQ-9).

## 6. Tests exécutés

- Reproduction manuelle déterministe de SEC-001 avant correction (voir Section 1), puis re-vérification après correction.
- `python -m unittest discover -s tests -v`
- `ruff check backend tests scripts ml`, `mypy backend`, `bandit -r backend scripts -q`, `pip-audit`, `python scripts/scan_secrets.py`, `python scripts/validate_openapi.py`
- `coverage run` + `coverage report`
- Vérification manuelle dans un navigateur réel de la CSP (patient + clinicien), y compris un appel `fetch()` réel confirmant que `connect-src` (hérité de `default-src 'self'`) autorise bien les appels same-origin.

## 7. Résultats des tests

- 93 tests automatisés, tous verts (6 nouveaux : 3 pour SEC-001, 2 pour SEC-002, 1 pour SEC-003). Aucune régression.
- Couverture : 92 % sur `backend/app`, au-dessus du seuil CI de 85 %.
- Aucun signalement `ruff`, `mypy`, `bandit`, `pip-audit`, scanner de secrets, validation OpenAPI.
- Vérification navigateur : 0 violation CSP, fonctionnalité intacte sur patient et clinicien.

## 8. Bugs détectés

- SEC-001, SEC-002, SEC-003 (voir `security-assessment-report.md` pour le détail complet par vulnérabilité).
- INFO-002 : trouvé uniquement en cherchant activement à casser le correctif de SEC-001, pas par accident — exactement la démarche que la mission d'audit exige (Phase 38 : « essaie de casser les protections que tu viens d'ajouter »).

## 9. Bugs corrigés

- SEC-001, SEC-002, SEC-003 : corrigés à la cause racine (voir Section 1), pas contournés ni masqués.

## 10. Vulnérabilités détectées

Voir le tableau complet dans `docs/security/security-assessment-report.md`. Résumé : 1 High, 1 Medium, 1 Low, 2 Informational. **Zéro vulnérabilité Critical.**

## 11. Vulnérabilités corrigées

SEC-001, SEC-002, SEC-003 — 3 sur 3 des vulnérabilités non-informationnelles trouvées, toutes corrigées, testées et re-vérifiées dans la même session.

## 12. Dette technique

- INFO-001 (rate limiting par IP derrière un reverse proxy non configuré) reste une décision de déploiement à prendre plus tard, pas une dette de code.
- INFO-002 (message d'erreur trompeur dans un cas limite bénin de double-approbation simultanée) reste tel quel, documenté comme compromis assumé.
- Aucun test d'intrusion externe par une équipe humaine n'a été réalisé (hors de portée d'un agent).

## 13. Décisions techniques

- Verrouillage optimiste (`WHERE status=<lu>` + `rowcount`) plutôt que des transactions SQL explicites plus lourdes (`BEGIN IMMEDIATE`) : suffisant pour l'invariant à protéger, cohérent avec le style de connexion-par-requête déjà établi en Phase 11–12, et testable de façon déterministe.
- CSP `default-src 'none'` sur l'API plutôt qu'une politique permissive « juste au cas où » : l'API ne rend jamais de HTML, donc la politique la plus stricte est aussi la plus correcte, pas un compromis.
- Ne pas corriger INFO-001 maintenant : implémenter un parsing naïf de `X-Forwarded-For` sans connaître l'architecture de déploiement réelle serait une régression de sécurité déguisée en correctif.

## 14. Risques restants

- Voir `docs/security/security-assessment-report.md`, INFO-001 et INFO-002.
- Comme toujours sur ce projet : aucune de ces vérifications ne remplace un test d'intrusion réel par une équipe de sécurité externe avant un pilote clinique.

## 15. Métriques

- 3 vulnérabilités réelles trouvées, 3 corrigées (100 %), 0 Critical, 0 High résiduel.
- 6 nouveaux tests de régression (93 au total), 0 nouvelle dépendance.
- 1 reproduction déterministe complète d'une race condition avant/après correctif, documentée avec les commandes exactes utilisées.

## 16. Critères de sortie

- [x] Reconnaissance exhaustive du dépôt par catégorie de vulnérabilité.
- [x] Chaque vulnérabilité trouvée reproduite avant d'être déclarée confirmée.
- [x] Correction à la cause racine, sans contournement ni masquage.
- [x] Test de régression permanent pour chaque correctif.
- [x] Second passage adversarial contre les correctifs eux-mêmes.
- [x] Aucune vulnérabilité Critical ou High non résolue.

## 17. Conclusion

Trois vulnérabilités réelles ont été trouvées en cherchant activement au-delà de ce qui était déjà vérifié dans les phases précédentes, la plus sérieuse (SEC-001) contournant un invariant de sécurité clinique explicitement voulu par la conception du projet. Toutes ont été reproduites avant d'être déclarées, corrigées à la cause racine, et re-testées — y compris en cherchant délibérément à casser les correctifs eux-mêmes, ce qui a révélé un cas limite bénin documenté honnêtement plutôt que caché. Voir `docs/security/security-assessment-report.md` pour le rapport complet et le score par catégorie.

STATUS: PASS
