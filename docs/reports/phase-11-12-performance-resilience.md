# PHASE REPORT

Phase: 11–12 — Performance et résilience
Date: 2026-08-27
Objectif: Vérifier ce que la fondation actuelle (WSGI mono-processus, SQLite de développement) peut honnêtement démontrer en matière de concurrence, de résilience aux pannes et de performance, sans prétendre à des résultats de charge qu'une architecture d'un seul processus ne peut pas produire.

## 0. Pourquoi cette phase a trouvé un bug plutôt que de simplement « tester »

En cherchant un premier scénario de concurrence à vérifier, la question la plus évidente était : que se passe-t-il si `backend/app/http.py::application()` est un jour servi par un serveur WSGI à plusieurs threads plutôt que par `wsgiref.simple_server` (mono-thread) ? La réponse, vérifiée directement plutôt que supposée : la connexion SQLite unique partagée par tout le processus (`conn = connect(...)` ouverte une seule fois au démarrage) lève `sqlite3.ProgrammingError` dès qu'un thread différent de celui qui l'a créée l'utilise — c'est le comportement par défaut de `sqlite3` (`check_same_thread=True`). Concrètement : sous un serveur multi-thread (gunicorn `--threads`, waitress, un mixin de threading), la quasi-totalité des requêtes échoueraient en `500`, y compris celles du pipeline de crise. Ce n'est pas un cas théorique : de nombreux déploiements par défaut activent plusieurs threads.

## 1. Travaux réalisés

