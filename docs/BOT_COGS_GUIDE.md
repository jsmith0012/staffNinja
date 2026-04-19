# Bot Cogs Guide

## Responsibilities
- Cogs in bot/cogs/ own Discord command/event wiring.
- Keep command functions thin and delegate logic to services/.
- Utility modules (e.g. bot/cogs/mailing_lists.py) may live alongside cogs but are not loaded as cogs — they provide shared Views, helpers, and embed builders.

## Do and Prefer
```python
# Preferred: delegate reusable logic to services
docs = await _svc_search_documents(question, category_filter=allowed_categories)
await interaction.response.send_message(rendered, ephemeral=True)
```

```python
# Acceptable for one-off health checks in existing code
rows = await Database.fetch("SELECT 1 AS ok")
```

Use direct DB access in cogs only for narrow operational checks. Move reusable or multi-step business logic into services.

## Ephemeral Message Pattern
When using interactive Views (select menus, buttons) with ephemeral messages:
```python
# Correct: defer() then edit_original_response()
await interaction.response.defer()
# ... do work ...
await interaction.edit_original_response(embed=embed, view=self)
await interaction.followup.send("result", ephemeral=True)
```
Do NOT use `defer(thinking=True)` with `message.edit()` — it causes 404 errors on ephemeral messages.

## Pattern
1. Validate command input quickly.
2. Call a service async method.
3. Convert service result into Discord response.
4. Handle expected user-facing errors cleanly.

## All Slash Commands
All commands are under the `/staffninja` group (defined in bot/cogs/staffninja.py):
- `/staffninja server` — server health check (DB, email, uptime)
- `/staffninja help` — list available commands
- `/staffninja jobs` — job queue status
- `/staffninja event` — active event info and metrics
- `/staffninja link` — link Discord account to staff email
- `/staffninja verify` — verify email code to complete linking
- `/staffninja status` — staff profile (positions, leadership status, agreement status)
- `/staffninja mailinglist` — view/manage mailing list subscriptions (interactive View)
- `/staffninja policy` — search policy documents (uses db_search or AI provider)

### Disabling Commands
You can disable specific slash commands by setting the `DISABLED_COMMANDS` environment variable in `.env`:
```bash
# Disable one or more commands (comma-separated, case-insensitive)
DISABLED_COMMANDS="policy,mailinglist"
```

Disabled commands will not appear in Discord's slash command autocomplete after the bot restarts and syncs commands. To re-enable commands, remove them from the list or clear the variable entirely.

Available command names: `server`, `help`, `jobs`, `event`, `link`, `verify`, `status`, `mailinglist`, `policy`

## Utility Modules
- **bot/cogs/mailing_lists.py**: NOT a cog. Provides `_get_user_email()`, `_is_leadership()`, `MailingListView`, and `_build_embed()`. Imported by staffninja.py.

## Add a New Command Checklist
- Add command handler in bot/cogs/staffninja.py (inside StaffNinjaGroup).
- Keep DB access out of cog when possible.
- Add or reuse service method for business logic.
- Add tests for command logic path and service behavior.
- Confirm slash command sync behavior in development guild.
