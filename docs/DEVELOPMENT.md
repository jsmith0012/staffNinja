# Development Workflow

## Local Setup
1. Copy .env.example to .env.
2. Install dependencies: pip install -r requirements.txt
3. Start the bot: python -m bot.main

## Remote Workflow
- Edits are uploaded to remote Linux host via VS Code SFTP on save.
- Remote test loops are available through VS Code tasks in .vscode/tasks.json.
- Typical tasks include running all tests, running current file, and custom pytest args.

### Current Task Labels
- Remote: pytest all
- Remote: pytest current file
- Remote: pytest custom
- Remote: install test deps

These labels are the source of truth for team workflow and should match .vscode/tasks.json exactly.

## Remote Test Dependencies
- Install test dependencies on remote host using the dedicated remote install task.
- Ensure remote .venv has pytest and requirements installed.

The install task runs:
- source .venv/bin/activate && python -m pip install -r requirements.txt pytest

## SSH Notes
- Fast non-interactive remote testing expects SSH key auth.
- If auth prompts appear, fix SSH keys/agent before relying on task automation.

If SSH auth is not key-based, remote tasks may block waiting for password prompts.

## Environment Notes
- Keep secrets only in .env, never commit real credentials.
- Config behavior is defined in config/settings.py.

### Debug Log to Discord
- `DEBUG_LOG_TO_DISCORD=true` enables forwarding of application logs to a Discord channel named `debug_log`.
- When enabled, the bot will create the channel if it doesn't exist (requires Manage Channels permission).
- This is independent of `LOG_LEVEL` — you can have DEBUG logging to files without Discord forwarding.
- Default: `false` (disabled)
- To enable: Add `DEBUG_LOG_TO_DISCORD=true` to your `.env` file and restart the bot.