- **Correction structurelle** : `application()` n'ouvre plus une connexion SQLite persistante partagée. Chaque requête ouvre désormais sa propre connexion (`conn = connect(...)`) et la ferme dans un bloc `finally`, ce qui élimine la question d'affinité de thread au lieu de la contourner. Le mode WAL de SQLite est conçu pour ce modèle (plusieurs connexions, lecteurs concurrents et un seul rédacteur à la fois).
- La vérification de vivacité (`/health/live`) a été déplacée avant l'ouverture de la connexion : elle ne doit jamais dépendre de la disponibilité de la base, contrairement à la vérification de disponibilité (`/health/ready`), qui elle interroge réellement la base.
- `tests/test_resilience.py` : suite de tests de concurrence et de résilience.
  - Reproduction du bug ci-dessus avant correction, puis test de non-régression après (20 threads appellent `/health/ready` simultanément).
  - Inscriptions concurrentes de comptes distincts : toutes réussissent.
  - Inscriptions concurrentes avec le **même** e-mail : une seule réussit, les autres échouent proprement — la contrainte `UNIQUE` de la base est le véritable garde-fou, pas une hypothèse de verrouillage applicatif non vérifiée.
  - Récupération après un « crash » simulé (coupure d'une connexion sans fermeture propre, pas un arrêt propre) : les données déjà validées (mode autocommit) sont bien relisibles après reconnexion, conformément à la garantie du mode WAL.
- `scripts/benchmark.py` : mesure de latence séquentielle sur les opérations clés, explicitement documentée comme une mesure sur une seule machine partagée, pas un test de charge, et jamais utilisée comme porte de CI (les seuils de performance sur une machine de développement partagée sont trop bruités pour être fiables comme critère automatique).

## 2. Fichiers créés

- `tests/test_resilience.py`
- `scripts/benchmark.py`
- `docs/reports/phase-11-12-performance-resilience.md`

## 3. Fichiers modifiés

- `backend/app/http.py` (connexion par requête au lieu d'une connexion partagée ; réordonnancement de `/health/live`)

## 4. Architecture impactée

Changement de gestion de connexion uniquement : aucun contrat d'API, aucun schéma de données, aucune règle métier modifiée. C'est un changement d'implémentation qui corrige une hypothèse de déploiement implicite et non vérifiée.

## 5. Fonctionnalités terminées

- Sécurité de concurrence de la couche HTTP vérifiée par un vrai test multi-thread, pas supposée.
- Récupération après coupure brutale vérifiée pour le mode WAL.
- Base de référence de latence mesurée et documentée honnêtement.

## 6. Tests exécutés

- `python -m unittest discover -s tests -v`
- Reproduction manuelle du bug de concurrence avant correction (20 threads), puis re-vérification après correction.
- `ruff check`, `mypy`, `bandit`, `pip-audit`, `scan_secrets.py`, `coverage run` + `coverage report`.
- `python scripts/benchmark.py` (mesure ponctuelle, résultats en Section 7).

## 7. Résultats des tests

- 83 tests automatisés, tous verts (4 nouveaux dans `test_resilience.py`). Aucune régression.
- Couverture : 92 % sur `backend/app`, au-dessus du seuil CI de 85 %.
- Reproduction du bug de concurrence : confirmée avant correction (`sqlite3.ProgrammingError` systématique dès qu'un second thread appelait l'application) ; 20/20 requêtes concurrentes réussissent après correction.
- Coût de la connexion par requête isolé : environ 3 ms en moyenne (ouverture + une requête triviale + fermeture) sur la machine de développement — un coût honnête, mesuré, pas une estimation.
- Mesures de latence séquentielle (n=200, machine de développement partagée, à titre indicatif uniquement) :

| Opération | Moyenne | p50 | p95 |
| --- | --- | --- | --- |
| Inscription | 17,8 ms | 17,8 ms | 24,6 ms |
| Connexion | 20,8 ms | 18,4 ms | 22,6 ms |
| Soumission PHQ-9 | 19,5 ms | 18,6 ms | 28,3 ms |
| Démarrage de conversation | 13,7 ms | 12,9 ms | 18,6 ms |
| Envoi de message (pipeline complet crise + émotion) | 24,7 ms | 23,9 ms | 29,8 ms |

L'essentiel du coût de l'inscription et de la connexion vient du hachage PBKDF2 à 600 000 itérations (volontairement coûteux pour la sécurité), pas de la base de données.

## 8. Bugs détectés

**Bug de concurrence critique** (Section 0) : une connexion SQLite partagée entre threads aurait rendu l'application quasiment inutilisable (500 sur presque toutes les requêtes) sous tout serveur WSGI multi-thread — une configuration de déploiement courante, pas un cas exotique. Ce bug n'affecte pas `wsgiref.simple_server` (mono-thread) tel qu'utilisé aujourd'hui en développement, ce qui explique qu'il soit passé inaperçu jusqu'à cette vérification délibérée.

## 9. Bugs corrigés

- Connexion SQLite ouverte et fermée par requête plutôt que partagée pour toute la durée de vie du processus (Section 1). Vérifié par un test de régression qui aurait échoué avant la correction.

## 10. Vulnérabilités détectées

Aucune vulnérabilité de sécurité au sens strict : le bug de concurrence est un défaut de disponibilité (déni de service involontaire sous certaines configurations de déploiement), pas une fuite de données ni un contournement d'autorisation.

## 11. Vulnérabilités corrigées

Sans objet au-delà de la Section 9.

## 12. Dette technique

- L'ouverture d'une connexion SQLite par requête (~3 ms) est un coût acceptable pour une fondation de développement/pilote, mais ne remplace pas un vrai pool de connexions PostgreSQL prévu pour la production (ADR-003).
- `scripts/benchmark.py` reste une mesure ponctuelle sur une seule machine : aucune conclusion de capacité réelle ne peut en être tirée. Un vrai test de charge (Phase 11 complète du prompt maître : montée en charge, pic, endurance) nécessiterait une infrastructure dédiée, hors de portée d'un agent seul.
- Aucun test de panne pour les autres composants (aucun n'existe encore : pas de file de messages, pas de cache, pas de service externe réel) — le seul composant à panne testable aujourd'hui est SQLite lui-même, ce qui a été fait.

## 13. Décisions techniques

- Connexion par requête plutôt que pool de connexions maison : plus simple, correct par construction, et le coût mesuré (~3 ms) est négligeable devant le reste du travail par requête (hachage de mot de passe, détection de crise). Un vrai pool serait sur-ingénierie pour une fondation SQLite mono-fichier destinée à être remplacée par PostgreSQL avant tout pilote réel.
- Pas de seuil de performance appliqué en CI : les temps mesurés sur une machine de développement partagée varient trop pour être un critère de blocage fiable ; `benchmark.py` reste un outil de diagnostic manuel, pas une porte automatisée.

## 14. Risques restants

- Si ce projet est un jour déployé avec un serveur WSGI multi-thread sans relire ce rapport, le bug corrigé ici aurait pu être réintroduit par une régression future qui reviendrait à une connexion partagée : le test de régression (`test_health_ready_survives_concurrent_calls_from_different_threads`) est la garde-fou permanent contre cela.
- Aucun test de charge réel, aucun test de résilience réseau (puisqu'il n'existe aucune dépendance réseau externe aujourd'hui) : à réévaluer dès qu'un LLM réel ou un canal de notification réel sera intégré.

## 15. Métriques

- 1 bug de concurrence critique trouvé et corrigé.
- 4 nouveaux tests (83 au total), 0 nouvelle dépendance externe.
- ~3 ms de surcoût mesuré pour la connexion par requête ; latences bout-en-bout mesurées entre 13 et 25 ms en moyenne pour les opérations clés.

## 16. Critères de sortie

- [x] Sécurité de concurrence de la connexion base de données vérifiée par un test réel multi-thread.
- [x] Comportement de vivacité (`/health/live`) indépendant de la base de données.
- [x] Récupération après coupure brutale vérifiée pour le mode WAL.
- [x] Base de référence de latence mesurée et documentée honnêtement, sans revendication de capacité de charge.
- [ ] Test de charge réel (montée en charge, pic, endurance) — hors de portée sans infrastructure dédiée.
- [ ] Test de panne pour des dépendances externes réelles — sans objet tant qu'aucune n'existe.

## 17. Conclusion

Cette phase a trouvé un bug qui aurait pu rendre l'application presque totalement indisponible dans une configuration de déploiement pourtant courante — pas un cas exotique nécessitant un scénario de panne inventé, mais un changement de configuration serveur banal. Il a été corrigé à la racine (changement de modèle de connexion), pas contourné, et un test de régression permanent empêche qu'il ne revienne silencieusement. Les mesures de performance et de résilience restantes sont documentées avec la même honnêteté que le reste du projet : ce qui a été mesuré, ce qui ne l'a pas été, et pourquoi.

STATUS: PASS WITH WARNINGS
