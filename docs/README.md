# staffNinja Knowledge Pack

This folder is the syncable Copilot knowledge pack for this repository. It is git-tracked and intended to stay consistent across PCs.

## Guides
- ARCHITECTURE.md: system boundaries, module flow, entry points.
- DEVELOPMENT.md: local and remote workflow, setup, and commands.
- BOT_COGS_GUIDE.md: command and cog patterns.
- SERVICE_LAYER_GUIDE.md: service design patterns.
- DATABASE_GUIDE.md: connection, SSL, query, and migration conventions.
- JOB_QUEUE_GUIDE.md: scheduler, queue, and handler extension patterns.
- TESTING.md: test strategy and command matrix.
- AGENT_FRAMEWORK.md: current placeholder state and future integration.
- ERRORS_AND_TROUBLESHOOTING.md: common failures and fixes.

## Update Trigger
When changing commands, configuration keys, architecture boundaries, or runtime behavior, update the relevant guide in this folder.

## Maintenance Checklist
- Commands or task labels changed: update DEVELOPMENT.md and TESTING.md.
- DB schema/query behavior changed: update DATABASE_GUIDE.md and related tests.
- Queue or handler behavior changed: update JOB_QUEUE_GUIDE.md.
- Cog-to-service boundary changed: update BOT_COGS_GUIDE.md and SERVICE_LAYER_GUIDE.md.
