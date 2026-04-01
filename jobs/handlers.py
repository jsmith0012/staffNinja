"""Registry of job-type handlers.

Register async callables keyed by job_type string.  The worker looks up
handlers here when it claims a job.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

# handler signature: async def handler(payload: dict) -> dict | None
HandlerFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]

_registry: dict[str, HandlerFn] = {}


def register(job_type: str):
    """Decorator to register a handler for *job_type*."""
    def decorator(fn: HandlerFn) -> HandlerFn:
        _registry[job_type] = fn
        logger.info("Registered job handler: %s -> %s", job_type, fn.__qualname__)
        return fn
    return decorator


def get_handler(job_type: str) -> HandlerFn | None:
    return _registry.get(job_type)


def registered_types() -> list[str]:
    return list(_registry.keys())
