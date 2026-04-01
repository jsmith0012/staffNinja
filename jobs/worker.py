"""Async job-queue worker.

Polls ``staffninja_jobs`` for pending work, dispatches to registered
handlers, and marks jobs completed or failed (with retry-to-pending).

Sprinkles anime waiting quotes into the logs because every convention
deserves a little fun between panels.
"""

from __future__ import annotations

import asyncio
import logging
import traceback

from jobs import queue
from jobs.handlers import get_handler
from jobs.anime_quotes import random_wait_quote

logger = logging.getLogger(__name__)

# How often the worker checks for new jobs (seconds).
DEFAULT_POLL_INTERVAL: float = 5.0


class Worker:
    """Single-threaded async worker that processes jobs one at a time."""

    def __init__(self, poll_interval: float = DEFAULT_POLL_INTERVAL):
        self._poll_interval = poll_interval
        self._running = False
        self._task: asyncio.Task | None = None

    # ── lifecycle ─────────────────────────────────────────────────────────

    def start(self) -> asyncio.Task:
        """Create and return the background task."""
        if self._task is not None and not self._task.done():
            return self._task
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Job worker started (poll_interval=%.1fs)", self._poll_interval)
        return self._task

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Job worker stopped")

    # ── main loop ─────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        idle_quotes_shown = 0
        while self._running:
            try:
                job = await queue.claim_next()
            except Exception:
                logger.exception("Error claiming next job")
                await asyncio.sleep(self._poll_interval)
                continue

            if job is None:
                # Nothing to do — log an anime quote every ~60 s of idle time for fun
                idle_quotes_shown += 1
                if idle_quotes_shown % int(60 / self._poll_interval) == 0:
                    q = random_wait_quote()
                    logger.debug(
                        "Queue idle — %s  [%s]", q["quote"], q["anime"]
                    )
                await asyncio.sleep(self._poll_interval)
                continue

            idle_quotes_shown = 0
            await self._execute(job)

    # ── execution ─────────────────────────────────────────────────────────

    async def _execute(self, job) -> None:
        handler = get_handler(job.job_type)
        if handler is None:
            msg = f"No handler registered for job_type={job.job_type!r}"
            logger.error(msg)
            await queue.mark_failed(job.id, msg)
            return

        anime = random_wait_quote()
        logger.info(
            "Processing job id=%s type=%s attempt=%s/%s — %s [%s]",
            job.id,
            job.job_type,
            job.attempt,
            job.max_retries,
            anime["quote"],
            anime["anime"],
        )

        try:
            result = await handler(job.payload)
            await queue.mark_completed(job.id, result)
        except Exception as exc:
            tb = traceback.format_exc()
            logger.exception("Job id=%s raised %s", job.id, exc)
            await queue.mark_failed(job.id, f"{exc}\n{tb}")
