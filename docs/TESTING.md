# Testing Guide

## Test Scope
- Unit tests: fast logic tests in tests/.
- Contract/integration tests: DB and queue behavior.

## Standard Commands
- Local all tests: pytest tests/
- Remote all tests: use VS Code task Remote: pytest all
- Remote current file: use VS Code task Remote: pytest current file
- Remote custom: use VS Code task Remote: pytest custom

## Concrete Examples
```bash
pytest tests/test_job_queue.py -q
pytest tests/test_db_contract.py -q
```

```python
# tests/test_job_queue.py pattern
with patch("jobs.queue.Database") as mock_db:
	mock_db.fetch = AsyncMock(return_value=[{"cnt": 5}])
	count = await pending_count()
	assert count == 5
```

Remote task labels are defined in .vscode/tasks.json and should be kept in sync with this guide.

## Test Authoring Rules
- Prefer small deterministic tests.
- Mock external provider boundaries (Discord/AI/network) as needed.
- Keep contract tests for DB and queue behavior current when schema/logic changes.
