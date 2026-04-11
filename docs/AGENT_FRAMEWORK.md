# Agent Framework Status

## Current State
Files under agent/ define planned structure and placeholders for future orchestration.

## Important Constraint
Treat agent/ as non-authoritative for current runtime behavior unless specific implementation is added and wired from bot/main.py.

## Planned Direction
- Planner coordinates tasks.
- Tool registry exposes safe tool operations.
- Audit captures action history.
- Agent context carries request-scoped metadata.

## Implementation Rule
When adding real agent behavior, update this guide and docs/ARCHITECTURE.md in the same change.
