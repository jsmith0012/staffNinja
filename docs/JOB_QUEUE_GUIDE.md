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

## Built-in Job Types

### ping
Health check job that echoes payload back.
```python
await enqueue("ping", {"test": "value"})
# Returns: {"pong": True, "test": "value"}
```

### log_message
Write a message to application logs.
```python
await enqueue("log_message", {"message": "Scheduled task", "level": "INFO"})
# Returns: {"logged": True}
```

### database_backup
Create compressed PostgreSQL backup with automatic rotation (7 daily + 3 monthly).

**Configuration** (in .env):
```bash
DB_BACKUP_ENABLED=true
DB_BACKUP_DIR=/home/jsmith/staffNinja/backups
DB_BACKUP_HOUR=3  # UTC hour for daily backup (default: 3 AM)
```

**Payload** (all optional):
- `backup_dir`: Override default backup directory
- `skip_rotation`: Skip backup rotation if true

**Returns**:
```python
{
    "success": True,
    "filename": "staffninja_backup_20260419_030000.sql.gz",
    "path": "/home/jsmith/staffNinja/backups/staffninja_backup_20260419_030000.sql.gz",
    "size_bytes": 12345678,
    "size_mb": 11.77,
    "duration_seconds": 8.45,
    "timestamp": "20260419_030000",
    "rotation": {
        "kept_count": 10,
        "deleted_count": 3,
        "freed_bytes": 34567890
    }
}
```

**Scheduling**: When `DB_BACKUP_ENABLED=true`, backups run daily at the configured hour (default 3 AM UTC). The job is enqueued automatically by the scheduler in bot/main.py.

**Rotation Logic**:
- Keeps last 7 daily backups (most recent)
- Keeps 1 backup per month for the last 3 months
- Deletes all other backups
- Example: On 2026-04-19, keeps newest from April, March, February + last 7 daily

**Manual Backup**:
```python
from jobs import enqueue
await enqueue("database_backup", {})
```

**Restore Procedure**:
```bash
# List available backups
ls -lh /home/jsmith/staffNinja/backups/

# Restore from compressed backup
gunzip < /home/jsmith/staffNinja/backups/staffninja_backup_20260419_030000.sql.gz | \
  psql -h localhost -U staffninja -d staffninja_db

# Or restore in one command with PGPASSWORD
PGPASSWORD=yourpass gunzip < backup.sql.gz | psql -h host -U user -d db
```

**Monitoring**:
- Check backup job status via `/staffninja jobs` Discord command
- Review logs for backup completion and rotation summaries
- Monitor backup directory disk usage
- Verify backup file sizes are consistent (sudden changes may indicate issues)
