# Architecture

## Runtime Flow
1. bot/main.py initializes logging, settings, DB, cogs, and scheduler.
2. Cogs in bot/cogs/ receive slash commands and messages.
3. Cogs call services in services/ for business logic.
4. Services interact with db/ for data and with jobs/ for deferred execution.
5. jobs/ worker and scheduler process queued work.

## Boundaries
- bot/: Discord interactions and command handlers only.
- services/: business logic, orchestration, and validation.
- db/: connection lifecycle, models, and query operations.
- jobs/: asynchronous background processing.
- agent/: planned orchestration framework, currently skeleton.
- ai/: provider abstraction for local stub and Ollama integration.

## Entry Points
- bot/main.py is the primary process entrypoint.
- jobs/scheduler.py and jobs/worker.py define background flow.
- config/settings.py defines environment-driven settings.

## Current vs Planned
- Current production behavior relies on cogs + services + db + jobs.
- agent/ should be treated as non-authoritative until concrete implementation is complete.
