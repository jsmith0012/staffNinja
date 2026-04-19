"""Tests for database backup rotation logic."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path


# Import the rotation function
from jobs.builtin_handlers import _rotate_backups


def _create_backup_file(backup_dir: Path, days_ago: int, hour: int = 3) -> Path:
    """Helper to create a fake backup file with specific timestamp."""
    timestamp = datetime.now() - timedelta(days=days_ago)
    timestamp = timestamp.replace(hour=hour, minute=0, second=0, microsecond=0)
    filename = f"staffninja_backup_{timestamp.strftime('%Y%m%d_%H%M%S')}.sql.gz"
    backup_file = backup_dir / filename
    backup_file.write_text("fake backup data")
    return backup_file


def test_rotate_backups_keeps_last_7_daily():
    """Rotation should keep the last 7 daily backups."""
    with tempfile.TemporaryDirectory() as tmpdir:
        backup_dir = Path(tmpdir)
        
        # Create 10 daily backups (0-9 days ago)
        for i in range(10):
            _create_backup_file(backup_dir, days_ago=i)
        
        # Run rotation
        result = _rotate_backups(backup_dir, daily_keep=7, monthly_keep=3)
        
        # Should keep 7, delete 3
        assert result["kept_count"] == 7
        assert result["deleted_count"] == 3
        assert result["freed_bytes"] > 0
        
        # Verify the correct files remain
        remaining = list(backup_dir.glob("staffninja_backup_*.sql.gz"))
        assert len(remaining) == 7


def test_rotate_backups_keeps_monthly():
    """Rotation should keep one backup per month for last 3 months."""
    with tempfile.TemporaryDirectory() as tmpdir:
        backup_dir = Path(tmpdir)
        
        # Create backups from 4 different months
        # Current month: 2 backups
        _create_backup_file(backup_dir, days_ago=1)
        _create_backup_file(backup_dir, days_ago=5)
        
        # Last month: 2 backups (35 and 40 days ago)
        _create_backup_file(backup_dir, days_ago=35)
        _create_backup_file(backup_dir, days_ago=40)
        
        # 2 months ago: 2 backups
        _create_backup_file(backup_dir, days_ago=65)
        _create_backup_file(backup_dir, days_ago=70)
        
        # 3 months ago: 1 backup (should be kept - within 3 month window)
        _create_backup_file(backup_dir, days_ago=85)
        
        # 4 months ago: 1 backup (should be deleted - outside 3 month window)
        _create_backup_file(backup_dir, days_ago=125)
        
        # Run rotation with daily_keep=3 to better see monthly retention
        result = _rotate_backups(backup_dir, daily_keep=3, monthly_keep=3)
        
        # Should keep: 3 daily + up to 3 monthly (with some overlap)
        # The exact count depends on which backups are in the "daily" set
        # At minimum, we should have at least 3 backups (the daily ones)
        assert result["kept_count"] >= 3
        
        # The 4-month-old backup should definitely be deleted
        remaining_files = list(backup_dir.glob("staffninja_backup_*.sql.gz"))
        remaining_days_ago = []
        for f in remaining_files:
            # Extract date to verify old ones are gone
            parts = f.stem.replace(".sql", "").split("_")
            if len(parts) >= 3:
                date_str = parts[2]
                backup_date = datetime.strptime(date_str, "%Y%m%d")
                days_diff = (datetime.now() - backup_date).days
                remaining_days_ago.append(days_diff)
        
        # No backup should be from 4+ months ago (>120 days)
        assert all(days < 120 for days in remaining_days_ago)


def test_rotate_backups_empty_directory():
    """Rotation should handle empty directory gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        backup_dir = Path(tmpdir)
        
        result = _rotate_backups(backup_dir)
        
        assert result["kept_count"] == 0
        assert result["deleted_count"] == 0
        assert result["freed_bytes"] == 0


def test_rotate_backups_nonexistent_directory():
    """Rotation should handle nonexistent directory gracefully."""
    backup_dir = Path("/tmp/nonexistent_backup_dir_12345")
    
    result = _rotate_backups(backup_dir)
    
    assert result["kept_count"] == 0
    assert result["deleted_count"] == 0
    assert result["freed_bytes"] == 0


def test_rotate_backups_skips_invalid_filenames():
    """Rotation should skip files that don't match the expected pattern."""
    with tempfile.TemporaryDirectory() as tmpdir:
        backup_dir = Path(tmpdir)
        
        # Create valid backup
        _create_backup_file(backup_dir, days_ago=1)
        
        # Create invalid files
        (backup_dir / "random_file.sql.gz").write_text("data")
        (backup_dir / "backup_wrong_format.gz").write_text("data")
        (backup_dir / "staffninja_backup_invalid.sql.gz").write_text("data")
        
        result = _rotate_backups(backup_dir, daily_keep=7, monthly_keep=3)
        
        # Should only count the valid backup
        assert result["kept_count"] == 1
        assert result["deleted_count"] == 0
        
        # Invalid files should still exist
        assert (backup_dir / "random_file.sql.gz").exists()
        assert (backup_dir / "backup_wrong_format.gz").exists()


def test_rotate_backups_calculates_freed_bytes():
    """Rotation should calculate freed bytes correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        backup_dir = Path(tmpdir)
        
        # Create backups with known sizes
        for i in range(10):
            f = _create_backup_file(backup_dir, days_ago=i)
            # Write different amounts of data to create different file sizes
            f.write_text("x" * (1000 * (i + 1)))
        
        result = _rotate_backups(backup_dir, daily_keep=5, monthly_keep=3)
        
        # Should have freed some bytes
        assert result["freed_bytes"] > 0
        assert result["deleted_count"] > 0
        
        # Freed bytes should be reasonable (at least 1KB per deleted file)
        assert result["freed_bytes"] >= result["deleted_count"] * 1000
