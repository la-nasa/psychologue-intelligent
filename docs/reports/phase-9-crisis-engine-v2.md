# PHASE REPORT

Phase : 9 (V2) — Approfondissement du moteur de risque / crise / alerte
Date : 2026-09-01
Objectif : Robustesse de la détection (obfuscation typographique), modèle de risque lexical derrière le port, harnais d'évaluation recall/precision, cycle de vie d'alerte complet (§32) avec état `NOTIFIED` automatique et balayage SLA.

STATUS : **PASS**.

---

## 1. Livré

### Normalisation durcie (`app/domain/safety/normalize.py`)
`harden(text)` : casse, accents, caractères invisibles, **leetspeak** (`4→a`, `1→i`, `0→o`, …), **espacement caractère par caractère** (`p l a n` → `plan`), **allongement** (`suiciiiide` → `suicide`). `crisis.normalize` l'utilise. `_rule_signal` fait un double appariement — normal **et** « sans espaces » — pour attraper l'écriture caractère par caractère où plusieurs mots fusionnent (`plansuicidaire` ← `plan suicidaire`).

### `LexiconRiskModel` (`app/ai/providers/lexicon_risk.py`) — nouveau défaut de production
Toujours **un signal parmi d'autres** (ADR-004). Entrée durcie, catégories pondérées (HIGH 0.95 / CONCERN 0.6), lexique plus large incluant des formes robustes à la variante phonétique (`me tue`, `me suicider`), et quelques tournures de **réassurance explicite** (`je ne veux pas mourir`) qui abaissent le score. Pas un modèle neuronal (pas d'infra d'entraînement) — une amélioration honnête de robustesse, mesurée.

### Harnais d'évaluation (`app/tests/eval/`)
`corpus.py` : ~28 messages français étiquetés (crises claires, crises obfusquées, détresse, GREEN clairs). **Limites assumées** (§47) : petit, écrit à la main, ne reflète pas la distribution réelle ni les variantes régionales.
`test_crisis_eval.py` : calcule recall / precision / faux négatifs / faux positifs pour le moteur de règles seul **et** avec le modèle lexical. Seuils : **recall ≥ 0.94** (une crise manquée est le pire échec), precision ≥ 0.85 (la sur-escalade est fail-safe). Bloque les régressions.

### Cycle de vie d'alerte (`0008_alert_lifecycle`, `app/application/alerting.py`)
- Nouvel état **`NOTIFIED`** (master prompt §32) entre `OPEN` et `ACKNOWLEDGED`. Posé **automatiquement** par l'`EscalationEngine` quand au moins un canal confirme l'envoi (`AlertAction` acteur système). `OPEN` reste l'état si aucun canal n'est configuré (honnête).
- `transition_alert` accepte `actor_id=None` (transitions système) ; `AlertAction.justification` = `"system"` par défaut dans ce cas.
- **`sla_sweep(session, now)`** : point d'entrée d'un worker périodique (Phase 10). Auto-escalade (`OPEN`/`NOTIFIED` → `ESCALATED`) les alertes dont `sla_due_at` est dépassé, avec audit. **Idempotent** ; ne touche jamais une alerte déjà prise en charge par un humain.

## 2. Invariants vérifiés

| Invariant | Test |
| --- | --- |
| Obfuscation (leet, espacement, allongement, phonétique) désormais attrapée | `test_crisis_robustness.py::test_obfuscated_crisis_phrasings_are_now_caught` |
| Réassurance explicite reste GREEN | `test_crisis_robustness.py::test_reassurance_phrasing_stays_green` |
| Écart résiduel documenté (mot de crise en contexte neutre → sur-escalade) | `test_crisis_robustness.py::test_known_gap_crisis_word_in_a_non_crisis_context_over_escalates` |
| Une panne de modèle n'abaisse jamais la prudence | `test_crisis_robustness.py::test_model_failure_never_lowers_caution` |
| Recall ≥ 0.94 / precision ≥ 0.85 (lexique) ; lexique ≥ règles sur le recall | `test_crisis_eval.py` |
| Alerte → `NOTIFIED` automatique à la confirmation d'envoi ; reste `OPEN` sans canal | `test_alert_lifecycle.py` |
| `sla_sweep` auto-escalade les alertes en retard, idempotent, épargne les alertes acquittées | `test_alert_lifecycle.py::test_sla_sweep_*` |
| Chemin complet `OPEN→NOTIFIED→ACKNOWLEDGED→IN_REVIEW→RESOLVED→CLOSED` | `test_alert_lifecycle.py::test_full_lifecycle_path` |
| Garde de concurrence sur les transitions (TV-15) conservée | `test_alerts.py::test_concurrent_conflicting_transitions_have_exactly_one_winner` |

