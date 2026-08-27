# Runbook opérationnel

Procédures pour les incidents les plus probables compte tenu de ce qui existe réellement dans ce projet aujourd'hui (Phase 14). Ce n'est pas un runbook générique copié d'un autre projet : chaque scénario correspond à un mécanisme réel du code, ou à un incident réellement rencontré pendant la construction de ce projet.

## Une alerte ROUGE n'est pas prise en compte dans le délai attendu

**Symptôme** : une ligne dans `alerts` avec `level='RED'` et `status='OPEN'` dont `created_at` dépasse le SLA défini dans `config/policies/crisis-policy-v1.json` (`response_sla_minutes.RED`).

1. Vérifier `notifications` pour cette alerte : si `delivery_status='SKIPPED_NO_CHANNEL'`, c'est le comportement honnête attendu tant qu'aucun canal réel n'est configuré (`notification_channels` vide dans la politique) — voir `production-readiness.md`. Ce n'est pas un bug, c'est l'absence délibérée d'un faux positif de livraison.
2. Si un canal est configuré et `delivery_status='FAILED'` malgré les 3 tentatives synchrones (`notifications.py::MAX_ATTEMPTS`), la ligne sera reprise automatiquement en arrière-plan (backoff exponentiel jusqu'à `MAX_TOTAL_ATTEMPTS=10`) au prochain déclenchement planifié de `scripts/retry_notifications.py` — vérifier que ce script est bien exécuté périodiquement (cron/Task Scheduler ; aucun ordonnanceur n'est démarré automatiquement par l'application elle-même). Si `attempt_count >= 10` et `next_retry_at IS NULL`, la notification est en lettre morte définitive : une intervention manuelle est nécessaire pour relancer la notification ou contacter directement le clinicien assigné. Note : une panne du processus exactement entre l'écriture `PENDING` et la mise à jour finale (fenêtre très étroite) reste un cas non repris automatiquement (TM-08, résiduel) — vérifier aussi les lignes `delivery_status='PENDING'` anormalement anciennes.
3. Vérifier `patient_clinician_relationships` : une alerte sans clinicien assigné (relation active) n'apparaîtra dans la file d'aucun clinicien. Assigner en urgence via `POST /api/v1/admin/relationships`.

## Le disque de la machine hébergeant l'application est plein

**Ce n'est pas un scénario théorique : cela s'est produit pendant le développement de ce projet** (installation de `scikit-learn` en Phase 8, échouée avec `OSError: [Errno 28] No space left on device`).

1. Vérifier l'espace disque : `df -h` (Linux/macOS) ou `Get-PSDrive` (PowerShell).
2. Le cache pip est le premier candidat sûr à vider : `pip cache purge` (a libéré ~840 Mo dans l'incident réel rencontré).
3. Vérifier `work/*.db-wal` : en écriture intensive, le fichier WAL de SQLite peut grossir avant un checkpoint. Un `PRAGMA wal_checkpoint(TRUNCATE);` force sa réduction (à exécuter avec la base fermée par ailleurs, ou via une connexion dédiée).
4. Ne jamais supprimer directement un fichier `.db-wal` ou `.db-shm` pendant que l'application tourne : risque de corruption. Arrêter l'application avant toute intervention manuelle sur les fichiers SQLite.

## `python -m unittest discover` échoue après un changement de dépendance ou d'environnement

1. Vérifier que l'artefact du modèle d'émotion existe : `ml/artifacts/emotion-classifier-v1.json`. Son absence ne fait pas échouer les tests (ils se dégradent proprement, voir `@unittest.skipUnless` dans `test_emotion_model.py`) mais réduit la couverture réelle vérifiée.
2. Vérifier `config/policies/*.json` : un fichier de politique manquant ou invalide fait échouer `application(settings)` au démarrage (voir `policy.py`), ce qui fait échouer toute la suite de tests d'un coup — un signal clair, pas un vrai bug caché.
3. Relancer `python -m compileall -q backend tests scripts ml` avant la suite complète pour isoler une erreur de syntaxe d'un vrai échec de test.

## Suspicion de fuite de secret ou de donnée sensible

1. Lancer immédiatement `python scripts/scan_secrets.py` sur l'état actuel du dépôt.
2. Vérifier les logs applicatifs : aucun `password_hash`, `mfa_secret`, ni contenu de message clinique ne doit y apparaître (voir `docs/security/threat-model.md`, TH-09). Une présence de l'un de ces éléments dans les logs est un incident de sécurité à traiter en priorité, pas une simple anomalie.
3. Si un secret a réellement fuité (ex. commit accidentel d'un fichier `.env`) : le révoquer/régénérer immédiatement (mot de passe de base de données, clé API si applicable) — un `git revert` ne suffit pas, un secret exposé doit être considéré compromis définitivement.

## Un déploiement de modèle doit être arrêté en urgence

Voir `rollback.md` Section 3 : `POST /api/v1/admin/learning/models/{id}/deploy` peut être annulé via `POST /api/v1/admin/learning/models/{id}/rollback`, réservé aux administrateurs, audité (`audit_logs`, action `learning.model.rollback`).

## Latence anormalement élevée

1. Comparer aux références mesurées en Phase 11–12 (`docs/reports/phase-11-12-performance-resilience.md`, 13–25 ms en moyenne sur une machine de développement).
2. Le coût de connexion SQLite par requête est d'environ 3 ms mesuré isolément (Phase 11–12) : un écart bien plus important suggère un problème ailleurs (verrouillage SQLite sous contention, hachage de mot de passe avec un nombre d'itérations mal configuré — vérifier `Settings.password_iterations`, qui doit rester 600 000 en environnement réel, pas la valeur réduite utilisée dans les tests).
3. Si plusieurs threads/processus accèdent à la même base SQLite sous forte charge concurrente, du « database is locked » peut apparaître : c'est un signal que SQLite a atteint sa limite pour ce volume, pas un bug à corriger dans le code applicatif — voir `production-readiness.md` (migration PostgreSQL).

## Contact et escalade

Ce document ne liste pas de contacts nominatifs (aucun n'a été fourni au moment de la rédaction) : les compléter avant tout déploiement réel, dans `config/policies/crisis-policy-v1.json::emergency_contacts` pour les urgences patient, et dans une liste d'astreinte technique séparée pour les incidents d'infrastructure.
