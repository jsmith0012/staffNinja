# Errors and Troubleshooting

## Database Connection Failures
- Check host, database, user, and password values in .env.
- Confirm POSTGRES_SSL matches server requirements.
- Verify network reachability to database host and port.

## Remote Test Task Failures
- Verify SSH key authentication works without password prompts.
- Confirm remote project path and remote .venv are valid.
- Run the remote install test dependencies task when needed.

## Discord Command Issues
- Confirm bot token and guild ID values.
- Ensure required intents are enabled in config and Discord app settings.
- Re-run bot startup to trigger command sync.

## Job Queue Stalls
- Verify scheduler and worker loops are running.
- Inspect job state transitions and retry logic.
- Check handler registration for job type mismatches.

## AI Provider Issues
- Confirm AI_PROVIDER value and endpoint settings.
- For local development, use local_stub when provider services are unavailable.
