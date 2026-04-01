"""Built-in job handlers that ship with staffNinja.

Add new ``@register("job_type")`` handlers here (or in separate modules
that are imported from ``jobs/__init__.py``).
"""

from __future__ import annotations

import logging
from typing import Any

from jobs.handlers import register

logger = logging.getLogger(__name__)


@register("ping")
async def handle_ping(payload: dict[str, Any]) -> dict[str, Any]:
    """Trivial health-check job.  Returns the payload back as the result."""
    logger.info("Ping job executed with payload: %s", payload)
    return {"pong": True, **payload}


@register("log_message")
async def handle_log_message(payload: dict[str, Any]) -> dict[str, Any]:
    """Write a message to the application log — useful for scheduled notices."""
    message = payload.get("message", "(no message)")
    level = payload.get("level", "INFO").upper()
    log_fn = getattr(logger, level.lower(), logger.info)
    log_fn("Scheduled log message: %s", message)
    return {"logged": True}
