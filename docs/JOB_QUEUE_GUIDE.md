# Job Queue Guide

## Components
- jobs/models.py: job model and states.
- jobs/queue.py: queue interactions.
- jobs/scheduler.py: scheduling lifecycle.
- jobs/worker.py: polling and execution.
- jobs/handlers.py and jobs/builtin_handlers.py: handler registration and behavior.

## Concrete Lifecycle
1. Enqueue work with jobs.queue.enqueue(job_type, payload, created_by).
2. Worker claims oldest pending job via jobs.queue.claim_next() using SKIP LOCKED.
3. Worker resolves handler by job_type from jobs.handlers.get_handler().
4. Handler returns result payload; queue marks completed or failed.

```python
# jobs/builtin_handlers.py
@register("ping")
async def handle_ping(payload):
	return {"pong": True, **payload}
```

```python
# jobs/queue.py
rows = await Database.fetch("""
UPDATE staffninja_jobs
SET status = 'running', started_at = NOW(), attempt = attempt + 1
WHERE id = (
	SELECT id FROM staffninja_jobs
	WHERE status = 'pending'
	ORDER BY created_at
	LIMIT 1
	FOR UPDATE SKIP LOCKED
)
RETURNING *
""")
```

## Handler Pattern
1. Register job type to handler in jobs/handlers.py.
2. Keep handler idempotent when possible.
3. Return explicit success/failure outcomes for retry logic.

## Add a New Job Type Checklist
- Define payload contract.
- Register handler mapping.
- Add tests in tests/test_job_queue.py.
- Validate retry and timeout behavior.
