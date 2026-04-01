"""Job queue — enqueue, claim, and update jobs via PostgreSQL."""

from __future__ import annotations

import json
import logging
from typing import Any

from db.connection import Database
from jobs.models import Job, JobStatus

logger = logging.getLogger(__name__)


async def enqueue(
    job_type: str,
    payload: dict[str, Any] | None = None,
    created_by: int | None = None,
    max_retries: int = 3,
) -> Job:
    """Insert a new job and return it."""
    rows = await Database.fetch(
        """
        INSERT INTO staffninja_jobs (job_type, payload, created_by, max_retries)
        VALUES ($1, $2::jsonb, $3, $4)
        RETURNING *
        """,
        job_type,
        json.dumps(payload or {}),
        created_by,
        max_retries,
    )
    job = Job.from_record(rows[0])
    logger.info("Enqueued job id=%s type=%s created_by=%s", job.id, job.job_type, created_by)
    return job


async def claim_next() -> Job | None:
    """Atomically claim the oldest pending job (SKIP LOCKED) and return it.

    Returns ``None`` when the queue is empty.
    """
    rows = await Database.fetch(
        """
        UPDATE staffninja_jobs
        SET    status     = 'running',
               started_at = NOW(),
               attempt    = attempt + 1
        WHERE  id = (
            SELECT id FROM staffninja_jobs
            WHERE  status = 'pending'
            ORDER  BY created_at
            LIMIT  1
            FOR UPDATE SKIP LOCKED
        )
        RETURNING *
        """
    )
    if not rows:
        return None
    return Job.from_record(rows[0])


async def mark_completed(job_id: int, result: dict[str, Any] | None = None) -> None:
    await Database.execute(
        """
        UPDATE staffninja_jobs
        SET    status       = 'completed',
               completed_at = NOW(),
               result       = $2::jsonb
        WHERE  id = $1
        """,
        job_id,
        json.dumps(result or {}),
    )
    logger.info("Job id=%s completed", job_id)


async def mark_failed(job_id: int, error: str) -> None:
    """Mark a job as failed.  If retries remain, reset it to pending."""
    rows = await Database.fetch(
        "SELECT attempt, max_retries FROM staffninja_jobs WHERE id = $1", job_id
    )
    if not rows:
        return

    attempt, max_retries = rows[0]["attempt"], rows[0]["max_retries"]

    if attempt < max_retries:
        await Database.execute(
            """
            UPDATE staffninja_jobs
            SET    status = 'pending', error = $2
            WHERE  id = $1
            """,
            job_id,
            error,
        )
        logger.warning(
            "Job id=%s failed (attempt %s/%s), re-queued: %s",
            job_id, attempt, max_retries, error,
        )
    else:
        await Database.execute(
            """
            UPDATE staffninja_jobs
            SET    status       = 'failed',
                   completed_at = NOW(),
                   error        = $2
            WHERE  id = $1
            """,
            job_id,
            error,
        )
        logger.error("Job id=%s permanently failed after %s attempts: %s", job_id, attempt, error)


async def get_job(job_id: int) -> Job | None:
    rows = await Database.fetch("SELECT * FROM staffninja_jobs WHERE id = $1", job_id)
    if not rows:
        return None
    return Job.from_record(rows[0])


async def pending_count() -> int:
    rows = await Database.fetch(
        "SELECT COUNT(*) AS cnt FROM staffninja_jobs WHERE status = 'pending'"
    )
    return int(rows[0]["cnt"]) if rows else 0


async def reap_stale_jobs(timeout_seconds: int = 600) -> int:
    """Reset jobs stuck in 'running' longer than *timeout_seconds* back to pending.

    Returns the number of reaped jobs.
    """
    rows = await Database.fetch(
        """
        UPDATE staffninja_jobs
        SET    status = 'pending',
               error  = 'reaped: exceeded stale timeout of ' || $1 || 's'
        WHERE  status = 'running'
          AND  started_at < NOW() - make_interval(secs => $1::double precision)
          AND  attempt < max_retries
        RETURNING id
        """,
        float(timeout_seconds),
    )
    reaped = len(rows)
    if reaped:
        logger.warning("Reaped %d stale running job(s)", reaped)

    # Permanently fail any that have exhausted retries
    await Database.execute(
        """
        UPDATE staffninja_jobs
        SET    status       = 'failed',
               completed_at = NOW(),
               error        = 'reaped: exceeded stale timeout and max retries'
        WHERE  status = 'running'
          AND  started_at < NOW() - make_interval(secs => $1::double precision)
          AND  attempt >= max_retries
        """,
        float(timeout_seconds),
    )
    return reaped


async def job_counts() -> dict[str, int]:
    """Return a {status: count} dict for all job statuses."""
    rows = await Database.fetch(
        "SELECT status, COUNT(*) AS cnt FROM staffninja_jobs GROUP BY status"
    )
    return {r["status"]: int(r["cnt"]) for r in rows}


async def recent_failed(limit: int = 5) -> list[Job]:
    """Return the most recent failed jobs."""
    rows = await Database.fetch(
        """
        SELECT * FROM staffninja_jobs
        WHERE  status = 'failed'
        ORDER  BY completed_at DESC NULLS LAST
        LIMIT  $1
        """,
        limit,
    )
    return [Job.from_record(r) for r in rows]
