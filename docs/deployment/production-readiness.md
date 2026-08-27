# Ce qui manque avant un déploiement pilote réel

Ce document liste, honnêtement, l'écart entre la fondation actuelle (Phase 13, testée localement) et ce qu'exige un déploiement pilote réel avec de vrais patients. Rien ici n'est fait « à moitié » : chaque ligne est soit livrée et vérifiée (voir les rapports de phase), soit explicitement non commencée. Aucune ligne ne prétend être « presque prête ».

## Obligatoire avant tout pilote

| Sujet | État actuel | Ce qu'il faut |
| --- | --- | --- |
| Base de données | SQLite, connexion par requête (Phase 11–12) | PostgreSQL avec pool de connexions ; migration testée avec restauration réelle, pas seulement en théorie |
| Secrets | Aucune gestion centralisée ; configuration via variables d'environnement locales | Un gestionnaire de secrets (Vault, AWS Secrets Manager, ou équivalent) ; rotation documentée |
| Rate limiting | En mémoire de processus (`RateLimiter`, Phase 10) | Implémentation distribuée (Redis ou équivalent) si plusieurs instances tournent |
| Canal de notification | `LogNotificationProvider` — n'atteint aucun canal réel (Phase 5–6) | Un vrai fournisseur (e-mail, SMS) branché derrière le port `NotificationProvider` déjà existant, avec supervision de la livraison |
| Politiques cliniques | Fichiers JSON versionnés en développement, non approuvés (`approved_by`/`approved_at` à `null`) | Approbation réelle par l'équipe clinique locale avant tout déploiement hors développement — le chargeur (`policy.py`) refuse déjà de démarrer sans ça, c'est un contrôle actif, pas une formalité |
| Numéros d'urgence / contacts | `emergency_contacts` vide par défaut | Configuration validée localement par pays/établissement, jamais codée en dur (voir `config/policies/crisis-policy-v1.json`) |
| Chiffrement au repos | Contenu des messages et réponses PHQ-9 en clair en SQLite de développement | Chiffrement applicatif par champ pour les données cliniques sensibles, une fois la base de production choisie |
| TLS | Aucun en développement local (HTTP) ; terminé en périphérie par Railway sur le déploiement de démonstration (voir `railway.md`) | TLS obligatoire en frontière de production — déjà couvert pour un déploiement Railway, à revérifier pour toute autre infrastructure |
| Validation clinique | Aucune — voir `docs/reports/phase-*` pour les avertissements répétés | Revue par un psychologue clinicien, un psychiatre si besoin, et un comité d'éthique avant toute utilisation avec de vrais patients |
| Test d'intrusion | Aucun (seulement des tests adversariaux automatisés internes, Phase 10) | Un test d'intrusion par une équipe de sécurité externe |

## Fortement recommandé

| Sujet | État actuel | Ce qu'il faut |
| --- | --- | --- |
| Notifications fiables | Retry synchrone borné (3) puis worker de reprise en arrière-plan avec backoff exponentiel et lettre morte explicite (`scripts/retry_notifications.py`, `MAX_TOTAL_ATTEMPTS=10`) — nécessite un ordonnanceur OS réel (cron/Task Scheduler), aucun n'est démarré par l'application ; un cas résiduel étroit reste ouvert (panne de processus entre l'écriture `PENDING` et la mise à jour finale — TM-08, réduit depuis la Phase 5–6 mais pas totalement fermé) | Planifier réellement `scripts/retry_notifications.py` en production ; fermer le cas résiduel par une réclamation par verrouillage optimiste si jugé nécessaire ; alerting opérationnel sur les lignes en lettre morte |
| Test de charge réel | Mesure séquentielle sur une machine partagée uniquement (Phase 11–12) | Un test de montée en charge/pic/endurance sur une infrastructure dédiée |
| E2E navigateur automatisé | Vérification manuelle par phase + E2E applicatif automatisé (Phase 13) | Une suite Playwright (ou équivalent) si l'équipe veut une garantie automatisée au niveau interface |
| Anonymisation des données d'apprentissage | Filtre par motifs (e-mail, téléphone) uniquement (Phase 8b) | Une détection d'entités nommées plus robuste, en complément — pas en remplacement — de la revue humaine déjà obligatoire |
| Console d'administration complète | Utilisateurs et relations uniquement (Phase 23) | Gestion des rôles/permissions fines, des feature flags, et des politiques directement depuis l'interface |
| Monitoring/observabilité | Journalisation structurée locale uniquement | Métriques (latence, taux d'alerte, taux d'échec de notification), traces, tableaux de bord, alerting opérationnel |
| Sauvegardes | Aucune configurée (SQLite de développement) | Sauvegardes régulières avec restauration testée en conditions réelles, pas seulement documentée |

## Ce qui est déjà solide et ne bloque pas un pilote très restreint et supervisé

- Authentification (PBKDF2 600k itérations, MFA clinicien/admin obligatoire), autorisation RBAC vérifiée par relation active, moteur de crise indépendant du LLM et fail-safe, pipeline d'apprentissage avec consentement révocable et double approbation clinique, suite de tests de sécurité adversariaux, CI complète (lint/type-check/SAST/audit de dépendances/scan de secrets), 4 parcours E2E automatisés.
- Ces éléments sont vérifiés par des tests réels (voir `docs/reports/`), pas seulement conçus.

## Décision explicite requise avant d'aller plus loin

Ce document ne recommande pas de date ni de méthode de déploiement : ce sont des décisions qui appartiennent à l'équipe clinique, juridique et opérationnelle du projet, pas à l'agent qui a construit cette fondation.

Un déploiement de démonstration technique existe sur Railway (voir `railway.md`) : il n'allège aucune des exigences de cette page, il illustre seulement que la fondation tourne bien en dehors d'une machine de développement locale.
