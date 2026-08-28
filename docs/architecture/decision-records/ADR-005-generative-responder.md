# ADR-005 — Répondeur génératif auto-hébergé pour les réponses GREEN

Date : 2026-08-28
Statut : Accepté, en écart explicite avec ADR-003

## Contexte

Le répondeur non génératif (`TemplatedSupportiveResponder`, voir README et rapports de phase antérieurs) a été un choix délibéré de l'utilisateur : aucune donnée patient ne quitte le système, aucune clé API, aucun coût. En usage réel, ce choix produit des conversations perçues comme scriptées et non personnalisées — retour direct de l'utilisateur. Trois options ont été présentées (API Claude, modèle auto-hébergé, gabarits enrichis) ; l'utilisateur a choisi le modèle auto-hébergé, en connaissance de cause de son coût d'ingénierie.

## Décision

Un modèle génératif auto-hébergé répond aux messages classés GREEN, via `llama-cpp-python` (CPU uniquement). Initialement `Qwen2.5-3B-Instruct` (~2,1 Go), **remplacé par `Qwen2.5-1.5B-Instruct`** (licence Apache-2.0, quantifié GGUF `q4_k_m`, ~1,1 Go) après mesure en conditions réelles d'une latence de 30 s à plus d'une minute par réponse jugée trop lente — un modèle moitié plus petit vise à réduire ce temps de génération, au prix réel (assumé) d'une capacité un peu moindre pour des réponses courtes de soutien. C'est un écart **explicite et documenté** à ADR-003 (« zéro dépendance runtime ») : `llama-cpp-python` est une dépendance runtime réelle, isolée dans le groupe optionnel `llm` de `pyproject.toml` et importée uniquement à l'intérieur de `backend/app/local_llm.py`, jamais au niveau module — le reste de l'application continue de fonctionner et de se tester sans cette dépendance installée (`PI_RESPONDER_MODE=templated`, valeur par défaut).

L'invariant d'ADR-004 est structurellement inchangé : `responder.py::compose_reply` route ORANGE/RED vers les gabarits fixes avant même de considérer le LLM — celui-ci n'est jamais appelé pour ces niveaux, quel que soit son état ou son contenu généré. Un test de régression (`tests/test_generative_responder.py::test_orange_and_red_messages_never_reach_the_generative_engine`) vérifie cette garantie avec un moteur espion.

La personnalisation (`backend/app/personalization.py::build_context`) assemble, en lecture seule et de façon best-effort (jamais bloquant, jamais une exception) : le prénom déclaré (`profiles.display_name`), un texte libre facultatif que le patient choisit de partager sur lui-même (`profiles.about_me`, éditable via `GET`/`POST /api/v1/profile` — voir Section 3), une bande de sévérité PHQ-9 qualitative (jamais le score numérique brut — voir Sécurité ci-dessous), et l'historique récent de la conversation. Ce contexte n'est utilisé que pour la réponse GREEN, jamais pour la classification du risque elle-même, et n'alimente jamais le pipeline d'apprentissage continu (`learning.py`), qui reste régi par le consentement `LEARNING` séparé et n'échantillonne que du contenu de message, pas des champs de profil — une décision de périmètre délibérée, pas un oubli.

Le poids du modèle est téléchargé une fois par `scripts/bootstrap_llm_model.py` (idempotent, vérifie la taille du fichier avant de l'accepter) vers le volume persistant, jamais commité dans le dépôt Git.

## Sécurité et vie privée

- **TH-04 du threat model redevient pleinement pertinent** (voir sa mise à jour) : un patient peut tenter une injection de prompt, y compris via `about_me` (texte entièrement contrôlé par le patient, injecté dans le message système lui-même, pas seulement dans un tour utilisateur). `local_llm.py::_build_messages` l'encadre explicitement comme une information, jamais comme une instruction, y compris si son contenu y ressemble. Le rayon d'impact reste borné par construction dans tous les cas : au pire, une réponse GREEN inappropriée ou peu utile — jamais un contournement de la classification de crise, qui a lieu avant et indépendamment de tout appel au LLM.
- Le score PHQ-9 brut n'est jamais injecté dans le prompt : seule une bande qualitative (« légère », « modérée », etc. — les seuils cliniques publiés de Kroenke, Spitzer & Williams 2001) l'est, avec instruction explicite de ne jamais la mentionner explicitement au patient. Réduit le risque qu'un score sensible fuite mot pour mot dans une réponse générée.
- Aucune donnée ne quitte le système : contrairement à l'option API externe, le contenu des messages ne transite jamais vers un tiers.
- `llama.cpp` n'est pas sûr pour des appels concurrents sur un même contexte : `LocalGenerativeResponder` sérialise tout accès via un verrou (`threading.Lock`), vérifié par un test de concurrence réel (deux threads, pas seulement une inspection du code).

## Conséquences

- Écart assumé et documenté à ADR-003 : la première dépendance runtime réelle du projet. Limité au strict nécessaire (un seul module l'importe, en différé).
- Limite assumée, mesurée en conditions réelles sur le déploiement Railway (pas estimée) : inférence CPU uniquement, **30 secondes à plus d'une minute par réponse**, sur un hébergement à CPU partagé où la variance elle-même est significative — deux essais de réglage du nombre de threads (`n_threads`) ont chacun *dégradé* la latence par rapport au réglage par défaut de `llama-cpp-python`, contre-intuitivement (`os.cpu_count()` dans un conteneur reflète souvent le nombre de cœurs de l'hôte, pas la part réellement allouée, d'où une sursouscription qui ralentit plus qu'elle n'accélère). `PI_LLM_THREADS` reste disponible comme échappatoire si une mesure propre sur un hébergement dédié le justifie un jour. Un modèle plus petit ou un hébergement dédié/GPU serait la vraie réponse si cette latence bloque un usage réel — pas un réglage de threads sur un hôte partagé et bruité.
- Limite assumée : les appels concurrents sont sérialisés (un seul verrou global) — un pic d'usage simultané dégradera la latence avant de dégrader la qualité, par choix explicite (sûr avant rapide).
- Limite assumée : aucune évaluation qualitative formelle de la fluidité/pertinence des réponses générées n'a été menée au-delà de tests structurels (routage, personnalisation, repli) — une revue humaine réelle des réponses produites reste à faire avant tout pilote.
- `production-readiness.md` et `docs/security/threat-model.md` (TH-04) sont mis à jour en conséquence.
