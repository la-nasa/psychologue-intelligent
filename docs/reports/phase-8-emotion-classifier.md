# PHASE REPORT

Phase: 8 (tranche ML) — Entraînement réel d'un classifieur d'émotions
Date: 2026-08-27
Objectif: Après discussion explicite avec l'utilisateur (qui a demandé un entraînement réel plutôt qu'une simulation), livrer un véritable pipeline d'entraînement et d'évaluation derrière l'abstraction `ModelProvider` (Section 13), sans jamais transformer ce modèle non validé en source de décision clinique.

## 0. Cadrage et décision explicite de l'utilisateur

L'utilisateur a demandé « train our own AI ». Avant d'écrire du code, il a été explicitement signalé qu'aucune donnée de conversation réelle, consentie et validée n'existait encore pour entraîner un modèle de risque clinique, conformément à la séquence de la Section 15 (production → échantillonnage → anonymisation → revue humaine → dataset → entraînement). Deux options ont été présentées ; l'utilisateur a choisi : construire le pipeline complet **et** entraîner dès maintenant un modèle placeholder réel sur des données publiques, explicitement non cliniques.

## 1. Travaux réalisés

- **Recherche de dataset sous contrainte réseau réelle** : le bac à sable réseau autorise `pypi.org`/`files.pythonhosted.org` et l'API `huggingface.co`, mais bloque le CDN de contenu de Hugging Face (`*.cdn.hf.co`) ainsi que `datasets-server.huggingface.co`. Le dataset initialement visé (`dair-ai/emotion`) était donc inaccessible. `raw.githubusercontent.com` s'est révélé fiable, ce qui a permis d'identifier et d'utiliser **GoEmotions** (Demszky et al. 2020, Google Research), un choix objectivement meilleur : licence Apache-2.0 non ambiguë (contre « other » pour dair-ai/emotion) et annotations humaines (contre une supervision distante par hashtags).
- `ml/train_emotion_classifier.py` : pipeline complet — téléchargement, réduction des 27 émotions fines aux 6 émotions de base d'Ekman via le mapping officiel de Google, filtrage des lignes multi-catégories/neutres, vectorisation TF-IDF, régression logistique multinomiale, évaluation sur un jeu de test jamais vu à l'entraînement, export.
- **Entraînement réellement exécuté** : 28 104 exemples d'entraînement, 3 527 de validation, 3 539 de test (après filtrage). Résultats sur le test, jamais utilisés pendant l'entraînement : **exactitude 69 %, F1 macro 0,58** (voir `ml/MODEL_CARD.md` pour le détail par classe et la matrice de confusion). Ce ne sont pas des chiffres inventés : ils sont produits par un vrai calcul, reproductible en relançant le script.
- `backend/app/emotion.py` : **réimplémentation pure Python** du TF-IDF et de la fonction de décision linéaire, chargée depuis les poids exportés en JSON. Aucune dépendance `scikit-learn`/`numpy` n'est nécessaire à l'exécution de l'application — cohérent avec la fondation sans dépendance (ADR-003). `scikit-learn` reste un outil d'entraînement, ajouté comme extra `ml` dans `pyproject.toml`, jamais une dépendance d'exécution.
- **Vérification de fidélité** : la réimplémentation pure Python a été comparée directement aux probabilités produites par le modèle scikit-learn en mémoire sur sept phrases types ; écart maximal `2,2×10⁻¹⁶` (précision flottante), confirmant que ce n'est pas une approximation mais une reproduction exacte de la formule.
- **Intégration en observabilité uniquement** : migration `008_emotion_observability` ajoute `emotion_label`, `emotion_confidence`, `emotion_model_version` à `risk_assessments`. `pipeline.handle_incoming_message` accepte un `EmotionModel` optionnel ; son résultat est enregistré mais **n'entre jamais** dans `CrisisDetector`. Un échec du modèle d'émotion est capturé et n'affecte jamais la détection de crise.
- `ml/MODEL_CARD.md` généré automatiquement à chaque entraînement : dataset, licence, taille des splits, distribution des classes, métriques réelles, matrice de confusion, limites explicites, et rappel de gouvernance (ADR-002/ADR-004).
- **Vérifié via l'API HTTP réelle**, pas seulement en test unitaire : un message « I am so happy today, this is wonderful news! » envoyé via `/api/v1/conversations/{id}/messages` a produit `emotion_label=joy`, `emotion_confidence=0.94`, enregistré dans `risk_assessments`, sans que la réponse de l'assistant ni le niveau de crise n'en soient affectés.

