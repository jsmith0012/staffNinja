# staffNinja Discord Bot

A modular, maintainable Discord bot for Anime Nebraskon staff support.

## Features (Planned)
- Staff status tracking
- Reminders and nudges
- Organization tools
- Slash command group `/staffninja` with initial health/help commands
- Safe PostgreSQL integration
- Modular cogs/services
- AI/agent framework (future)

## Setup
1. Copy `.env.example` to `.env` and fill in values.
2. Install dependencies: `pip install -r requirements.txt`
3. Run migrations for bot-owned tables (if any): `alembic upgrade head`
4. Start the bot: `python -m bot.main`

## Development
- All features are modular cogs in `bot/cogs/`.
- Database access is via the `db/` layer. Only add new tables with clear namespacing.
- AI and agent features are stubs/TODOs for now.
- Local edits upload to the Linux host via VS Code SFTP on save.
- Rapid remote test loop from this workspace: run the VS Code tasks `Remote: pytest all`, `Remote: pytest current file`, or `Remote: pytest custom`.
- One-time remote setup for tests: run `Remote: install test deps` to install `pytest` into `/home/jsmith/staffNinja/.venv`.
- Slash commands are synced to `DISCORD_GUILD_ID` on startup for fast command updates.

## Slash Commands
- `/staffninja server`: Ephemeral server health status (service process, Discord gateway, DB check, host, uptime).
- `/staffninja help`: Ephemeral list of supported slash commands.

## Testing
- Unit tests: `pytest tests/`
- Integration/contract tests: see `tests/`

## Documentation
- Copilot instruction entrypoint: `.github/copilot-instructions.md`
- Knowledge pack index: `docs/README.md`
- Architecture guide: `docs/ARCHITECTURE.md`
- Development workflow: `docs/DEVELOPMENT.md`
- Bot cogs patterns: `docs/BOT_COGS_GUIDE.md`
- Service layer patterns: `docs/SERVICE_LAYER_GUIDE.md`
- Database conventions: `docs/DATABASE_GUIDE.md`
- Job queue patterns: `docs/JOB_QUEUE_GUIDE.md`
- Testing guide: `docs/TESTING.md`
- Agent framework status: `docs/AGENT_FRAMEWORK.md`
- Troubleshooting: `docs/ERRORS_AND_TROUBLESHOOTING.md`

This documentation set is the syncable Copilot knowledge pack for cross-PC consistency.

## Deployment
- Use a process manager (systemd, pm2, etc.)
- Configure environment variables for production
- Monitor logs for errors

---

See code comments and docs for more details.
