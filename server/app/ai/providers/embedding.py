"""Modèle d'embedding — port + implémentation locale déterministe (Phase 5).

`HashingEmbeddingModel` : pas un vrai encodeur sémantique (sentence-transformers
serait une dépendance lourde + un téléchargement de modèle). C'est un sac de
tri-grammes de caractères projeté et L2-normalisé : deux textes qui partagent du
vocabulaire ont une similarité cosinus plus élevée — suffisant pour tester le
*pipeline* de récupération (pertinent remonte, hors-sujet ne remonte pas). Un
adaptateur `sentence-transformers` viendra en extra optionnel si besoin.
"""
from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from typing import Protocol

EMBEDDING_DIM = 256
_TOKEN = re.compile(r"[a-z0-9]+")


class EmbeddingModel(Protocol):
    version: str
    dim: int

    def embed(self, text: str) -> list[float]: ...


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


class HashingEmbeddingModel:
    version = "hashing-embed-dev-1"
    dim = EMBEDDING_DIM

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * EMBEDDING_DIM
        normalized = _normalize(text or "")
        tokens = _TOKEN.findall(normalized)
        features: list[str] = list(tokens)
        for token in tokens:
            padded = f"^{token}$"
            features.extend(padded[i : i + 3] for i in range(len(padded) - 2))
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % EMBEDDING_DIM
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[bucket] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            return vec
        return [v / norm for v in vec]
