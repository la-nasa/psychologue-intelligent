"""RabbitMQ — publication d'événements de domaine (master prompt §7, §79).

Best-effort et **jamais bloquant** pour le chemin critique : si le broker est
injoignable, la publication est journalisée et abandonnée — l'alerte est déjà
persistée et notifiée de façon synchrone (l'événement sert l'analytics et un
futur traitement piloté par événements, pas la sûreté).
"""
from __future__ import annotations

import json
import logging

import aio_pika

from app.core.config import get_settings

LOGGER = logging.getLogger("pi.mq")
EXCHANGE = "pi.events"

_connection: aio_pika.abc.AbstractRobustConnection | None = None


async def _get_connection() -> aio_pika.abc.AbstractRobustConnection:
    global _connection
    if _connection is None or _connection.is_closed:
        _connection = await aio_pika.connect_robust(get_settings().rabbitmq_url, timeout=5)
    return _connection


async def close() -> None:
    global _connection
    if _connection is not None and not _connection.is_closed:
        await _connection.close()
    _connection = None


async def publish_event(routing_key: str, body: dict) -> bool:
    """Publie sur l'échange `pi.events` (topic, durable). Renvoie False si le
    broker est injoignable ou désactivé — l'appelant ne doit jamais échouer."""
    if not get_settings().mq_enabled:
        return False
    try:
        connection = await _get_connection()
        channel = await connection.channel()
        exchange = await channel.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
        await exchange.publish(
            aio_pika.Message(body=json.dumps(body).encode("utf-8"), content_type="application/json"),
            routing_key=routing_key,
        )
        await channel.close()
        return True
    except Exception:
        LOGGER.warning("event publish failed routing_key=%s (broker unreachable?)", routing_key)
        return False


async def health_check() -> bool:
    try:
        connection = await _get_connection()
        return not connection.is_closed
    except Exception:
        return False
