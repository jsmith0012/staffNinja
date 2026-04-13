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

## External API Mocking
When testing code that calls external services (e.g. Google Groups), mock at the service boundary:
```python
# tests/test_mailing_lists.py pattern
@patch("services.google_groups_service.get_user_groups", new_callable=AsyncMock)
@patch("services.google_groups_service.get_allowed_groups")
async def test_mailinglist_view(mock_allowed, mock_user_groups):
    mock_allowed.return_value = ["staff@example.com"]
    mock_user_groups.return_value = [{"email": "staff@example.com", "name": "Staff"}]
    # ... test logic
```

## Test Files
- tests/test_job_queue.py: job queue operations and claim logic.
- tests/test_db_contract.py: database connectivity and query patterns.
- tests/test_reminders.py: reminder service behavior.
- tests/test_staff_status.py: staff status lookups.
- tests/test_mailing_lists.py: mailing list views, Google API mocking, leadership filtering.
