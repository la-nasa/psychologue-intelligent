# PHASE REPORT

Phase: 8a — Cœur conversationnel (préalable à l'apprentissage continu)
Date: 2026-08-27
Objectif: Construire le domaine Conversation (Section 3) et l'activer avec un répondeur non génératif, honnête et sans dépendance externe, afin que de vraies données de conversation existent avant de construire le pipeline d'apprentissage de la Phase 8 proprement dite.

## 0. Pourquoi cette phase existe

La Phase 8 (apprentissage continu) du prompt maître opère sur des conversations produites en production. Aucune n'existait : le chat était désactivé depuis la Phase 3 en attendant le moteur de crise (livré en Phase 5–6). Après discussion explicite avec l'utilisateur, le choix retenu pour le contenu conversationnel a été un répondeur non génératif de développement (aucune donnée patient n'est envoyée à un tiers, aucun coût, aucune clé API), conforme à la Section 7 : le LLM (ou son substitut) ne décide jamais du cadrage d'une crise.

## 1. Travaux réalisés

- Migration `007_conversations` : tables `conversations` et `messages` (auteur PATIENT/ASSISTANT, numéro de séquence unique par conversation, référence à l'événement de crise déclenché).
- `backend/app/ai.py` : `TemplatedSupportiveResponder`, un `LLMProvider` non génératif qui choisit parmi un petit ensemble d'accusés de réception ; explicitement documenté comme non conversationnel et jamais utilisé pour un message ORANGE/RED.
- `backend/app/policy.py` : `ResponseTemplates` + `load_response_templates`, chargées et validées comme la politique de crise (ADR-002/ADR-004), avec la même garde d'approbation par environnement. Les textes de réponse liés à la crise sont ainsi une donnée versionnée, pas une chaîne codée en dur.
- `backend/app/responder.py` : `compose_reply` — pour ORANGE/RED, la réponse vient uniquement des modèles versionnés (jamais du LLM) ; seul GREEN passe par le répondeur. C'est l'implémentation concrète de la Section 7 : le LLM ne décide jamais d'une situation de crise.
- `backend/app/conversation.py` : démarrage idempotent d'une conversation active (exige un consentement de soin actif), envoi de message (persistance patient → pipeline de crise déjà construit en Phase 5–6 → persistance de la réponse), historique — tout scopé par propriétaire, refus par défaut.
- `pipeline.py` mis à jour : `input_reference` stocke désormais le véritable identifiant du message plutôt qu'une empreinte SHA-256 (la table `messages` existe enfin), ce qui ferme aussi la limite de déduplication documentée en Phase 5–6 (TM-09) : rejouer le même message ne peut plus dupliquer la chaîne alerte/notification.
- Frontend patient : la vue « Conversation bientôt disponible » est remplacée par une vraie interface de discussion, avec un avertissement explicite et permanent — *« Ceci n'est pas une intelligence artificielle conversationnelle »* — conforme à la Section 52.
- **Bug réel trouvé par vérification manuelle dans le navigateur, pas par les tests automatisés** (Section 8) : corrigé.

## 2. Fichiers créés

- `backend/app/conversation.py`, `backend/app/responder.py`
- `config/policies/response-templates-v1.json`
- `tests/test_conversation.py`
- `docs/reports/phase-8a-conversational-core.md`

## 3. Fichiers modifiés

- `backend/app/db.py` (migration 007), `backend/app/config.py` (chemin des modèles de réponse)
- `backend/app/ai.py` (`TemplatedSupportiveResponder`, correction de calibration — voir Section 8)
- `backend/app/policy.py` (`ResponseTemplates`)
- `backend/app/pipeline.py` (référence réelle au message, `crisis_event_id` exposé)
- `backend/app/http.py` (routes `/api/v1/conversations`, `/api/v1/conversations/{id}/messages`)
- `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`
- `tests/test_foundation.py` (mise à jour de l'assertion affectée par la correction)

## 4. Architecture impactée

Le domaine Conversation existe et s'appuie sur le pipeline de crise sans le dupliquer : `conversation.send_message` appelle `pipeline.handle_incoming_message`, qui appelle `crisis.CrisisDetector`. Le contenu des messages est stocké en clair dans SQLite de développement, cohérent avec la décision déjà prise pour les réponses PHQ-9 (Phase 4) : le chiffrement au repos reste une dette pré-pilote assumée et documentée, pas un oubli silencieux.

## 5. Fonctionnalités terminées

- Conversation démarrée automatiquement (une par patient, exige un consentement de soin actif), messages envoyés et historisés.
- Réponse dont le contenu est entièrement déterminé par le niveau de crise détecté : jamais le LLM pour ORANGE/RED.
- Interface patient honnête sur la nature non-IA de la conversation.
- Vérification fonctionnelle complète dans un navigateur réel, y compris la détection du bug de la Section 8.

## 6. Tests exécutés

- `ruff check`, `mypy`, `bandit`, `pip-audit`, `python scripts/scan_secrets.py`, `coverage run` + `coverage report`
- `python -m unittest discover -s tests -v`
- Vérification manuelle dans le navigateur : inscription, connexion, onboarding, ouverture de la conversation, envoi d'un message calme, d'un message ambigu et d'un message à haut risque, relecture de l'historique après rechargement de page, vérification directe en base que les alertes ORANGE et RED ont bien été créées.

## 7. Résultats des tests

- 41 tests automatisés, tous verts (7 nouveaux). Aucune régression.
- Couverture : 91 % sur `backend/app`, au-dessus du seuil CI de 85 %.
- Aucun signalement `ruff`, `mypy`, `bandit`, scanner de secrets.
- Vérification navigateur : les trois niveaux (GREEN/ORANGE/RED) produisent la réponse attendue ; aucune erreur console ; les lignes `alerts` et `messages` correspondantes existent bien en base après coup.

## 8. Bugs détectés

**Bug de calibration critique, trouvé uniquement par la vérification manuelle dans le navigateur, pas par la suite automatisée existante.** `KeywordRiskModel` (l'adaptateur de risque de développement) renvoyait une confiance de `0.50` lorsqu'aucun terme connu n'était trouvé dans un message. Le seuil `orange_confidence_floor` de la politique de crise est `0.65`. Résultat : *tout* message ordinaire, y compris un message parfaitement calme, tombait sous le seuil de confiance et déclenchait systématiquement le repli prudent vers ORANGE — pas seulement les cas réellement ambigus. En pratique, le tout premier message envoyé dans la conversation réelle (« Ma journée a été plutôt calme aujourd'hui. ») a reçu le message-type de sécurité ORANGE au lieu d'un accusé de réception normal.

Les tests existants ne l'ont pas détecté parce qu'un des tests (`test_risk_engine_is_independent_and_conservative`) asserait déjà `ORANGE` pour un message calme, comme si c'était le comportement voulu — ce qui semblait raisonnable en Phase 5–6 (« prudence par défaut ») mais s'est révélé être, une fois relié à un vrai produit, un défaut qui rendrait la conversation inutilisable : chaque message aurait déclenché une notification et un ton de crise.

## 9. Bugs corrigés

- `KeywordRiskModel.predict()` : la confiance par défaut (aucun terme trouvé) passe de `0.50` à `0.85`. Justification : ne trouver aucun terme connu est, pour un modèle à base de règles, un résultat plutôt sûr, pas une estimation incertaine ; la confiance intermédiaire (`0.60`) reste réservée aux termes de préoccupation réellement ambigus, qui continuent de déclencher ORANGE.
- `tests/test_foundation.py` : l'assertion pour un message calme passe de `ORANGE` à `GREEN`, avec un commentaire expliquant pourquoi l'ancienne attente était elle-même le bug.
- `tests/test_conversation.py` : le test du message GREEN vérifie désormais que la réponse est *exactement* l'un des accusés de réception configurés, et non plus seulement qu'elle ne contient pas la phrase propre au message ROUGE — une assertion plus faible qui n'aurait pas détecté ce bug si elle avait existé avant.

## 10. Vulnérabilités détectées

- Aucune nouvelle. Le bug de la Section 8 est un défaut de calibration fonctionnelle, pas une faille de sécurité : aucune donnée n'a fuité, aucun contrôle d'accès n'a été contourné.

## 11. Vulnérabilités corrigées

- Sans objet au-delà de la Section 9.

## 12. Dette technique

- Contenu des messages stocké en clair en SQLite de développement (cohérent avec la dette déjà documentée pour PHQ-9 en Phase 4).
- Le répondeur GREEN reste un choix parmi trois phrases fixes : suffisant pour prouver le pipeline, pas une expérience conversationnelle riche. Toute amélioration doit rester derrière le port `LLMProvider` existant.
- Une seule conversation active par patient (pas de historique de conversations multiples ni de reprise d'une conversation clôturée) : suffisant pour ce périmètre, à revoir si le besoin apparaît.
- Ce bug de calibration soulève une question plus large : d'autres seuils de la politique de développement n'ont peut-être jamais été exercés avec un vrai flux utilisateur. Une revue systématique des seuils par simulation de messages variés est recommandée avant tout pilote (Section 17 « Full E2E » du prompt maître, Phase 13).

## 13. Décisions techniques

- `input_reference` des `risk_assessments` pointe maintenant vers l'identifiant réel du message plutôt qu'une empreinte : plus traçable, et l'identifiant sert aussi de clé d'idempotence pour la déduplication d'alerte, fermant une dette Phase 5–6.
- Les textes de réponse liés à la crise sont un fichier de politique versionné et approuvable, pas une chaîne dans le code : cohérent avec ADR-002/ADR-004, et directement conforme à l'exigence du design system (« les communications de crise doivent être rédigées et validées avec les cliniciens »).

## 14. Risques restants

- Ce bug de calibration, une fois découvert, invite à la prudence sur tout seuil de développement non encore exercé par un usage réel : la Phase 13 (E2E complet) devra couvrir bien plus de scénarios de messages que ceux testés ici.
- Les textes de sécurité ORANGE/RED restent des brouillons non approuvés cliniquement (`approved_by`/`approved_at` sont `null`) : ils ne peuvent pas être utilisés hors développement sans validation, ce que le chargeur applique déjà.

## 15. Métriques

- 1 migration ajoutée (007), 2 nouvelles tables, 2 nouvelles routes HTTP.
- 7 nouveaux tests (41 au total), 1 bug de calibration critique trouvé et corrigé grâce à la vérification manuelle.
- 0 nouvelle dépendance externe, 0 donnée patient envoyée à un tiers.

## 16. Critères de sortie

- [x] Domaine Conversation complet et testé.
- [x] Le LLM (ou son substitut) ne décide jamais du cadrage d'une crise.
- [x] Interface patient honnête sur la nature non-IA de la conversation.
- [x] Vérifié fonctionnellement dans un navigateur réel, bug trouvé et corrigé.
- [ ] Chiffrement au repos du contenu des messages (dette pré-pilote assumée).

## 17. Conclusion

Le préalable à la Phase 8 est en place : de vraies conversations peuvent maintenant être produites, avec un cadrage de crise qui ne dépend jamais du répondeur. La vérification manuelle a trouvé un bug qu'aucun test automatisé n'avait détecté, rappelant qu'un test qui vérifie un comportement spécifique peut masquer un défaut systémique si personne ne questionne si ce comportement est réellement souhaitable. La Phase 8 proprement dite (échantillonnage, anonymisation, revue humaine, versioning de dataset, registre de modèles) et l'entraînement d'un classifieur d'émotions réel (décision utilisateur explicite) peuvent maintenant commencer sur des données réelles plutôt que sur du vide.

STATUS: PASS WITH WARNINGS
