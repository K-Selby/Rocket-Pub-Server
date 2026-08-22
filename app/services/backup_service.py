from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sqlite3


BACKUP_RETENTION = 30


def database_path(db) -> Path | None:
    database = db.engine.url.database
    if not database:
        return None
    return Path(database).resolve()


def backup_directory(app) -> Path:
    path = Path(app.instance_path) / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_backups(app):
    directory = backup_directory(app)
    rows = []

    for path in sorted(
        directory.glob("pub_booking-*.db"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    ):
        stat = path.stat()
        rows.append(
            {
                "name": path.name,
                "path": path,
                "size_bytes": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime),
            }
        )

    return rows


def prune_backups(app, keep=BACKUP_RETENTION):
    backups = list_backups(app)

    for old in backups[keep:]:
        try:
            old["path"].unlink()
        except OSError:
            pass


def create_database_backup(app, db, reason="manual"):
    source = database_path(db)

    if source is None or not source.exists():
        return None

    directory = backup_directory(app)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_reason = "".join(
        character if character.isalnum() or character in {"-", "_"} else "-"
        for character in (reason or "backup").lower()
    ).strip("-") or "backup"

    destination = directory / (
        f"pub_booking-{timestamp}-{safe_reason}.db"
    )

    # SQLite's online backup API produces a consistent copy even while the
    # application is serving requests.
    source_connection = sqlite3.connect(str(source), timeout=10)
    destination_connection = sqlite3.connect(str(destination), timeout=10)

    try:
        with destination_connection:
            source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()

    prune_backups(app)
    return destination


def create_daily_backup_if_due(app, db):
    backups = list_backups(app)

    if backups:
        age = datetime.now() - backups[0]["created_at"]
        if age < timedelta(hours=20):
            return None

    return create_database_backup(app, db, reason="daily")
