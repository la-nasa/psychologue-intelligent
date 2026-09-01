"""Normalisation « durcie » du texte pour l'appariement de termes de crise
(master prompt §29, §46 robustesse).

Objectif : réduire l'obfuscation typographique simple (leetspeak, espacement
caractère par caractère, allongements, accents, caractères invisibles) qui
faisait passer une formulation de crise évidente en GREEN (voir
`tests/ai_redteam/test_crisis_robustness.py`).

Ce n'est PAS un anti-obfuscation complet : la variation phonétique reste un
écart, couvert par le modèle de risque lexical (`ai/providers/lexicon_risk.py`),
pas par ces règles. La chaîne produite ne sert qu'à l'appariement, jamais à
l'affichage.
"""
from __future__ import annotations

import re
import unicodedata

# Substitutions leetspeak les plus courantes. `1 -> i` (et non `l`) parce que
# les termes de crise visés (« su1c1de », « pl4n ») utilisent `1` pour `i`.
_LEET = str.maketrans({"4": "a", "@": "a", "3": "e", "1": "i", "!": "i", "0": "o", "5": "s", "$": "s", "7": "t", "|": "l"})
_ZERO_WIDTH = re.compile(r"[​-‏‪-‮⁠﻿]")
_SPACED_LETTERS = re.compile(r"(?<![^\W\d_])([^\W\d_](?:\s[^\W\d_]){3,})(?![^\W\d_])")
_ELONGATION = re.compile(r"(.)\1{2,}")
_MULTISPACE = re.compile(r"\s+")

MAX_CHARS = 8_000


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def harden(text: str) -> str:
    if not text or len(text) > MAX_CHARS:
        raise ValueError("invalid message")
    lowered = strip_accents(text.casefold())
    lowered = _ZERO_WIDTH.sub("", lowered)
    lowered = lowered.translate(_LEET)
    # "s u i c i d e" -> "suicide" (une lettre suivie d'au moins 3 " lettre")
    lowered = _SPACED_LETTERS.sub(lambda m: m.group(1).replace(" ", ""), lowered)
    # "suiciiiide" -> "suicide"
    lowered = _ELONGATION.sub(r"\1", lowered)
    return _MULTISPACE.sub(" ", lowered).strip()
