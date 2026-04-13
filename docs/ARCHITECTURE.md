# Architecture

## Runtime Flow
1. bot/main.py initializes logging, settings, DB, cogs, and scheduler.
2. Cogs in bot/cogs/ receive slash commands and messages.
3. Cogs call services in services/ for business logic.
4. Services interact with db/ for data and with jobs/ for deferred execution.
5. jobs/ worker and scheduler process queued work.
6. bot/main.py maintains Staff Stats voice channels (active staff count, agreements) via periodic updates.

## Boundaries
- bot/: Discord interactions and command handlers only.
- bot/cogs/mailing_lists.py: utility module (not a cog) — provides MailingListView, helpers for mailing list commands.
- services/: business logic, orchestration, validation, and external API integrations (e.g. Google Groups).
- db/: connection lifecycle, models, and query operations.
- jobs/: asynchronous background processing.
- agent/: planned orchestration framework, currently skeleton.
- ai/: provider abstraction for local stub, Ollama, and db_search (direct DB search without LLM).

## Key Shared Tables (read-only, not owned by bot)
- "User": staff members, linked via "Discord" column.
- "StaffPosition": positions with LeadershipPosition boolean and DepartmentId.
- "UserStaffPosition": many-to-many join of users to positions.
- "Event", "CompletedForm", "Document": event data, staff agreements, and policy documents.

## Entry Points
- bot/main.py is the primary process entrypoint.
- jobs/scheduler.py and jobs/worker.py define background flow.
- config/settings.py defines environment-driven settings.

## Current vs Planned
- Current production behavior relies on cogs + services + db + jobs.
- agent/ should be treated as non-authoritative until concrete implementation is complete.
