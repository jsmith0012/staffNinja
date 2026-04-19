"""Built-in job handlers that ship with staffNinja.

Add new ``@register("job_type")`` handlers here (or in separate modules
that are imported from ``jobs/__init__.py``).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from config.settings import get_settings
from jobs.handlers import register

logger = logging.getLogger(__name__)
settings = get_settings()


@register("ping")
async def handle_ping(payload: dict[str, Any]) -> dict[str, Any]:
    """Trivial health-check job.  Returns the payload back as the result."""
    logger.info("Ping job executed with payload: %s", payload)
    return {"pong": True, **payload}


@register("log_message")
async def handle_log_message(payload: dict[str, Any]) -> dict[str, Any]:
    """Write a message to the application log — useful for scheduled notices."""
    message = payload.get("message", "(no message)")
    level = payload.get("level", "INFO").upper()
    log_fn = getattr(logger, level.lower(), logger.info)
    log_fn("Scheduled log message: %s", message)
    return {"logged": True}


def _rotate_backups(backup_dir: Path, daily_keep: int = 7, monthly_keep: int = 3) -> dict[str, Any]:
    """Rotate backup files: keep last N daily backups + 1 per month for M months.
    
    Args:
        backup_dir: Directory containing backup files
        daily_keep: Number of recent daily backups to keep (default 7)
        monthly_keep: Number of months to keep monthly backups (default 3)
    
    Returns:
        Dict with rotation stats: kept_count, deleted_count, freed_bytes
    """
    if not backup_dir.exists():
        return {"kept_count": 0, "deleted_count": 0, "freed_bytes": 0}
    
    # Find all backup files matching our naming pattern
    backup_files = []
    for f in backup_dir.glob("staffninja_backup_*.sql.gz"):
        try:
            # Extract timestamp from filename: staffninja_backup_YYYYMMDD_HHMMSS.sql.gz
            parts = f.stem.replace(".sql", "").split("_")
            if len(parts) >= 4:
                date_str = parts[2]  # YYYYMMDD
                time_str = parts[3]  # HHMMSS
                timestamp = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
                backup_files.append((f, timestamp))
        except (ValueError, IndexError) as e:
            logger.warning("Skipping invalid backup filename %s: %s", f.name, e)
    
    if not backup_files:
        return {"kept_count": 0, "deleted_count": 0, "freed_bytes": 0}
    
    # Sort by timestamp (newest first)
    backup_files.sort(key=lambda x: x[1], reverse=True)
    
    # Determine which backups to keep
    to_keep = set()
    
    # Keep last N daily backups
    for f, ts in backup_files[:daily_keep]:
        to_keep.add(f)
    
    # Keep one backup per month for the last M months
    now = datetime.now()
    monthly_buckets = {}
    for f, ts in backup_files:
        # Month bucket is YYYY-MM
        month_key = ts.strftime("%Y-%m")
        # Only consider backups from last M months
        months_diff = (now.year - ts.year) * 12 + (now.month - ts.month)
        if months_diff < monthly_keep:
            # Keep the newest backup from each month
            if month_key not in monthly_buckets:
                monthly_buckets[month_key] = f
                to_keep.add(f)
    
    # Delete backups not in the keep set
    deleted_count = 0
    freed_bytes = 0
    for f, ts in backup_files:
        if f not in to_keep:
            try:
                size = f.stat().st_size
                f.unlink()
                deleted_count += 1
                freed_bytes += size
                logger.info("Deleted old backup: %s (freed %d bytes)", f.name, size)
            except Exception as e:
                logger.error("Failed to delete backup %s: %s", f.name, e)
    
    kept_count = len(to_keep)
    logger.info(
        "Backup rotation complete: kept=%d deleted=%d freed=%.2fMB",
        kept_count,
        deleted_count,
        freed_bytes / (1024 * 1024)
    )
    
    return {
        "kept_count": kept_count,
        "deleted_count": deleted_count,
        "freed_bytes": freed_bytes
    }


@register("database_backup")
async def handle_database_backup(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a compressed PostgreSQL backup and rotate old backups.
    
    Payload (all optional):
        - backup_dir: Override default backup directory
        - skip_rotation: Skip backup rotation if True
    
    Returns:
        Dict with backup metadata: filename, size_bytes, duration_seconds, etc.
    """
    start_time = time.time()
    
    # Get backup directory
    backup_dir_str = payload.get("backup_dir", settings.DB_BACKUP_DIR)
    backup_dir = Path(backup_dir_str)
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"staffninja_backup_{timestamp}.sql.gz"
    backup_path = backup_dir / filename
    
    logger.info("Starting database backup to %s", backup_path)
    
    # Build pg_dump command with gzip compression
    cmd = [
        "pg_dump",
        "-h", settings.POSTGRES_HOST,
        "-p", str(settings.POSTGRES_PORT),
        "-U", settings.POSTGRES_USER,
        "-d", settings.POSTGRES_DB,
        "--no-password",
    ]
    
    # Set PGPASSWORD environment variable for authentication
    env = os.environ.copy()
    env["PGPASSWORD"] = settings.POSTGRES_PASSWORD
    
    try:
        # Run pg_dump and pipe to gzip
        with open(backup_path, "wb") as out_file:
            # Start pg_dump process
            pg_dump = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            
            # Start gzip process
            gzip_proc = await asyncio.create_subprocess_exec(
                "gzip",
                stdin=pg_dump.stdout,
                stdout=out_file,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Wait for both processes to complete
            pg_stderr = await pg_dump.stderr.read()
            gzip_stderr = await gzip_proc.stderr.read()
            
            pg_returncode = await pg_dump.wait()
            gzip_returncode = await gzip_proc.wait()
            
            if pg_returncode != 0:
                error_msg = pg_stderr.decode("utf-8", errors="replace")
                logger.error("pg_dump failed (exit %d): %s", pg_returncode, error_msg)
                # Clean up partial backup file
                if backup_path.exists():
                    backup_path.unlink()
                return {
                    "success": False,
                    "error": f"pg_dump failed: {error_msg[:200]}"
                }
            
            if gzip_returncode != 0:
                error_msg = gzip_stderr.decode("utf-8", errors="replace")
                logger.error("gzip failed (exit %d): %s", gzip_returncode, error_msg)
                if backup_path.exists():
                    backup_path.unlink()
                return {
                    "success": False,
                    "error": f"gzip failed: {error_msg[:200]}"
                }
        
        # Get backup file size
        size_bytes = backup_path.stat().st_size
        duration = time.time() - start_time
        
        logger.info(
            "Database backup completed: %s (%.2f MB in %.1f seconds)",
            filename,
            size_bytes / (1024 * 1024),
            duration
        )
        
        result = {
            "success": True,
            "filename": filename,
            "path": str(backup_path),
            "size_bytes": size_bytes,
            "size_mb": round(size_bytes / (1024 * 1024), 2),
            "duration_seconds": round(duration, 2),
            "timestamp": timestamp
        }
        
        # Rotate old backups unless explicitly skipped
        if not payload.get("skip_rotation", False):
            rotation_result = _rotate_backups(backup_dir)
            result["rotation"] = rotation_result
        
        return result
        
    except Exception as e:
        logger.exception("Database backup failed: %s", e)
        # Clean up partial backup file
        if backup_path.exists():
            try:
                backup_path.unlink()
            except Exception:
                pass
        return {
            "success": False,
            "error": str(e)[:200]
        }
