# Psychologue Intelligent

Plateforme d’assistance en santé mentale conçue pour un pilote supervisé. Elle ne pose pas de diagnostic, ne remplace pas un professionnel humain et ne doit pas être utilisée pour traiter une urgence sans procédure locale validée.

## État du projet

Phase 14+ (audit de sécurité complet) — fondation complète : plateforme patient, PHQ-9, moteur de crise indépendant du LLM, tableau de bord clinicien, console d’administration, un cœur conversationnel dont les réponses GREEN sont désormais générées par un modèle auto-hébergé personnalisé au profil du patient (ADR-005 — [`docs/architecture/decision-records/ADR-005-generative-responder.md`](docs/architecture/decision-records/ADR-005-generative-responder.md)), un modèle d’émotion réellement entraîné (observabilité uniquement) et le pipeline d’apprentissage continu complet, durcis par une suite de tests de sécurité adversariaux, un threat model synchronisé avec le code réel, et les quatre parcours de bout en bout du prompt maître automatisés. Le moteur de crise reste structurellement indépendant du répondeur, génératif ou non : ORANGE/RED ne passent jamais par lui, vérifié par test. Un audit de sécurité méthodique (OWASP/CWE/STRIDE) a trouvé et corrigé 3 vulnérabilités réelles — la plus sérieuse une race condition contournant l’invariant « un rejet clinique bloque définitivement un modèle » — chacune reproduite avant correction, corrigée à la cause racine, et couverte par un test de régression permanent ([`docs/security/security-assessment-report.md`](docs/security/security-assessment-report.md)). Un worker de reprise de notifications avec backoff exponentiel et lettre morte explicite ([`scripts/retry_notifications.py`](scripts/retry_notifications.py)) réduit sans totalement fermer l’écart historique sur la fiabilité de livraison (TM-08). Spécification API complète et validée en CI ([`docs/api/openapi.yaml`](docs/api/openapi.yaml)), rapport final synthétisant les 17 rapports de phase ([`docs/reports/final-report.md`](docs/reports/final-report.md)), et documentation de déploiement/rollback/runbook honnête sur ce qui existe et ce qui ne l’est pas encore ([`docs/deployment/`](docs/deployment/)). **Non recommandé pour un déploiement avec de vrais patients en l’état** : voir `docs/deployment/production-readiness.md` pour les conditions préalables non négociables (aucun canal de notification réel, aucune infrastructure de production, aucune validation clinique, aucun test d’intrusion externe).

## Démonstration en ligne

Une démonstration technique tourne sur Railway : https://web-production-58f77a.up.railway.app (`/clinician/`, `/admin/`). **Ce n'est pas un déploiement pilote** — voir [`docs/deployment/railway.md`](docs/deployment/railway.md) pour ce qui est réellement déployé, y compris trois pièges de plateforme rencontrés et corrigés (dont un volume signalé comme monté par un outil d'infrastructure alors qu'il ne l'était pas), et `production-readiness.md` pour l'écart complet avant tout pilote réel.

## Vérifier la qualité et la sécurité localement

```bash
pip install -e ".[dev]"
ruff check backend tests scripts ml
mypy backend
python -m unittest discover -s tests -v
coverage run -m unittest discover -s tests && coverage report
bandit -r backend scripts -q
pip-audit
python scripts/scan_secrets.py
python scripts/validate_openapi.py
```

## Ré-entraîner le classifieur d'émotions (optionnel)

```bash
pip install -e ".[ml]"
python ml/train_emotion_classifier.py
```

Télécharge GoEmotions (Apache-2.0) depuis GitHub, entraîne et évalue le modèle, régénère `ml/artifacts/emotion-classifier-v1.json` et `ml/MODEL_CARD.md`. Voir le modèle card pour les métriques réelles, la portée et les limites — ce n'est pas un modèle clinique.

## Activer le répondeur génératif (optionnel, ADR-005)

Désactivé par défaut (`PI_RESPONDER_MODE=templated`) : la fondation reste testable et exécutable sans aucune dépendance supplémentaire (ADR-003). Pour l'activer localement :

```bash
pip install -e ".[llm]"
export PI_RESPONDER_MODE=local-llm
export PI_LLM_MODEL_PATH=work/models/qwen2.5-1.5b-instruct-q4_k_m.gguf
python scripts/bootstrap_llm_model.py   # télécharge ~2,1 Go une seule fois, idempotent
```

N'importe où ailleurs dans le code, `llama_cpp` n'est jamais importé qu'à l'intérieur de `backend/app/local_llm.py`, et seulement si ce mode est actif : la suite de tests complète (`python -m unittest discover -s tests`) passe sans cette dépendance installée. Voir l'ADR pour les limites assumées (latence CPU, appels sérialisés, aucune revue humaine du contenu généré encore menée).

## Principes non négociables

- Le moteur de crise est indépendant du LLM et applique des politiques versionnées.
- Les décisions cliniques critiques exigent une validation humaine et locale.
- Les données d’apprentissage requièrent consentement explicite, anonymisation, revue humaine et approbation avant déploiement.
- L’autorisation est contrôlée côté serveur et refuse par défaut.

Consulter [l’architecture](docs/architecture/overview.md), le [modèle de données](docs/architecture/data-model.md), les [décisions d'architecture](docs/architecture/decision-records/) (dont ADR-005 sur le répondeur génératif), la [spécification API](docs/api/openapi.yaml), le [threat model](docs/security/threat-model.md), le [rapport d’audit de sécurité](docs/security/security-assessment-report.md), le [rapport final](docs/reports/final-report.md), les [rapports de phase](docs/reports/) et la [documentation de déploiement](docs/deployment/) (procédure locale, déploiement Railway, écart avant pilote, rollback, runbook).
