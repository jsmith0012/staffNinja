# Service Layer Guide

## Purpose
Services in services/ contain business logic and coordinate DB, jobs, provider calls, and external API integrations.

## Implemented Services
- **services/document_search_service.py**: reusable async document/policy retrieval logic used by cogs and chat monitor.
- **services/google_groups_service.py**: Google Workspace Groups integration for mailing list membership management.
- **services/reminder_service.py**: reminder scheduling logic.
- **services/staff_status_service.py**: staff status lookup (stub).
- **services/org_tools_service.py**: org tools (stub).

## Concrete Patterns

### Database service pattern
```python
# services/document_search_service.py
rows = await Database.fetch("SELECT ... FROM \"Document\" ...", search_candidate)
```

### External API service pattern
```python
# services/google_groups_service.py
from utils.errors import GoogleGroupsError

async def get_user_groups(user_email: str) -> list[dict]:
    service = _build_service()  # cached Google Admin SDK client
    response = await asyncio.to_thread(
        service.groups().list(userKey=user_email).execute,
    )
    # ... process and return results

async def remove_member(group_email: str, user_email: str) -> None:
    if is_protected(group_email):
        raise GoogleGroupsError(f"Cannot opt out of protected group: {group_email}")
    # ... call Google API
```

## Google Groups Service
Manages mailing list memberships via Google Admin SDK Directory API.
- **Auth**: Service account with domain-wide delegation (`GOOGLE_SERVICE_ACCOUNT_FILE`, `GOOGLE_DELEGATED_ADMIN`).
- **Config helpers**: `get_allowed_groups()`, `get_protected_groups()`, `is_protected()` — driven by env vars.
- **Operations**: `get_user_groups()`, `add_member()`, `remove_member()`.
- **Errors**: Raises `GoogleGroupsError` (from utils/errors.py) for API failures and protected group violations.
- **Leadership filtering**: `MAILINGLIST_LEADERSHIP_GROUP` is filtered out for non-leaders at the cog level using `_is_leadership()`.

## Conventions
- Use async methods for IO-heavy operations.
- Keep service methods deterministic and testable.
- Raise domain-specific errors from utils/errors.py when appropriate.
- Keep Discord-specific response formatting in cogs, not services.
- For external API calls, use `asyncio.to_thread()` to avoid blocking the event loop.

## Add a New Service Method Checklist
- Define method in existing service or create a focused new service module.
- Accept clear inputs and return explicit structured results.
- Use db/ query helpers rather than ad hoc SQL in service callers.
- Add unit tests covering success and failure paths.
