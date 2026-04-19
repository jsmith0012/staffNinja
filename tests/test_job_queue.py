"""Tests for the job queue — models, handlers, and anime quotes."""

from __future__ import annotations

import datetime
import pytest
from unittest.mock import AsyncMock, patch

from jobs.models import Job, JobStatus
from jobs.handlers import register, get_handler, registered_types, _registry
from jobs.anime_quotes import (
    ANIME_WAIT_QUOTES,
    random_wait_quote,
    random_wait_message,
)


# ── Model tests ───────────────────────────────────────────────────────────

class TestJobModel:
    def test_from_record(self):
        row = {
            "id": 42,
            "job_type": "ping",
            "payload": {"hello": "world"},
            "status": "pending",
            "result": None,
            "error": None,
            "created_at": datetime.datetime(2026, 3, 30, tzinfo=datetime.timezone.utc),
            "started_at": None,
            "completed_at": None,
            "created_by": 12345,
            "max_retries": 3,
            "attempt": 0,
        }
        job = Job.from_record(row)
        assert job.id == 42
        assert job.job_type == "ping"
        assert job.payload == {"hello": "world"}
        assert job.status == JobStatus.PENDING
        assert job.created_by == 12345

    def test_from_record_empty_payload(self):
        row = {
            "id": 1,
            "job_type": "test",
            "payload": None,
            "status": "running",
            "result": None,
            "error": None,
            "created_at": datetime.datetime.now(tz=datetime.timezone.utc),
            "started_at": None,
            "completed_at": None,
            "created_by": None,
            "max_retries": 1,
            "attempt": 1,
        }
        job = Job.from_record(row)
        assert job.payload == {}
        assert job.status == JobStatus.RUNNING


class TestJobStatus:
    def test_enum_values(self):
        assert JobStatus.PENDING == "pending"
        assert JobStatus.RUNNING == "running"
        assert JobStatus.COMPLETED == "completed"
        assert JobStatus.FAILED == "failed"


# ── Handler registry tests ────────────────────────────────────────────────

class TestHandlerRegistry:
    def test_register_and_lookup(self):
        @register("_test_type")
        async def _dummy(payload):
            return {"ok": True}

        assert get_handler("_test_type") is _dummy
        assert "_test_type" in registered_types()

        # Cleanup
        _registry.pop("_test_type", None)

    def test_missing_handler_returns_none(self):
        assert get_handler("nonexistent_handler_xyz") is None

    def test_builtin_ping_registered(self):
        import jobs.builtin_handlers  # noqa: F401
        assert get_handler("ping") is not None

    def test_builtin_log_message_registered(self):
        import jobs.builtin_handlers  # noqa: F401
        assert get_handler("log_message") is not None


# ── Anime quotes tests ────────────────────────────────────────────────────

class TestAnimeQuotes:
    def test_quote_list_not_empty(self):
        assert len(ANIME_WAIT_QUOTES) >= 20

    def test_every_quote_has_keys(self):
        for entry in ANIME_WAIT_QUOTES:
            assert "anime" in entry, f"Missing 'anime' key in {entry}"
            assert "quote" in entry, f"Missing 'quote' key in {entry}"
            assert len(entry["anime"]) > 0
            assert len(entry["quote"]) > 0

    def test_random_wait_quote_returns_dict(self):
        result = random_wait_quote()
        assert isinstance(result, dict)
        assert "anime" in result
        assert "quote" in result

    def test_random_wait_message_formatted(self):
        msg = random_wait_message()
        assert "**" in msg  # bold anime title
        assert "*" in msg   # italic quote


# ── Builtin handler tests ─────────────────────────────────────────────────

class TestBuiltinHandlers:
    @pytest.mark.asyncio
    async def test_ping_returns_pong(self):
        handler = get_handler("ping")
        result = await handler({"foo": "bar"})
        assert result["pong"] is True
        assert result["foo"] == "bar"

    @pytest.mark.asyncio
    async def test_log_message(self):
        handler = get_handler("log_message")
        result = await handler({"message": "test", "level": "INFO"})
        assert result["logged"] is True


# ── Queue function tests (mocked DB) ─────────────────────────────────────

class TestQueueFunctions:
    @pytest.mark.asyncio
    async def test_enqueue_calls_db(self):
        fake_row = {
            "id": 99,
            "job_type": "ping",
            "payload": "{}",
            "status": "pending",
            "result": None,
            "error": None,
            "created_at": datetime.datetime.now(tz=datetime.timezone.utc),
            "started_at": None,
            "completed_at": None,
            "created_by": None,
            "max_retries": 3,
            "attempt": 0,
        }
        with patch("jobs.queue.Database") as mock_db:
            mock_db.fetch = AsyncMock(return_value=[fake_row])
            from jobs.queue import enqueue
            job = await enqueue("ping", {"test": True})
            assert job.id == 99
            assert job.job_type == "ping"
            mock_db.fetch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_claim_next_empty(self):
        with patch("jobs.queue.Database") as mock_db:
            mock_db.fetch = AsyncMock(return_value=[])
            from jobs.queue import claim_next
            result = await claim_next()
            assert result is None

    @pytest.mark.asyncio
    async def test_pending_count(self):
        with patch("jobs.queue.Database") as mock_db:
            mock_db.fetch = AsyncMock(return_value=[{"cnt": 5}])
            from jobs.queue import pending_count
            count = await pending_count()
            assert count == 5

    @pytest.mark.asyncio
    async def test_reap_stale_jobs(self):
        with patch("jobs.queue.Database") as mock_db:
            mock_db.fetch = AsyncMock(return_value=[{"id": 10}, {"id": 11}])
            mock_db.execute = AsyncMock()
            from jobs.queue import reap_stale_jobs
            reaped = await reap_stale_jobs(600)
            assert reaped == 2
            mock_db.fetch.assert_awaited_once()
            mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_job_counts(self):
        with patch("jobs.queue.Database") as mock_db:
            mock_db.fetch = AsyncMock(return_value=[
                {"status": "pending", "cnt": 3},
                {"status": "completed", "cnt": 10},
                {"status": "failed", "cnt": 1},
            ])
            from jobs.queue import job_counts
            counts = await job_counts()
            assert counts == {"pending": 3, "completed": 10, "failed": 1}

    @pytest.mark.asyncio
    async def test_recent_failed_empty(self):
        with patch("jobs.queue.Database") as mock_db:
            mock_db.fetch = AsyncMock(return_value=[])
            from jobs.queue import recent_failed
            result = await recent_failed()
            assert result == []
