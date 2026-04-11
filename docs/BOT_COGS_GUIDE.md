# Bot Cogs Guide

## Responsibilities
- Cogs in bot/cogs/ own Discord command/event wiring.
- Keep command functions thin and delegate logic to services/.

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

## Pattern
1. Validate command input quickly.
2. Call a service async method.
3. Convert service result into Discord response.
4. Handle expected user-facing errors cleanly.

## Add a New Command Checklist
- Add command handler in the relevant cog file.
- Keep DB access out of cog when possible.
- Add or reuse service method for business logic.
- Add tests for command logic path and service behavior.
- Confirm slash command sync behavior in development guild.

## Existing Command Examples
- staffninja server health command.
- staffninja help command.
- staffninja jobs command uses queue read models and registered handler listing.
