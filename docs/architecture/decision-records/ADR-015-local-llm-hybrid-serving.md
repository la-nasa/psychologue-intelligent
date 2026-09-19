# ADR-015 — Serving LLM local hybride (OpenAI-compat / GGUF / gabarits)

Date : 2026-09-18  
Statut : **Accepté**. Étend [ADR-007](ADR-007-hybrid-llm-strategy.md). Ne remplace pas le consentement `AI_EXTERNAL` du chemin DEEP.  
Ne pas confondre avec [ADR-012](ADR-012-hybrid-llm-redondant-incomplet.md) (rejeté : hybride sans consentement).

## Contexte

Le FAST path V2 utilisait `LocalSupportiveResponder` (gabarits). La démo V1 (Qwen2.5-1.5B CPU, Railway) a une latence de 30 s à plus d’une minute (ADR-005). Le prompt maître vise un premier token < 1–2 s : cela exige un GPU lorsqu’il est disponible, et un repli honnête sinon.

## Décision

Un seul port `StreamingLLMProvider` (`name="local"`) choisit, à l’exécution :

1. **HTTP OpenAI-compatible** (`PI_LLM_BASE_URL`) — vLLM ou `llama-server`, typiquement GPU.
2. **GGUF in-process** (`PI_LLM_MODEL_PATH` + extra `llm`) — `n_gpu_layers=-1` si le binaire CUDA le permet, sinon CPU.
3. **Gabarits** — SAFE_FALLBACK de qualité conversationnelle minimale, jamais présenté comme un modèle « en ligne ».

`PI_FAST_MODEL` / `PI_STANDARD_MODEL` nomment le modèle côté serveur HTTP. `PI_DEEP_REASONING_MODEL` reste le chemin externe (ADR-007). **Pas de Triton** (règle maître §10) : un seul modèle de dialogue local à la fois, pas de mutualisation GPU multi-framework.

Les cibles TTFT / tour normal sont des **objectifs d’ingénierie**. Elles sont mesurées (`scripts/benchmark_llm_ttft.py`, événements `AI_QUALITY`) et **non promises** sur CPU partagé.

## Conséquences

- Positif : même orchestrateur pour GPU, CPU et repli ; pytest sans poids ni GPU.
- Positif : les données GREEN restent locales tant que le chemin DEEP n’est pas consenti.
- Négatif : deux backends locaux à tester (HTTP + GGUF) ; vLLM n’est pas natif Windows.
- Invariant : ORANGE/RED n’atteignent jamais ce provider (déjà garanti par `compose_reply` / orchestrateur).
