from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
from sqlalchemy import text

from .backup_service import database_path, list_backups


APP_VERSION = "10.9.0"


def collect_health(app, db, migration_rows, email_configured=False):
    database_ok = True
    database_error = None

    try:
        db.session.execute(text("SELECT 1")).scalar()
    except Exception as exc:
        database_ok = False
        database_error = str(exc)

    db_path = database_path(db)
    db_size = (
        db_path.stat().st_size
        if db_path and db_path.exists()
        else 0
    )

    backups = list_backups(app)
    latest_backup = backups[0] if backups else None

    disk = shutil.disk_usage(app.instance_path)

    log_path = Path(app.instance_path) / "logs" / "rocket.log"

    return {
        "version": APP_VERSION,
        "checked_at": datetime.now(),
        "database_ok": database_ok,
        "database_error": database_error,
        "database_path": str(db_path) if db_path else None,
        "database_size": db_size,
        "latest_backup": latest_backup,
        "backup_count": len(backups),
        "disk_free": disk.free,
        "disk_total": disk.total,
        "migrations": migration_rows,
        "migrations_ok": all(row["applied"] for row in migration_rows),
        "email_configured": email_configured,
        "log_path": str(log_path),
        "log_exists": log_path.exists(),
        "debug": bool(app.debug),
    }
