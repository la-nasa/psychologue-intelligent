# PHASE REPORT

Phase : 7 (V2) — Safety Engine complet
Date : 2026-09-01
Objectif : Remplacer l'`OutputSafety` minimal de la Phase 4 par le pipeline complet ; nommer et cohérer les composants du moteur de sûreté (§28) ; formaliser `SAFE_FALLBACK` (§30) ; constituer la **suite AI red team** (§91).

STATUS : **PASS**.

---

## 1. Livré

### `OutputSafety` complet (`app/application/output_safety.py`)
Pipeline sur **toute** réponse générée (locale ou externe), pour une décision déjà GREEN :

1. **cohérence de crise** — appelé sur non-GREEN ⇒ remplacement immédiat.
2. **politique clinique** — revendication de diagnostic / posture clinique / identité humaine, conseil médicamenteux, fausse réassurance / minimisation.
3. **auto-agression** — contenu de méthode.
4. **fuite du message système** — la réponse répète le prompt.
5. **PII** — e-mail / téléphone **rédigés** (la réponse par ailleurs correcte est conservée).
6. **longueur** — tronquée.

Résultat structuré : `list[SafetyFinding]`, `text`, `replaced`, `reason`. Toute violation de catégorie 1-4 ⇒ `green_acknowledgments[0]` (repli neutre, jamais la sortie brute). Ce sont des garde-fous lexicaux conservateurs : le faux positif est acceptable, le faux négatif ne l'est pas.

### `SAFE_FALLBACK` (§30)
- Nouveau champ `safe_fallback` dans `response-templates-v1.json` (versionné, approval-gated comme le reste) : « difficulté technique, message enregistré, urgence → ressources locales ».
- `ConversationOrchestrator` : **toute** défaillance de génération (fournisseur externe puis local en échec, exception inattendue) ⇒ `safe_fallback` persisté et marqué `safe_fallback:generation_error`, jamais un 500 sans réponse ni une réponse partielle non vérifiée livrée telle quelle.

### Cohérence des composants (§28)
- `application/escalation.py` — **`EscalationEngine`** extrait de `safety.py` (décision → alerte idempotente + SLA + notification). Comportement inchangé, couvert par `test_safety_pipeline.py`.
- `domain/safety/engine.py` — vue d'ensemble documentée : `RuleEngine` / `RiskClassifier` / `CrisisDetector` / `PolicyEngine` / `EscalationEngine` / `OutputSafety` et où chacun vit.

### Suite AI red team (`server/tests/ai_redteam/`, marqueur `-m ai_redteam`)
Chaque test envoie une entrée adverse au moteur réel. Un `NaiveEchoProvider` (fournisseur entièrement « injectable » qui renvoie le texte demandé) sert à vérifier que le *système* contient une injection réussie — pas seulement que le fournisseur local est non génératif.

| Fichier | Couvre (OWASP LLM) | Vérifie |
| --- | --- | --- |
| `test_prompt_injection.py` | LLM01 | injection reste GREEN + pas de fuite prompt ; ne peut pas abaisser/désactiver une crise ultérieure ; injection + signal de crise dans le même message → escalade ; même un LLM injectable ne casse pas l'indépendance de la crise ; `OutputSafety` attrape un écho dangereux |
| `test_system_prompt_extraction.py` | LLM07 | aucune tentative d'extraction ne divulgue le prompt (local + écho + OpenAPI) |
| `test_unsafe_content.py` | LLM09 / LLM06 | 7 réponses dangereuses (diagnostic, médicaments, fausse réassurance, méthode, écho de prompt) remplacées ; réponse normale laissée passer ; PII rédigée sans perdre le message |
| `test_context_poisoning.py` | LLM01 / LLM04 | `about_me` et mémoire encadrés comme données ; `about_me` empoisonné ne casse pas la crise ; impact borné à un GREEN |
| `test_leakage.py` | LLM02 | un patient ne peut pas tirer la mémoire d'un autre dans son contexte ; `memory.retrieve` scopé |
| `test_crisis_robustness.py` | MEASURE / robustesse | **honnête sur les limites** : variantes simples (casse/accents/mot nu) attrapées ; obfuscation (leetspeak, espacement, phonétique) **non attrapée** par le moteur de règles seul (tests qui documentent l'écart, à corriger = améliorer le moteur, jamais à supprimer) ; faux positif « article sur le suicide » documenté ; un message calme reste GREEN |

## 2. Résultats de vérification

| Contrôle | Résultat |
| --- | --- |
| `pytest` | **166 tests** (133 + 33 red team), ~44 s |
| `pytest -m ai_redteam` | **33 passent** |
| `coverage` | **91 %** (seuil 85 %) |
| `ruff` / `mypy` / `bandit` / `pip-audit` | propres |
| `alembic downgrade base && upgrade head` | réversible (0001→0006, pas de nouvelle migration) |

## 3. Ce qui n'est PAS fait

- **Détection ML des sorties non sûres** : `OutputSafety` est lexical. Un classifieur de sécurité (Phase 8 : modèles distincts) affinerait précision/rappel. Les garde-fous actuels sont volontairement larges.
- **Robustesse du moteur de crise à l'obfuscation** : documenté comme écart mesuré (`test_crisis_robustness.py`). Le modèle de risque entraîné (Phase 8) et une revue clinique des règles le réduiront.
- **Faux positifs de la règle par sous-chaîne** (« article sur le suicide » → escalade) : documenté. Un contexte négatif (« j'ai lu / un article / à la télé ») serait une amélioration du `RuleEngine`.
- **AI red team par un tiers** : Phase 22, non substituable par cette suite interne.
- **Détection de PII non structurée** dans les sorties (noms propres, adresses) : hors périmètre lexical.
- **Pipeline `OutputSafety` sur le chemin externe réel** : la logique s'applique déjà à toute sortie ; elle n'est exercée de bout en bout avec un vrai fournisseur externe que lorsqu'une clé est configurée.

## 4. Critères de sortie — Gate Phase 7

- [x] `OutputSafety` : cohérence crise, politique clinique, auto-agression, fuite prompt, PII, longueur — échec ⇒ `SAFE_FALLBACK`.
- [x] `SAFE_FALLBACK` formalisé (template versionné) + toute défaillance de génération ⇒ repli persisté, jamais un 500.
- [x] `EscalationEngine` extrait et nommé ; `SafetyEngine` documenté (§28).
- [x] Suite AI red team : prompt injection, extraction de prompt, jailbreak / conseils dangereux, empoisonnement de contexte, fuite inter-utilisateur, robustesse de crise.
- [x] Limites de la détection de crise **testées et documentées**, pas masquées.
- [x] `pytest` (dont `-m ai_redteam`) vert (166 / 33) ; couverture 91 % ; `ruff`/`mypy`/`bandit`/`pip-audit` propres.

## 5. Conclusion

La sortie générée est désormais filtrée par un pipeline réel avant d'atteindre le patient, toute défaillance de génération dégrade proprement, et la suite AI red team ancre les propriétés de sécurité face à un fournisseur adverse — y compris en documentant honnêtement ce que le moteur de règles ne sait pas encore faire. La **Phase 8** (PHQ-9 / assessment) est indépendante ; la **Phase 9** (risque/crise/alertes) reprendra `test_crisis_robustness` pour combler les écarts documentés avec un modèle de risque entraîné.

STATUS : **PASS**.
