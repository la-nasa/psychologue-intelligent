"""Worker périodique hors chemin critique (master prompt §7, §31, §137).

Une boucle qui, à intervalle régulier, sur une `system_session` :
- `sla_sweep` : auto-escalade des alertes dont le SLA est dépassé,
- `retry_pending_notifications` : reprise des notifications `FAILED` sur backoff,
- `send_due_reminders` : rappels d'auto-évaluation échus.

Ces trois fonctions sont déjà idempotentes et testées unitairement (Phase 8/9).
Ce module ne fait que les cadencer. Lancement : `python -m app.workers.scheduler`.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

from app.application.alerting import sla_sweep
from app.application.notifications import CompositeNotificationProvider, retry_pending_notifications
from app.application.reminders import send_due_reminders
from app.core.db import system_session
from app.core.logging import configure_logging, get_logger

LOGGER = logging.getLogger("pi.worker")
_INTERVAL_SECONDS = 60


async def run_once() -> dict[str, int]:
    provider = CompositeNotificationProvider()
    async with system_session() as session:
        escalated = await sla_sweep(session)
        retried = await retry_pending_notifications(session, provider=provider, request_id="worker")
        reminded = await send_due_reminders(session)
    result = {"sla_escalated": len(escalated), "notifications_retried": len(retried), "reminders_sent": len(reminded)}
    if any(result.values()):
        get_logger("pi.worker").info("worker_tick", **result)
    return result


async def _loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await run_once()
        except Exception:
            LOGGER.exception("worker tick failed; continuing")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=_INTERVAL_SECONDS)


def main() -> None:
    configure_logging(json_output=True)
    stop = asyncio.Event()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    log = get_logger("pi.worker")
    log.info("worker_started", interval_seconds=_INTERVAL_SECONDS)
    try:
        loop.run_until_complete(_loop(stop))
    finally:
        log.info("worker_stopped")
        loop.close()


if __name__ == "__main__":
    main()
