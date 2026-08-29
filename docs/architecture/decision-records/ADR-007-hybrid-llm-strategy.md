# ADR-007 — Stratégie LLM hybride : petit modèle local (FAST) + API externe sous consentement (DEEP)

Date : 2026-08-28
Statut : **Accepté**. Étend [ADR-005](ADR-005-generative-responder.md) (répondeur génératif auto-hébergé).
Décideur : utilisateur (décision D-2 de `docs/reports/phase-0-audit-v2.md`).

## Contexte

ADR-005 a introduit un répondeur génératif auto-hébergé (`llama-cpp-python`, Qwen2.5-1.5B, CPU). Latence mesurée en conditions réelles sur Railway : **30 s à plus d'une minute par réponse**. Les cibles d'ingénierie du Prompt Maître V2 (§14) sont : premier token < 1–2 s, tour normal < 2–3 s. **L'écart est d'un ordre de grandeur** et n'est pas réductible par du réglage sur CPU partagé (deux tentatives de tuning `n_threads` ont dégradé la latence — voir ADR-005).

Trois options ont été posées en Phase 0 (D-2) :
- (a) API externe → sortie des données patient du système ;
- (b) GPU dédié → données internes, coût fixe mensuel élevé ;
- (c) hybride ;
- (d) rester CPU et documenter le non-respect de §14.

## Décision

**Option (c) — hybride, avec le consentement du patient comme condition du chemin externe.**

### Deux chemins de génération (aligné sur §15 du prompt : FAST PATH / DEEP PATH)

| Chemin | Déclencheur | Modèle | Latence visée | Données |
| --- | --- | --- | --- | --- |
| **FAST** | Messages GREEN de faible complexité : salutations, confirmations, accusés courts, relances simples (classé par `DialoguePolicy`, voir `overview-v2.md`) | Petit modèle local (Qwen2.5-1.5B ou équivalent), **quantifié, sur GPU si disponible sinon CPU** | < 2 s si GPU, best-effort sinon | Ne quittent jamais l'hébergement |
| **DEEP** | Messages GREEN complexes : historique important, évolution émotionnelle, ambiguïté, besoin de nuance | **API externe** (Anthropic Claude par défaut, port `LLMProvider` interchangeable) | < 2 s premier token | **Transitent vers le fournisseur** — d'où la condition de consentement ci-dessous |

### Le chemin DEEP est conditionné à un consentement explicite et distinct

- Nouveau `purpose` de consentement : **`AI_EXTERNAL`** (s'ajoute à `CARE` et `LEARNING`, versionné comme eux — voir `data-model-v2.md`).
- **Sans consentement `AI_EXTERNAL` actif**, un message qui aurait été routé DEEP est traité par le modèle local (FAST), avec dégradation de qualité assumée plutôt que transfert non consenti.
- Le consentement `AI_EXTERNAL` est **révocable** ; la révocation prend effet au message suivant.
- L'écran de consentement nomme le fournisseur, le type de données transmises (contenu du message + contexte minimal), le pays de traitement, et la politique de rétention du fournisseur (pour Anthropic : pas d'entraînement sur les données API, rétention limitée — à re-vérifier et citer dans l'UI au moment de l'implémentation).

### Invariants préservés (identiques à ADR-004 / ADR-005)

- **Le LLM, local OU externe, ne décide jamais d'une crise.** La classification ORANGE/RED a lieu dans `SafetyEngine` **avant et indépendamment** de tout appel de génération. ORANGE/RED → gabarits fixes versionnés, jamais un modèle.
- **Aucune donnée de crise ne part vers l'externe** : puisque ORANGE/RED n'atteignent jamais le générateur, un message classé à risque n'est jamais envoyé à l'API externe, quel que soit le consentement.
- **Le contexte envoyé à l'externe est minimisé** (`ContextBuilder`, `overview-v2.md`) : jamais le score PHQ-9 brut (bande qualitative seulement), jamais les données d'un autre patient, jamais d'identifiant direct.
- **`OutputSafety`** s'applique identiquement aux réponses locales et externes (PII, hallucination, cohérence de crise, revendication de diagnostic).

### Sélection du fournisseur

Le port `LLMProvider` (`generate` / `stream` / `health_check`) a plusieurs adaptateurs : `local` (vLLM ou llama.cpp), `anthropic`, `openai`, `openai-compatible`. Le `ModelRouter` choisit FAST/DEEP puis l'adaptateur, sur configuration (`FAST_MODEL`, `STANDARD_MODEL`, `DEEP_REASONING_MODEL`). Aucun couplage dur à un fournisseur.

## Conséquences

- **Positif** : la majorité des tours (courts, GREEN simples) restent 100 % internes et rapides ; les tours qui bénéficient réellement d'un grand modèle en profitent, sans imposer le transfert à tous.
- **Positif** : le consentement `AI_EXTERNAL` rend le choix explicite et auditable, et donne au patient un contrôle réel.
- **Négatif** : deux chemins = deux fois plus de surface à tester (routage, repli sans consentement, `OutputSafety` sur les deux) ; coût d'API à l'usage à suivre (`AI cost control`, §105, dès Phase 15).
- **Négatif** : dépendance à la disponibilité d'un fournisseur externe pour le chemin DEEP → `health_check` + repli automatique sur le modèle local en cas d'indisponibilité (mode dégradé, §75).
- **Risque R-04** : intégrer un LLM génératif à pleine surface rouvre TH-04 (prompt injection). Mitigation : `OutputSafety` obligatoire, mémoire/RAG traités comme données jamais comme instructions, suite AI red team (Phase 7 puis Phase 18), rayon d'impact borné par l'indépendance du moteur de crise.
- **Clé API externe** : secret géré hors Git (gestionnaire de secrets, §95), jamais dans les logs, rotation documentée dans le runbook.

## Alternatives rejetées

- **(a) tout API externe** : rejetée — imposerait le transfert des données de chaque tour, y compris les plus banals, sans bénéfice proportionné.
- **(b) GPU dédié pour tout** : non retenue comme point de départ (coût fixe mensuel significatif avant d'avoir un usage réel), mais reste la trajectoire cible si le volume DEEP le justifie — le port `LLMProvider` permet de basculer l'adaptateur `local` de llama.cpp vers vLLM/GPU sans toucher au reste.
- **(d) rester CPU et documenter** : rejetée — rend le produit conversationnel peu utilisable en pratique, ce qui est précisément le retour utilisateur qui a motivé ADR-005.
