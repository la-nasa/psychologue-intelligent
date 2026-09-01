# PHASE REPORT

Phase : 10 (V2) — Canaux de notification réels + workers
Date : 2026-09-01
Objectif : Adaptateur e-mail réel (SMTP), canaux de notification **par organisation**, échange d'événements RabbitMQ, worker périodique cadençant les fonctions déjà écrites (`sla_sweep`, `retry_pending_notifications`, rappels PHQ-9).

STATUS : **PASS** (gate exécutée le 2026-09-01)

---

## 1. Livré

### Adaptateurs de notification (`app/application/notifications.py`)
- **`EmailNotificationProvider`** : SMTP via `aiosmtplib`. Le corps est **volontairement dénué de contenu clinique** (TH-03) — niveau d'alerte, identifiant d'alerte, consigne de consulter le tableau de bord. Jamais le nom du patient, le texte du message, ni un score.
- **`CompositeNotificationProvider`** : aiguille selon le type de canal (`email` → SMTP ; `sms`/`push`/`log` → `LogNotificationProvider` en attendant de vrais fournisseurs). C'est désormais le provider câblé dans `app.state`.

### Canaux par organisation (`0009_notification_channels`, `app/application/channels.py`)
- Table `notification_channels` (RLS) : `name`, `kind` ∈ {email, sms, push, log}, `target_enc` **chiffrée**, `is_active`.
- `resolve(session, org_id, policy_channels)` : renvoie les canaux **actifs de l'organisation** ; repli sur les canaux nommés dans la politique de crise uniquement s'il n'y en a aucun en base — et un canal de repli est de type `log` (dev), jamais un destinataire réel deviné.
- `notifications.channel_kind` + `target_enc` ajoutés sur chaque ligne de notification → la reprise (`retry_pending_notifications`) a tout ce qu'il faut sans re-résoudre.
- API admin (`app/api/admin.py`, rôle `ADMIN`/`SUPER_ADMIN`) : `GET`/`POST /api/v1/admin/notification-channels`. La liste ne renvoie jamais la cible en clair, seulement un indice (`on***@clinic.example.com`).

### Événements RabbitMQ (`app/infrastructure/mq.py`)
- `publish_event(routing_key, body)` sur l'échange topic durable `pi.events`. **Best-effort, jamais bloquant** : si le broker est injoignable ou `PI_MQ_ENABLED=false`, renvoie `False` sans lever — l'alerte est déjà persistée et notifiée de façon synchrone. Un événement `alert.created.{level}` est publié à l'ouverture de chaque alerte (analytics + futur traitement piloté par événements).
- Désactivé dans la suite de tests (`mq_enabled=False` en `PI_ENV=testing`).

### Worker (`app/workers/scheduler.py`, service compose `worker`)
Boucle toutes les 60 s, sur une `system_session` : `sla_sweep` → `retry_pending_notifications` → `send_due_reminders`. Les trois fonctions sont déjà idempotentes et testées ; le worker ne fait que les cadencer. Arrêt propre sur SIGINT/SIGTERM. Lancement : `python -m app.workers.scheduler`.

### Rappels (`app/application/reminders.py`)
`send_due_reminders` marque `SENT` les `assessment_reminders` échus + audit. **Limite assumée** : l'envoi effectif au patient n'est pas branché (demande le canal du patient + une décision produit sur la fréquence acceptable) — documenté, pas simulé.

## 2. Invariants vérifiés

