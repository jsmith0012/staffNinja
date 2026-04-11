# Service Layer Guide

## Purpose
Services in services/ contain business logic and coordinate DB, jobs, and provider calls.

## Implemented Examples
- services/document_search_service.py exposes reusable async retrieval logic used by cogs.
- jobs/queue.py provides queue operations that services can call when work should run asynchronously.

## Concrete Pattern
Use a service boundary for reusable logic, then call it from a cog.

```python
# bot/cogs/staffninja.py (existing usage)
docs = await _svc_search_documents(question, category_filter=allowed_categories)

# services/document_search_service.py (service boundary)
rows = await Database.fetch("SELECT ... FROM \"Document\" ...", search_candidate)
```

## Conventions
- Use async methods for IO-heavy operations.
- Keep service methods deterministic and testable.
- Raise domain-specific errors from utils/errors.py when appropriate.
- Keep Discord-specific response formatting in cogs, not services.

## Placeholder Notice
- services/org_tools_service.py is currently a TODO stub. Do not use it as a pattern source until implemented.

## Add a New Service Method Checklist
- Define method in existing service or create a focused new service module.
- Accept clear inputs and return explicit structured results.
- Use db/ query helpers rather than ad hoc SQL in service callers.
- Add unit tests covering success and failure paths.