## 3. Résultats de vérification

| Contrôle | Résultat |
| --- | --- |
| `pytest` | **238 tests** (198 + 40 Phase 9), ~38 s ; `-m ai_redteam` → 37 |
| recall / precision — moteur de règles seul (`KeywordRiskModel`) | recall **0.67**, precision **1.0** (ligne de base documentée, *insuffisant seul* — d'où le modèle) |
| recall / precision — chemin lexical (`LexiconRiskModel`, défaut prod) | recall **≥ 0.94**, precision **≥ 0.85** (seuils bloquants) |
| `coverage` | **90 %** (seuil 85 %) |
| `ruff` / `mypy` / `bandit` / `pip-audit` | propres |
| `alembic downgrade base && upgrade head` | réversible (0001→0008) |

## 4. Ce qui n'est PAS fait

- **Modèle de risque entraîné** (CamemBERT etc. évoqués §8) : pas d'infra PyTorch / GPU / données d'entraînement dans cet environnement. Le port `RiskModel` reste prêt ; le `LexiconRiskModel` est un palier, pas la cible.
- **Compréhension du contexte** : « j'ai lu un article sur le suicide » sur-escalade toujours (sous-chaîne). Fermer cet écart demande un vrai modèle + une revue clinique des règles — écart documenté, pas masqué.
- **Signaux temporels** (§29 : « Temporal Signals ») : la décision reste par message. L'agrégation (plusieurs messages concernants en peu de temps → escalade) est un ajout Phase 15 (analytics longitudinales).
- **Worker SLA / worker de notification** : `sla_sweep` et `retry_pending_notifications` sont des fonctions appelables ; le consommateur RabbitMQ / planificateur qui les déclenche périodiquement est Phase 10.
- **Endpoints cliniciens** pour agir sur une alerte : Phase 12 (il n'y a pas encore de relation patient-clinicien en V2).
- **`emergency_contacts` / canaux réels** : la politique porte le champ ; les adaptateurs Email/SMS/Push sont Phase 10.

## 5. Critères de sortie — Gate Phase 9

- [x] Normalisation durcie (leet, espacement, allongement, accents).
- [x] `LexiconRiskModel` derrière le port `RiskModel`, défaut de production.
- [x] Harnais d'évaluation recall/precision avec seuils bloquants.
- [x] Cycle de vie d'alerte : état `NOTIFIED` automatique.
- [x] Balayage SLA auto-escaladant, idempotent, worker-ready.
- [x] Garde de concurrence conservée.
- [x] `pytest` vert (238) ; recall lexique ≥ 0.94 ; couverture 90 % ; `ruff`/`mypy`/`bandit`/`pip-audit` propres ; migration réversible (0001→0008).

## 6. Conclusion

Le moteur de crise attrape maintenant l'obfuscation typographique courante que la Phase 7 avait honnêtement documentée comme un trou, et le recall est **mesuré** (pas supposé) sur un corpus étiqueté, avec un seuil qui bloque toute régression. L'alerte a un cycle de vie complet où l'on sait si un clinicien a réellement été notifié, et une alerte laissée sans réponse au-delà de son SLA s'escalade toute seule au lieu d'attendre. La **Phase 10** rend les canaux de notification réels et branche les workers (SLA, reprise de notification, rappels PHQ-9) sur RabbitMQ.

STATUS : **PASS**.
