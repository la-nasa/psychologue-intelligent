# Exécution locale de la fondation

Cette fondation utilise uniquement la bibliothèque standard Python et SQLite. Ce n'est pas une configuration de production clinique — voir `production-readiness.md` pour ce qui doit changer avant un pilote réel.

## Lancer l'application

```bash
python -m unittest discover -s tests -v      # suite de tests complète
python -m backend.app                        # API seule, sur http://127.0.0.1:8000
python scripts/dev_server.py                 # API + les 3 frontends (patient, /clinician/, /admin/) sur une seule origine
```

`scripts/dev_server.py` est un outil de développement uniquement (pas de TLS, pas de cache, pas de compression) — voir sa docstring.

## Provisionner un compte clinicien ou administrateur

Ces rôles ne s'auto-inscrivent jamais par l'API (voir `docs/reports/phase-7-clinician-dashboard.md`) :

```bash
python scripts/provision_user.py clinicienne@example.test CLINICIAN
python scripts/provision_user.py admin@example.test ADMIN
```

Le script génère un secret TOTP affiché une seule fois : à entrer dans une application d'authentification (Google Authenticator, Authy, etc.) pour se connecter.

## Reprendre les notifications en échec

`notify_alert()` retente 3 fois de façon synchrone, puis laisse une ligne durable `FAILED` avec un `next_retry_at` calculé par backoff exponentiel. Rien ne la reprend automatiquement entre-temps : ce script doit être exécuté périodiquement par un vrai ordonnanceur (cron, systemd timer, Planificateur de tâches Windows) — l'exécuter manuellement ici sert seulement à vérifier son comportement en local :

```bash
python scripts/retry_notifications.py
```

Au-delà de `MAX_TOTAL_ATTEMPTS` (10) tentatives cumulées, une notification reste `FAILED` avec `next_retry_at=NULL` : une lettre morte explicite, interrogeable, jamais silencieusement abandonnée. Voir `docs/deployment/runbook.md` pour la procédure d'investigation manuelle.

## Contrat d'API

Voir [`docs/api/openapi.yaml`](../api/openapi.yaml) (34 opérations) — c'est la source de vérité, pas cette page.

## Vérifier la qualité et la sécurité

```bash
pip install -e ".[dev]"
ruff check backend tests scripts ml
mypy backend
bandit -r backend scripts -q
pip-audit
python scripts/scan_secrets.py
python scripts/validate_openapi.py
coverage run -m unittest discover -s tests && coverage report
```

## Ré-entraîner le classifieur d'émotions (optionnel)

```bash
pip install -e ".[ml]"
python ml/train_emotion_classifier.py
```

## Avant un pilote réel

Voir `production-readiness.md` pour la liste complète. En résumé : remplacer SQLite par PostgreSQL, le limiteur de débit en mémoire par une implémentation distribuée, ajouter une gestion centralisée des secrets, brancher un vrai canal de notification, et faire examiner la configuration par la sécurité et l'équipe clinique.