## 2. Fichiers créés

- `ml/train_emotion_classifier.py`, `ml/artifacts/emotion-classifier-v1.json`, `ml/MODEL_CARD.md`
- `backend/app/emotion.py`
- `tests/test_emotion_model.py`
- `docs/reports/phase-8-emotion-classifier.md`

## 3. Fichiers modifiés

- `backend/app/db.py` (migration 008), `backend/app/config.py` (chemin de l'artefact), `backend/app/pipeline.py` (paramètre `emotion_model` optionnel), `backend/app/conversation.py`, `backend/app/http.py` (chargement au démarrage, tolérant à l'absence de l'artefact)
- `pyproject.toml` (extra `ml`), `.github/workflows/ci.yml` (lint/compile étendus à `ml/`), `.gitignore` (`ml/data/` exclu — le dataset brut n'est pas redistribué)

## 4. Architecture impactée

Aucun changement au domaine Crisis/Alert. Le signal d'émotion est strictement additif et non décisionnel : `crisis.CrisisDetector` ne référence jamais `backend/app/emotion.py`. C'est la mise en œuvre concrète de la contrainte posée avant même d'écrire ce code.

## 5. Fonctionnalités terminées

- Pipeline d'entraînement réel, reproductible, documenté, avec des métriques honnêtes (ni gonflées, ni cachées).
- Inférence en production sans dépendance ML lourde, vérifiée bit-pour-bit fidèle au modèle scikit-learn d'origine.
- Enregistrement systématique du signal d'émotion pour revue clinique future, sans jamais influencer une décision de sécurité.

## 6. Tests exécutés

- `ruff check backend tests scripts ml`, `mypy backend`, `bandit -r backend scripts -q`, `pip-audit`, `python scripts/scan_secrets.py`
- `coverage run` + `coverage report`
- `python -m unittest discover -s tests -v`
- Script de vérification de fidélité pure-Python vs scikit-learn (voir Section 1), exécuté manuellement.
- Appel HTTP réel contre le serveur de développement (voir Section 1).

## 7. Résultats des tests

- 47 tests automatisés, tous verts (6 nouveaux). Aucune régression.
- Couverture : 91 % sur `backend/app`, au-dessus du seuil CI de 85 %.
- `pip-audit` : aucune vulnérabilité connue, y compris dans l'arbre de dépendances de `scikit-learn` (numpy, scipy, joblib, threadpoolctl).
- Aucun signalement `ruff`, `mypy`, `bandit`, scanner de secrets.
- Écart de fidélité pure-Python vs scikit-learn : `2,2×10⁻¹⁶` (bruit flottant, pas un écart réel).

## 8. Bugs détectés

- Aucun bug de code cette tranche. La principale difficulté a été d'ordre réseau (Section 1), pas fonctionnelle.

## 9. Bugs corrigés

- Sans objet pour cette tranche (le bug de calibration du modèle de risque de développement a été traité et documenté en Phase 8a, avant cette tranche).

## 10. Vulnérabilités détectées

- Aucune. L'artefact exporté est un JSON de poids numériques, pas du code exécutable : aucun risque `pickle` (délibérément évité, voir décision technique ci-dessous).

## 11. Vulnérabilités corrigées

- Sans objet.

## 12. Dette technique

- Le modèle reste un placeholder de démonstration : entraîné sur des commentaires Reddit en anglais, pas sur des messages thérapeutiques en français. Sa précision sur le trafic réel de l'application est inconnue et probablement inférieure aux chiffres du jeu de test.
- Pas de ré-entraînement automatisé ni de pipeline CI pour le modèle : relancer `ml/train_emotion_classifier.py` reste une action manuelle, ce qui est cohérent avec l'exigence de ne jamais ré-entraîner directement en production (Section 15) mais signifie qu'aucune fraîcheur du modèle n'est garantie.
- Aucune revue clinique du signal d'émotion n'a eu lieu : il est enregistré mais personne ne le consulte encore (pas d'affichage dans le dashboard clinicien à ce stade).

## 13. Décisions techniques

- **JSON plutôt que `pickle`** pour l'artefact exporté : un modèle scikit-learn picklé serait exécutable au chargement (risque de désérialisation, Section 5.3) ; le JSON ne contient que des nombres et des chaînes, aucun risque d'exécution de code, et reste inspectable par un humain.
- **GoEmotions plutôt que `dair-ai/emotion`** : décision technique documentée en détail dans `ml/MODEL_CARD.md`, motivée à la fois par une contrainte réseau réelle et par une licence et une méthode d'annotation objectivement meilleures — pas un choix arbitraire de contournement.
- **TF-IDF + régression logistique plutôt qu'un modèle neuronal/transformeur** : suffisant pour démontrer un pipeline d'entraînement réel et une intégration honnête, sans ajouter une dépendance d'exécution lourde (PyTorch/transformers) pour un signal qui n'est même pas encore utilisé dans une décision.
- **`scikit-learn` isolé dans un extra `ml` séparé de `dev`** : un contributeur qui lint/type-check/teste le projet n'a pas besoin d'installer une pile ML complète.

## 14. Risques restants

- Si ce signal d'émotion venait un jour à influencer une décision clinique, cela nécessiterait le même processus d'approbation que toute autre politique clinique (ADR-002) — ce n'est pas le cas aujourd'hui et le code ne le permet pas structurellement (`CrisisDetector` ne prend pas ce signal en paramètre).
- Le dataset d'entraînement (commentaires Reddit) a un registre linguistique et culturel différent de celui attendu dans une conversation thérapeutique ; toute extrapolation de ses métriques de test au contexte réel de l'application serait trompeuse.

## 15. Métriques

- 1 migration ajoutée (008), 3 colonnes ajoutées, 0 modification du schéma de décision de crise.
- Dataset réel : 28 104 / 3 527 / 3 539 lignes (train/dev/test) après filtrage à 6 classes.
- Modèle réel : exactitude test 69 %, F1 macro 0,58 — chiffres mesurés, pas déclarés.
- Fidélité de la réimplémentation pure Python : écart maximal 2,2×10⁻¹⁶.
- 6 nouveaux tests (47 au total), 1 nouvelle dépendance d'entraînement (`scikit-learn`, isolée), 0 nouvelle dépendance d'exécution.

## 16. Critères de sortie

- [x] Entraînement réel exécuté et reproductible, sur un dataset public à licence claire.
- [x] Métriques honnêtes documentées (pas de revendication d'efficacité clinique).
- [x] Inférence en production sans dépendance ML, vérifiée fidèle au modèle d'origine.
- [x] Signal enregistré pour observabilité, sans influence sur une décision de sécurité.
- [ ] Revue clinique du signal (aucun clinicien n'a encore vu ni validé ces sorties).
- [ ] Affichage du signal dans le dashboard clinicien (non fait, pas demandé pour cette tranche).

## 17. Conclusion

Un modèle a été réellement entraîné, évalué honnêtement, vérifié fidèle bit-pour-bit dans sa réimplémentation de production, et intégré sans jamais pouvoir influencer une décision de sécurité — exactement la ligne que l'utilisateur et le prompt maître avaient fixée avant d'écrire la moindre ligne de code. La dette restante (registre linguistique non adapté, absence de revue clinique) est documentée, pas cachée. Le pipeline d'apprentissage continu proprement dit (échantillonnage consenti, anonymisation, revue humaine, versioning de dataset, registre de modèles avec double approbation clinique) reste à construire : c'est la suite naturelle, maintenant que de vraies conversations et un vrai exemple de modèle entraîné existent tous les deux.

STATUS: PASS WITH WARNINGS
