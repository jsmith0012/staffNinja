# staffNinja Discord Bot

A modular, maintainable Discord bot for Anime Nebraskon staff support.

## Features (Planned)
- Staff status tracking
- Reminders and nudges
- Organization tools
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

## Testing
- Unit tests: `pytest tests/`
- Integration/contract tests: see `tests/`

## Deployment
- Use a process manager (systemd, pm2, etc.)
- Configure environment variables for production
- Monitor logs for errors

---

See code comments and docs for more details.
