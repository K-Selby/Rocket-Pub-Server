from __future__ import annotations

from datetime import datetime
from sqlalchemy import inspect, text


MIGRATIONS = [
    ("001_legacy_schema_baseline", "Legacy compatibility schema baseline"),
    ("002_operational_indexes", "Operational query indexes"),
]


def ensure_migration_table(db):
    db.session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS rocket_schema_migration (
                version VARCHAR(80) PRIMARY KEY,
                description VARCHAR(250) NOT NULL,
                applied_at DATETIME NOT NULL
            )
            """
        )
    )
    db.session.commit()


def applied_versions(db):
    ensure_migration_table(db)
    rows = db.session.execute(
        text("SELECT version FROM rocket_schema_migration")
    ).all()
    return {row[0] for row in rows}


def record_migration(db, version, description):
    db.session.execute(
        text(
            """
            INSERT INTO rocket_schema_migration
                (version, description, applied_at)
            VALUES (:version, :description, :applied_at)
            """
        ),
        {
            "version": version,
            "description": description,
            "applied_at": datetime.now(),
        },
    )
    db.session.commit()


def migration_001_legacy_schema_baseline(db, legacy_upgrade):
    # Reuse the existing idempotent compatibility logic once, then record a
    # baseline so future schema changes are versioned rather than silently
    # re-running ad-hoc ALTER TABLE statements forever.
    legacy_upgrade()


def migration_002_operational_indexes(db):
    # Indexes correspond to the hottest dashboard/booking/rota queries.
    statements = [
        """
        CREATE INDEX IF NOT EXISTS ix_booking_date_status
        ON booking (booking_date, status)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_booking_date_time
        ON booking (booking_date, booking_time)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_booking_table_table_booking
        ON booking_table (table_id, booking_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_large_party_date_status
        ON large_party_inquiry (event_date, status)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_diary_date_type_status
        ON staff_diary_entry (entry_date, entry_type, status)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_diary_staff_date
        ON staff_diary_entry (staff_id, entry_date)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_rota_shift_week_staff_date
        ON rota_shift (rota_week_id, staff_id, shift_date)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_shift_swap_target_status
        ON shift_swap_request (target_staff_id, status)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_shift_swap_requester_status
        ON shift_swap_request (requester_staff_id, status)
        """,
    ]

    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())

    for statement in statements:
        # Extract table name following ON so a brand-new partial database
        # doesn't fail if a feature table has not yet been created.
        flattened = " ".join(statement.split())
        table_name = flattened.split(" ON ", 1)[1].split(" ", 1)[0]
        if table_name in existing_tables:
            db.session.execute(text(statement))

    db.session.commit()


def run_pending_migrations(db, legacy_upgrade):
    ensure_migration_table(db)
    done = applied_versions(db)
    applied_now = []

    migration_functions = {
        "001_legacy_schema_baseline": (
            lambda: migration_001_legacy_schema_baseline(
                db,
                legacy_upgrade,
            )
        ),
        "002_operational_indexes": (
            lambda: migration_002_operational_indexes(db)
        ),
    }

    for version, description in MIGRATIONS:
        if version in done:
            continue

        migration_functions[version]()
        record_migration(db, version, description)
        applied_now.append(version)

    return applied_now


def migration_status(db):
    done = applied_versions(db)
    return [
        {
            "version": version,
            "description": description,
            "applied": version in done,
        }
        for version, description in MIGRATIONS
    ]