| Invariant | Test |
| --- | --- |
| L'e-mail d'alerte ne contient **aucune** donnée de santé (contenu, nom, score, id patient) — seul l'id d'alerte | `test_notifications_email.py::test_email_channel_delivers_a_content_free_alert` (SMTP → mailpit, vérifié via l'API mailpit) |
| Cible du canal chiffrée au repos ; jamais exposée en clair par la liste | `test_channels.py::test_channel_target_is_encrypted_at_rest`, `::test_list_channels_hints_target_never_exposes_it` |
| Résolution : canaux configurés priment ; repli politique en type `log` | `test_channels.py::test_resolve_prefers_configured_channels`, `::test_resolve_falls_back_to_policy_channels_as_log` |
| Canaux isolés par organisation | `test_channels.py::test_channels_are_isolated_between_organizations` |
| Endpoint admin refusé à un `PATIENT` | `test_channels.py::test_admin_channel_endpoint_requires_privilege` |
| `run_once` enchaîne les 3 tâches, idempotent | `test_worker.py::test_run_once_escalates_overdue_alerts_and_sends_due_reminders` |
| Publication d'événement jamais bloquante (broker absent → `False`) | `mq_enabled=False` en test ; publication silencieuse |
| Notification de crise reste **synchrone** (l'alerte n'attend pas le worker) | inchangé — `test_safety_pipeline.py`, `test_alert_lifecycle.py` |

## 3. Résultats de vérification

Exécutés dans l'image `server` (Docker, `docker compose run --rm --no-deps api`),
Postgres + Redis + Mailpit up, `PI_ENV=testing`.

| Contrôle | Résultat |
| --- | --- |
| `python -c 'import app.main; import app.workers.scheduler'` | OK |
| `ruff check .` | All checks passed |
| `mypy app` | Success: no issues found in 71 source files |
| `bandit -r app scripts -q` | 0 issue (le faux positif B613 « trojan-source » sur `normalize.py` est levé : les caractères invisibles sont désormais construits par point de code, aucun ne figure dans le source) |
| `pytest` | **250 passed** (dont red-team IA + e-mail SMTP réel → Mailpit) |
| `coverage` | **89 %** (seuil 85 %) |
| `pip-audit` | **No known vulnerabilities found** — `aiosmtplib` relevé `4.0.2 → 5.1.2` (PYSEC-2026-2338 + CVE-2026-55558) |
| `alembic downgrade base && alembic upgrade head` | OK, réversible 0001 → 0009 |
| `python -m app.workers.scheduler` | démarre (`worker_started`), s'arrête proprement sur SIGTERM (`worker_stopped`) |

### Corrections apportées pendant la gate

| # | Constat | Correction |
| --- | --- | --- |
| C-1 | `Dockerfile` : `RUN … && pip install -e ".[dev]" && … \|\| true` — le `\|\| true` final masquait l'échec de l'installation des dépendances ; l'image « réussissait » sans `structlog`, `ruff`, etc. | Découpé en `RUN` distincts ; ajout d'un `--mount=type=cache,target=/root/.cache/pip` (le registre PyPI est instable depuis ce runner — les téléchargements reprennent au lieu d'échouer). |
| C-2 | `channels.create_channel` et `assessment.schedule_reminder` n'appelaient pas `session.flush()` (session `autoflush=False`) → ligne invisible dans la même session ; 3 tests rouges. | `await session.flush()` après `session.add(...)`, conforme au reste de la couche application. |
| C-3 | `bandit` B613 (HIGH) : caractères de contrôle bidi littéraux dans la regex `_ZERO_WIDTH` de `normalize.py`. | Classe de caractères reconstruite à partir des points de code (`chr(cp)`), plus aucun caractère invisible dans le source. |
| C-4 | `pip-audit` : `aiosmtplib==4.0.2` vulnérable. | Montée à `5.1.2` ; API `aiosmtplib.send(...)` inchangée, test e-mail bout-en-bout toujours vert. |

## 4. Ce qui n'est PAS fait

- **SMS / push réels** : `CompositeNotificationProvider` a les emplacements ; les adaptateurs (Twilio, FCM…) et leurs secrets sont hors périmètre — `kind='sms'`/`'push'` tombent sur le log en attendant.
- **Consommateur RabbitMQ** : les événements sont publiés ; un consommateur qui les traite (analytics temps réel, ré-notification pilotée par événement) est Phase 15. Le worker actuel est un cadenceur, pas un consommateur d'événements.
- **Outbox strictement transactionnelle** (TM-08 complet) : la notification reste un *burst* synchrone borné + reprise worker (modèle v1 éprouvé). La fenêtre résiduelle (panne entre l'écriture `PENDING` et la mise à jour finale) est réduite mais pas fermée — réclamation par verrouillage optimiste sur les deux chemins, à faire.
- **Envoi de rappel au patient** : marqué `SENT` + audité, pas livré (voir §1).
- **Vérification de délivrabilité e-mail** (bounce, DKIM…) : non — dépend du fournisseur SMTP de production.

## 5. Critères de sortie — Gate Phase 10

- [x] Adaptateur e-mail SMTP, corps sans contenu clinique.
- [x] Canaux par organisation (table RLS, cible chiffrée, CRUD admin, résolution + repli).
- [x] Échange d'événements RabbitMQ, publication best-effort non bloquante.
- [x] Worker périodique cadençant sla_sweep + retry + rappels, idempotent, arrêt propre.
- [x] Notification de crise toujours synchrone (pas de régression de sûreté).
- [x] `pytest` vert (250) ; couverture 89 % ≥ 85 % ; `ruff`/`mypy`/`bandit`/`pip-audit` propres ; migration réversible 0001→0009 ; worker démarre et s'arrête proprement.

## 6. Conclusion

Une alerte peut maintenant réellement partir par e-mail vers le destinataire que **chaque établissement** configure lui-même, sans qu'aucune donnée de santé ne quitte l'application. Les tâches d'entretien (escalade SLA, reprise de notification, rappels) tournent dans un worker séparé au lieu d'attendre qu'une requête les déclenche, et RabbitMQ transporte les événements de domaine pour un traitement analytique ultérieur — le tout sans jamais mettre la notification de crise sur un chemin asynchrone. La **Phase 11** (voix temps réel) était marquée « plus tard » en décision D-3 ; la suite naturelle est la **Phase 12** (plateforme clinicien : dashboard, Alert Center, relation patient-clinicien, actions sur alerte).

STATUS : **PASS** — gate complète verte. Prochaine étape : Phase 12 (plateforme clinicien).
