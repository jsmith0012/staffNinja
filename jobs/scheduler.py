import asyncio
import logging

from jobs.worker import Worker

logger = logging.getLogger(__name__)


class Scheduler:
    """Manages the job-queue worker and periodic housekeeping tasks."""

    def __init__(self, poll_interval: float = 5.0):
        self._worker = Worker(poll_interval=poll_interval)
        self._periodic: list[tuple] = []
        self._periodic_tasks: list[asyncio.Task] = []

    # ── periodic callbacks ────────────────────────────────────────────────

    def add_periodic(self, coro_fn, interval_seconds: float):
        """Register an async callable to run every *interval_seconds*."""
        self._periodic.append((coro_fn, interval_seconds))

    # ── lifecycle ─────────────────────────────────────────────────────────

    async def start(self):
        """Start the job worker and all registered periodic tasks."""
        self._worker.start()
        for coro_fn, interval in self._periodic:
            task = asyncio.create_task(self._run_periodic(coro_fn, interval))
            self._periodic_tasks.append(task)
        logger.info("Scheduler started (%d periodic tasks)", len(self._periodic))

    async def stop(self):
        """Gracefully shut down the worker and periodic tasks."""
        await self._worker.stop()
        for task in self._periodic_tasks:
            task.cancel()
        self._periodic_tasks.clear()
        logger.info("Scheduler stopped")

    @property
    def worker(self) -> Worker:
        return self._worker

    # ── internals ─────────────────────────────────────────────────────────

    @staticmethod
    async def _run_periodic(coro_fn, interval: float):
        while True:
            try:
                await coro_fn()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Periodic task %s failed", coro_fn.__qualname__)
            await asyncio.sleep(interval)
