# Psychologue Intelligent

Plateforme d’assistance en santé mentale conçue pour un pilote supervisé. Elle ne pose pas de diagnostic, ne remplace pas un professionnel humain et ne doit pas être utilisée pour traiter une urgence sans procédure locale validée.

## État du projet

Phase 14+ (audit de sécurité complet) — fondation complète : plateforme patient, PHQ-9, moteur de crise indépendant du LLM, tableau de bord clinicien, console d’administration, cœur conversationnel, un modèle d’émotion réellement entraîné (observabilité uniquement) et le pipeline d’apprentissage continu complet, durcis par une suite de tests de sécurité adversariaux, un threat model synchronisé avec le code réel, et les quatre parcours de bout en bout du prompt maître automatisés. Un audit de sécurité méthodique (OWASP/CWE/STRIDE) a trouvé et corrigé 3 vulnérabilités réelles — la plus sérieuse une race condition contournant l’invariant « un rejet clinique bloque définitivement un modèle » — chacune reproduite avant correction, corrigée à la cause racine, et couverte par un test de régression permanent ([`docs/security/security-assessment-report.md`](docs/security/security-assessment-report.md)). Un worker de reprise de notifications avec backoff exponentiel et lettre morte explicite ([`scripts/retry_notifications.py`](scripts/retry_notifications.py)) réduit sans totalement fermer l’écart historique sur la fiabilité de livraison (TM-08). Spécification API complète et validée en CI ([`docs/api/openapi.yaml`](docs/api/openapi.yaml)), rapport final synthétisant les 17 rapports de phase ([`docs/reports/final-report.md`](docs/reports/final-report.md)), et documentation de déploiement/rollback/runbook honnête sur ce qui existe et ce qui ne l’est pas encore ([`docs/deployment/`](docs/deployment/)). **Non recommandé pour un déploiement avec de vrais patients en l’état** : voir `docs/deployment/production-readiness.md` pour les conditions préalables non négociables (aucun canal de notification réel, aucune infrastructure de production, aucune validation clinique, aucun test d’intrusion externe).

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

## Principes non négociables

- Le moteur de crise est indépendant du LLM et applique des politiques versionnées.
- Les décisions cliniques critiques exigent une validation humaine et locale.
- Les données d’apprentissage requièrent consentement explicite, anonymisation, revue humaine et approbation avant déploiement.
- L’autorisation est contrôlée côté serveur et refuse par défaut.

Consulter [l’architecture](docs/architecture/overview.md), le [modèle de données](docs/architecture/data-model.md), la [spécification API](docs/api/openapi.yaml), le [threat model](docs/security/threat-model.md), le [rapport d’audit de sécurité](docs/security/security-assessment-report.md), le [rapport final](docs/reports/final-report.md), les [rapports de phase](docs/reports/) et la [documentation de déploiement](docs/deployment/) (procédure locale, écart avant pilote, rollback, runbook).
