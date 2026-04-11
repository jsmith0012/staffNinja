# Database Guide

## Core Pattern
- Use db/connection.py for pool lifecycle and query execution.
- Keep schema changes in db/migrations/*.sql.
- Keep query logic centralized through db/ patterns.

## Concrete Examples
```python
# db/connection.py
ssl_mode = settings.POSTGRES_SSL.strip().lower()
ssl_value = None if ssl_mode in {"", "disable", "false", "0"} else ssl_mode
cls._pool = await asyncpg.create_pool(..., ssl=ssl_value)
```

```sql
-- jobs/queue.py claim pattern
SELECT id FROM staffninja_jobs
WHERE status = 'pending'
ORDER BY created_at
LIMIT 1
FOR UPDATE SKIP LOCKED
```

```sql
-- jobs/queue.py payload insert pattern
INSERT INTO staffninja_jobs (job_type, payload, created_by, max_retries)
VALUES ($1, $2::jsonb, $3, $4)
```

## Environment Keys
- POSTGRES_HOST
- POSTGRES_PORT
- POSTGRES_DB
- POSTGRES_USER
- POSTGRES_PASSWORD
- POSTGRES_SSL

## SSL Mode Guidance
- Local clone/dev commonly uses POSTGRES_SSL=disable or prefer.
- Azure/Postgres cloud commonly uses POSTGRES_SSL=require.
- Align setting with actual server requirements to avoid connection failures.

## Add DB Changes Checklist
- Add or update migration SQL.
- Update query/model usage in db/.
- Add or update tests in tests/test_db_contract.py and related modules.
