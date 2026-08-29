from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

# Champs qui ne doivent JAMAIS apparaître dans un log applicatif
# (threat-model-v2, hérité de v1 TH-09). Le filtre est une défense en profondeur :
# le code ne doit de toute façon pas les passer au logger.
_FORBIDDEN_KEYS = {
    "password",
    "password_hash",
    "token",
    "token_hash",
    "access_token",
    "mfa_secret",
    "authorization",
    "content",           # contenu de message clinique
    "message_content",
    "about_me",
    "answers",           # réponses PHQ-9
    "api_key",
    "signing_key",
}


def _redact(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key in list(event_dict.keys()):
        if key.lower() in _FORBIDDEN_KEYS:
            event_dict[key] = "[redacted]"
    return event_dict


def configure_logging(*, json_output: bool = True, level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _redact,
    ]
    processors.append(
        structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "pi") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
