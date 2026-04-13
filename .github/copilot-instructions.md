# staffNinja Copilot Instructions

This repository is the source of truth for cross-PC Copilot context. Keep this file and linked docs updated as the code changes.

## Project Context
- Type: Discord bot for Anime Nebraskon staff support.
- Stack: Python 3.10+, discord.py, asyncpg, pydantic-settings, structlog.
- Architecture: bot cogs call services; services use db layer; jobs run async work; agent framework is currently placeholder/skeleton.

## Quick Map
- Entry point: bot/main.py
- Cogs: bot/cogs/
- Utility modules: bot/cogs/mailing_lists.py (not a cog — provides mailing list helpers/Views)
- Services: services/ (includes google_groups_service.py for Google Groups API)
- Database: db/
- Jobs: jobs/
- Config: config/settings.py
- Tests: tests/

## Working Rules
- Prefer async patterns end-to-end.
- Keep Discord command logic in cogs and business logic in services.
- Route SQL through db/ layer patterns instead of ad hoc inline SQL in cogs.
- Keep settings environment-driven via config/settings.py and .env keys.
- Treat agent/ files as planned architecture unless a concrete implementation exists.

## Testing Rules
- Use pytest for all tests.
- Keep fast unit tests in tests/ and maintain DB/job contract tests.
- Prefer existing VS Code remote test tasks when working against the remote Linux host.

## Docs Index
- docs/README.md
- docs/ARCHITECTURE.md
- docs/DEVELOPMENT.md
- docs/BOT_COGS_GUIDE.md
- docs/SERVICE_LAYER_GUIDE.md
- docs/DATABASE_GUIDE.md
- docs/JOB_QUEUE_GUIDE.md
- docs/TESTING.md
- docs/AGENT_FRAMEWORK.md
- docs/ERRORS_AND_TROUBLESHOOTING.md

## Maintenance
Update this file and linked docs whenever architecture, commands, environment variables, or workflows change.
