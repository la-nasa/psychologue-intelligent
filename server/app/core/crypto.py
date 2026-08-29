from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import get_settings

# Chiffrement applicatif par champ (data-model-v2 §1) pour les valeurs sensibles :
# mfa_secret, about_me, réponses PHQ-9, contenu de message.
#
# LIMITE ASSUMÉE (Phase 2) : la clé dérive de PI_JWT_SIGNING_KEY. En production,
# une clé dédiée gérée par un KMS/gestionnaire de secrets, avec rotation, est
# requise (§95, production-readiness). Cette dérivation est un point de départ
# fonctionnel, pas la cible.


def _fernet() -> Fernet:
    key_material = get_settings().jwt_signing_key.encode("utf-8")
    derived = hashlib.sha256(b"pi-field-encryption-v1:" + key_material).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt(plaintext: str | None) -> str | None:
    if plaintext is None:
        return None
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str | None) -> str | None:
    if ciphertext is None:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except Exception:
        # InvalidToken, base64 malformé, ascii invalide : toute défaillance de
        # déchiffrement est traitée pareil — jamais un détail interne exposé.
        raise ValueError("field decryption failed") from None
