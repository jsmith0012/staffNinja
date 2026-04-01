"""Data classes for the job queue."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    """Represents a single queued job."""

    id: int
    job_type: str
    payload: dict[str, Any]
    status: JobStatus
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime.datetime
    started_at: datetime.datetime | None
    completed_at: datetime.datetime | None
    created_by: int | None
    max_retries: int
    attempt: int

    @classmethod
    def from_record(cls, row) -> Job:
        """Build a Job from an asyncpg Record."""
        return cls(
            id=row["id"],
            job_type=row["job_type"],
            payload=row["payload"] if row["payload"] else {},
            status=JobStatus(row["status"]),
            result=row["result"],
            error=row["error"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            created_by=row["created_by"],
            max_retries=row["max_retries"],
            attempt=row["attempt"],
        )
