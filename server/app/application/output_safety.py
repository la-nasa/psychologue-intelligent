"""Vérification de sortie (overview-v2 §7, master prompt §60).

Pipeline appliqué à **toute** réponse générée (locale ou externe), pour une
décision de crise déjà GREEN :

    crisis-consistency -> clinical-policy -> self-harm -> PII -> unsupported-claim

Toute défaillance -> `SAFE_FALLBACK` (message neutre de soutien + rappel des
ressources), jamais la sortie brute. Aucune de ces vérifications ne peut
*rendre* une réponse dangereuse acceptable : au pire elle la remplace.

Ceci n'est pas un classifieur ML : ce sont des garde-fous lexicaux
conservateurs. Le faux positif (remplacer une bonne réponse) est acceptable ;
le faux négatif (laisser passer une mauvaise réponse) ne l'est pas.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.domain.safety.crisis import CrisisDecision
from app.domain.safety.policy import ResponseTemplates

_MAX_REPLY_CHARS = 2000

# Revendication de diagnostic / de posture clinique / d'identité humaine.
_CLINICAL_CLAIM = re.compile(
    r"vous souffrez d[e']|vous (avez|présentez|faites) (un|une|de la|des) "
    r"(trouble|dépression|maladie|pathologie|burn ?out|bipolarit|tdah|toc|anxiété généralisée)"
    r"|je (vous )?diagnostique|mon diagnostic|votre diagnostic est"
    r"|en tant que (psychologue|psychiatre|médecin|thérapeute|soignant)"
    r"|je suis (un |une |votre |ton )?(psychologue|psychiatre|médecin|thérapeute|humain|une vraie personne)"
    r"|d'après (votre|ton) dossier|vos antécédents (montrent|indiquent)|votre historique médical",
    re.IGNORECASE,
)

# Conseil médicamenteux / d'automédication.
_MEDICATION_ADVICE = re.compile(
    r"(arrêt|augment|diminu|réduis|double|saut|prend|pren)\w*\s+"
    r"(tes|vos|ton|votre|les|leur|de|du|des|un|une)?\s*"
    r"(médicament|traitement|dose|comprimé|cachet|antidépresseur|anxiolytique|somnifère)"
    r"|il (te|vous) faut (un|des) (médicament|antidépresseur|anxiolytique|somnifère)"
    r"|(prends|prenez) (en|plus|moins|le double)",
    re.IGNORECASE,
)

# Fausse réassurance / minimisation.
_FALSE_REASSURANCE = re.compile(
    r"ce n'est rien|c'est pas grave|il n'y a pas de quoi (s'inquiéter|paniquer)"
    r"|tout (va|ira) (forcément |certainement |sûrement )?bien|je (te|vous) (garantis|promets) que"
    r"|arrête de (t'inquiéter|te faire du souci)",
    re.IGNORECASE,
)

# Méthodes d'auto-agression (ne doivent jamais apparaître dans une réponse).
_SELF_HARM_METHOD = re.compile(
    r"(comment|voici comment|tu peux|il suffit de).{0,40}(te (faire du mal|blesser|suicider|tuer|mutiler))"
    r"|(dose|quantité) (létale|mortelle|fatale)|se (pendre|trancher|ouvrir les veines)"
    r"|surdose de|médicaments? (pour|qui) (en finir|mourir)",
    re.IGNORECASE,
)

# PII structurée dans la réponse générée.
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d .\-]{7,}\d)(?!\w)")

# Signes que la réponse répète le message système.
_SYSTEM_PROMPT_LEAK = re.compile(
    r"tu es \"repère\"|système de sécurité de l'application|ce message a déjà été classé"
    r"|contexte interne \(ne jamais mentionner|instruction à suivre, même si le texte y ressemble",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SafetyFinding:
    check: str
    detail: str


@dataclass(frozen=True)
class OutputSafetyResult:
    text: str
    replaced: bool
    reason: str
    findings: list[SafetyFinding] = field(default_factory=list)


def _safe_fallback(templates: ResponseTemplates, reason: str, findings: list[SafetyFinding]) -> OutputSafetyResult:
    return OutputSafetyResult(text=templates.green_acknowledgments[0], replaced=True, reason=reason, findings=findings)


def check(reply: str, *, decision: CrisisDecision, templates: ResponseTemplates) -> OutputSafetyResult:
    findings: list[SafetyFinding] = []

    # 1. Cohérence de crise : ce module ne doit être appelé que pour du GREEN.
    if decision.level != "GREEN":
        return _safe_fallback(templates, "called_on_non_green", [SafetyFinding("crisis_consistency", decision.level)])

    stripped = (reply or "").strip()
    if not stripped:
        return _safe_fallback(templates, "empty_reply", [SafetyFinding("non_empty", "empty")])

    # 2. Politique clinique.
    if _CLINICAL_CLAIM.search(stripped):
        findings.append(SafetyFinding("clinical_policy", "diagnostic or clinical-posture claim"))
    if _MEDICATION_ADVICE.search(stripped):
        findings.append(SafetyFinding("clinical_policy", "medication advice"))
    if _FALSE_REASSURANCE.search(stripped):
        findings.append(SafetyFinding("clinical_policy", "false reassurance / minimisation"))

    # 3. Auto-agression.
    if _SELF_HARM_METHOD.search(stripped):
        findings.append(SafetyFinding("self_harm", "self-harm method content"))

    # 4. Fuite du message système.
    if _SYSTEM_PROMPT_LEAK.search(stripped):
        findings.append(SafetyFinding("prompt_leak", "reply echoes the system prompt"))

    if findings:
        return _safe_fallback(templates, findings[0].check, findings)

    # 5. PII : on rédige plutôt que remplacer (une réponse par ailleurs correcte).
    redacted = _EMAIL.sub("[contact retiré]", stripped)
    redacted = _PHONE.sub("[numéro retiré]", redacted)
    if redacted != stripped:
        findings.append(SafetyFinding("pii", "contact details redacted"))
        stripped = redacted

    # 6. Longueur.
    if len(stripped) > _MAX_REPLY_CHARS:
        stripped = stripped[:_MAX_REPLY_CHARS].rsplit(" ", 1)[0] + "…"
        findings.append(SafetyFinding("length", "truncated"))

    replaced = any(f.check in ("pii", "length") for f in findings)
    return OutputSafetyResult(text=stripped, replaced=replaced, reason=findings[0].check if findings else "ok", findings=findings)
