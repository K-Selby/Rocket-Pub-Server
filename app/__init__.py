from datetime import datetime, timedelta
from flask import Flask, render_template
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import event, inspect, text
from sqlalchemy.engine import Engine
import sqlite3

load_dotenv()

db = SQLAlchemy()

migrate = Migrate()


@event.listens_for(Engine, "connect")
def configure_sqlite_connection(dbapi_connection, connection_record):
    """Safer/faster SQLite defaults for the small multi-user pub server."""
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


def _persistent_secret_key(app):
    configured = os.environ.get("ROCKET_SECRET_KEY")

    if configured and configured != "rocket-dev-change-this-later":
        return configured

    secret_path = Path(app.instance_path) / ".rocket-secret-key"
    secret_path.parent.mkdir(parents=True, exist_ok=True)

    if secret_path.exists():
        return secret_path.read_text(encoding="utf-8").strip()

    import secrets
    generated = secrets.token_urlsafe(48)
    secret_path.write_text(generated, encoding="utf-8")
    return generated


def _configure_logging(app):
    log_dir = Path(app.instance_path) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        log_dir / "rocket.log",
        maxBytes=1_500_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
    )

    if not any(
        isinstance(existing, RotatingFileHandler)
        for existing in app.logger.handlers
    ):
        app.logger.addHandler(handler)

    app.logger.setLevel(logging.INFO)


def create_app():
    """Create and configure the Rocket Pub Server application."""
    app = Flask(__name__, instance_relative_config=True)

    app.config["SECRET_KEY"] = _persistent_secret_key(app)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///pub_booking.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = (
        os.environ.get("ROCKET_COOKIE_SECURE", "0") == "1"
    )

    _configure_logging(app)

    db.init_app(app)
    migrate.init_app(app, db)

    from app import models  # noqa: F401
    from app.routes import main
    from app.services.backup_service import (
        create_daily_backup_if_due,
        create_database_backup,
    )
    from app.services.migration_service import run_pending_migrations
    from app.services.security_service import apply_security_headers

    app.register_blueprint(main)

    @app.after_request
    def add_security_headers(response):
        return apply_security_headers(response)

    @app.errorhandler(404)
    def not_found(error):
        return render_template("error_404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        reference = datetime.now().strftime("%Y%m%d-%H%M%S")
        app.logger.exception(
            "Unhandled server error reference=%s",
            reference,
            exc_info=error,
        )
        return render_template(
            "error_500.html",
            error_reference=reference,
        ), 500

    with app.app_context():
        # Protect the live data before startup schema work.
        try:
            create_daily_backup_if_due(app, db)
        except Exception:
            app.logger.exception("Automatic startup backup failed")

        db.create_all()

        # Every schema change from this point is explicitly versioned. The
        # first migration records the old compatibility helper as our baseline.
        pending_before = None
        try:
            # If a database already exists, make an extra migration backup only
            # when startup actually has pending migrations.
            from app.services.migration_service import (
                applied_versions,
                MIGRATIONS,
            )
            done = applied_versions(db)
            pending_before = [
                version
                for version, _ in MIGRATIONS
                if version not in done
            ]
            if pending_before:
                create_database_backup(app, db, reason="pre-migration")

            applied = run_pending_migrations(
                db,
                ensure_starter_schema_updates,
            )
            if applied:
                app.logger.info(
                    "Applied database migrations: %s",
                    ", ".join(applied),
                )
        except Exception:
            app.logger.exception("Database migration failed")
            raise

        seed_default_areas()
        seed_buffet_options()
        seed_extra_dishes()
        seed_floor_plan_settings()
        seed_default_admin()
        seed_allergen_test_menu()
        seed_rota_finish_settings()
        seed_rota_shift_templates()
        seed_initial_staff_profiles()

    app.logger.info("Rocket Pub Server started")
    return app


def add_column_if_missing(inspector, table_name, column_name, sql_type):
    """Small development-only compatibility helper for the existing SQLite DB."""
    if table_name not in inspector.get_table_names():
        return

    columns = {c["name"] for c in inspector.get_columns(table_name)}

    if column_name not in columns:
        db.session.execute(
            text(
                f"ALTER TABLE {table_name} "
                f"ADD COLUMN {column_name} {sql_type}"
            )
        )


def ensure_starter_schema_updates():
    """
    Keep early test databases compatible while the schema is still changing.

    Once the design settles we will replace this with normal Flask-Migrate
    migration files.
    """
    inspector = inspect(db.engine)

    add_column_if_missing(
        inspector, "pub_table", "has_bench", "BOOLEAN DEFAULT 0"
    )
    add_column_if_missing(
        inspector, "pub_table", "unsuitable_for_food", "BOOLEAN DEFAULT 0"
    )

    pub_table_layout_additions = {
        "layout_width": "FLOAT DEFAULT 90",
        "layout_height": "FLOAT DEFAULT 60",
        "layout_shape": "VARCHAR(20) DEFAULT 'rectangle'",
        "layout_rotation": "FLOAT DEFAULT 0",
    }

    for name, sql_type in pub_table_layout_additions.items():
        add_column_if_missing(inspector, "pub_table", name, sql_type)

    add_column_if_missing(
        inspector, "customer", "avoids_bench", "BOOLEAN DEFAULT 0"
    )

    booking_additions = {
        "avoids_bench": "BOOLEAN DEFAULT 0",
        "preferred_table_id": "INTEGER",
        "number_of_children": "INTEGER DEFAULT 0",
        "deposit_required_amount": "FLOAT DEFAULT 0",
        "deposit_paid_amount": "FLOAT DEFAULT 0",
        "is_eating_food": "BOOLEAN DEFAULT 1",
        "high_chairs_required": "INTEGER DEFAULT 0",
        "repeat_booking_id": "INTEGER",
        "completed_at": "DATETIME",
    }

    for name, sql_type in booking_additions.items():
        add_column_if_missing(inspector, "booking", name, sql_type)

    add_column_if_missing(
        inspector, "repeat_booking", "high_chairs_required", "INTEGER DEFAULT 0"
    )

    app_user_additions = {
        "email": "VARCHAR(255)",
        "pending_email": "VARCHAR(255)",
        "email_verified": "BOOLEAN DEFAULT 0",
        "email_verification_code_hash": "VARCHAR(255)",
        "email_verification_expires_at": "DATETIME",
        "password_reset_code_hash": "VARCHAR(255)",
        "password_reset_expires_at": "DATETIME",
    }

    for name, sql_type in app_user_additions.items():
        add_column_if_missing(inspector, "app_user", name, sql_type)


    rota_profile_additions = {
        "sort_order": "INTEGER DEFAULT 100",
        "preferred_shifts": "VARCHAR(250)",
    }

    for name, sql_type in rota_profile_additions.items():
        add_column_if_missing(
            inspector,
            "staff_profile",
            name,
            sql_type,
        )

    add_column_if_missing(
        inspector,
        "staff_diary_entry",
        "request_group_id",
        "VARCHAR(36)",
    )

    allergen_item_additions = {
        "milk_status": "VARCHAR(20) DEFAULT 'free'",
        "nuts_status": "VARCHAR(20) DEFAULT 'free'",
        "egg_status": "VARCHAR(20) DEFAULT 'free'",
        "gluten_status": "VARCHAR(20) DEFAULT 'free'",
        "can_make_gluten_free": "BOOLEAN DEFAULT 0",
        "gluten_free_changes": "VARCHAR(300)",
    }

    for name, sql_type in allergen_item_additions.items():
        add_column_if_missing(
            inspector,
            "allergen_menu_item",
            name,
            sql_type,
        )

    # Carry existing v6.4 boolean test data into the new tri-state fields.
    if "allergen_menu_item" in inspector.get_table_names():
        for status_col, legacy_col in [
            ("milk_status", "contains_milk"),
            ("nuts_status", "contains_nuts"),
            ("egg_status", "contains_egg"),
            ("gluten_status", "contains_gluten"),
        ]:
            db.session.execute(
                text(
                    f"UPDATE allergen_menu_item "
                    f"SET {status_col} = 'contains' "
                    f"WHERE {legacy_col} = 1 "
                    f"AND ({status_col} IS NULL OR {status_col} = 'free')"
                )
            )

    add_column_if_missing(
        inspector,
        "inquiry_reminder",
        "reminder_kind",
        "VARCHAR(30) DEFAULT 'manual'"
    )

    menu_additions = {
        "option_number": "INTEGER",
        "items_text": "TEXT",
    }

    large_party_additions = {
        "deposit_payment_method": "VARCHAR(20)",
        "deposit_taken_by": "VARCHAR(120)",
        "expected_end_time": "TIME",
        "reserve_for_rest_of_day": "BOOLEAN DEFAULT 0",
        "high_chairs_required": "INTEGER DEFAULT 0",
        "deposit_due_date": "DATE",
        "deposit_paid_date": "DATE",
    }

    for name, sql_type in large_party_additions.items():
        add_column_if_missing(
            inspector, "large_party_inquiry", name, sql_type
        )

    for name, sql_type in menu_additions.items():
        add_column_if_missing(
            inspector, "large_party_menu_option", name, sql_type
        )

    db.session.commit()


def seed_default_areas():
    from app.models import Area

    for area_name in ["Restaurant", "Bar", "Snug / Cubby", "Pool Room"]:
        exists = db.session.scalar(
            db.select(Area).where(Area.name == area_name)
        )

        if not exists:
            db.session.add(Area(name=area_name))

    db.session.commit()


def seed_buffet_options():
    """Load the four packages from the supplied Rocket Pub buffet sheet."""
    from app.models import LargePartyMenuOption

    packages = [
        {
            "number": 1,
            "name": "The Basics",
            "price": 8.95,
            "items": [
                "Assorted Sandwiches & Wraps",
                "Pork Pies",
                "Sausage Rolls",
                "Tuna Pasta",
                "Coleslaw",
                "Salad Bowl",
                "Chips",
            ],
        },
        {
            "number": 2,
            "name": "The Classic",
            "price": 9.95,
            "items": [
                "Assorted Sandwiches & Wraps",
                "Chicken Wings",
                "Pork Pies",
                "Sausage Rolls",
                "Coleslaw",
                "Salad Bowl",
                "Chips",
                "Tuna Pasta",
            ],
        },
        {
            "number": 3,
            "name": "The Upgraded",
            "price": 10.95,
            "items": [
                "Assorted Sandwiches & Wraps",
                "Southern Fried Chicken Strips",
                "Fish Goujons",
                "Chicken & Bacon BBQ Parcels",
                "Coleslaw",
                "Salad Bowl",
                "Chips",
            ],
        },
        {
            "number": 4,
            "name": "The Full Works",
            "price": 12.95,
            "items": [
                "Chinese Chicken Curry",
                "Rice & Chips",
                "Duck Spring Rolls",
                "Salt & Pepper Chicken Wings",
                "Sui Mais",
                "Sweet & Sour Chicken",
                "Prawn Crackers",
                "Sauces and Dips",
            ],
        },
    ]

    for package in packages:
        option = db.session.scalar(
            db.select(LargePartyMenuOption).where(
                LargePartyMenuOption.option_number == package["number"]
            )
        )

        if option is None:
            # Upgrade an old "Option N" starter row if one exists.
            option = db.session.scalar(
                db.select(LargePartyMenuOption).where(
                    LargePartyMenuOption.name == f"Option {package['number']}"
                )
            )

        if option is None:
            option = LargePartyMenuOption()
            db.session.add(option)

        option.option_number = package["number"]
        option.name = package["name"]
        option.price_per_head = package["price"]
        option.items_text = "\n".join(package["items"])
        option.active = True

    db.session.commit()


def seed_extra_dishes():
    """Load the standard £6.50/head hot-dish list from the supplied sheet."""
    from app.models import ExtraDishOption

    names = [
        "Sweet & Sour Chicken",
        "Chicken Tikka Masala",
        "Lasagne",
        "Spaghetti Bolognese",
        "Chilli con Carne",
        "Chinese Chicken Curry",
    ]

    for name in names:
        option = db.session.scalar(
            db.select(ExtraDishOption).where(ExtraDishOption.name == name)
        )

        if option is None:
            option = ExtraDishOption(name=name)
            db.session.add(option)

        option.default_price_per_head = 6.50
        option.minimum_people = 25
        option.active = True

    db.session.commit()



def seed_floor_plan_settings():
    """Create the single main floor-plan settings row on first launch."""
    from app.models import FloorPlanSetting

    settings = db.session.scalar(
        db.select(FloorPlanSetting).where(FloorPlanSetting.name == "main")
    )

    if settings is None:
        db.session.add(
            FloorPlanSetting(
                name="main",
                canvas_width=1200,
                canvas_height=760,
                background_note="Main pub floor",
            )
        )
        db.session.commit()



def seed_default_admin():
    """
    Create the first administrator on a new database.

    Initial credentials:
      username: admin
      password: Password

    The account is forced through Change Password immediately after first login.
    """
    from werkzeug.security import generate_password_hash
    from app.models import AppUser

    existing_admin = db.session.scalar(
        db.select(AppUser).where(AppUser.role == "admin")
    )

    if existing_admin is not None:
        return

    db.session.add(
        AppUser(
            username="admin",
            password_hash=generate_password_hash("Password"),
            role="admin",
            must_change_password=True,
            active=True,
        )
    )
    db.session.commit()



def seed_allergen_test_menu():
    """
    Small temporary menu for testing the allergen search, colour states and
    side-suggestion workflow. Replace with verified pub data later.
    """
    from app.models import AllergenMealSide, AllergenMenuItem

    if db.session.scalar(db.select(AllergenMenuItem.id).limit(1)):
        return

    rows = [
        AllergenMenuItem(
            name="Cheese Burger",
            category="Main Meals",
            description="Beef burger with cheese in a bun.",
            ingredients="Beef burger, burger bun, cheddar cheese, lettuce, sauce",
            milk_status="contains",
            nuts_status="free",
            egg_status="may_contain",
            gluten_status="contains",
        ),
        AllergenMenuItem(
            name="Chicken Curry",
            category="Main Meals",
            description="Chicken curry with a choice of chips or rice.",
            ingredients="Chicken, curry sauce",
            milk_status="may_contain",
            nuts_status="free",
            egg_status="free",
            gluten_status="may_contain",
        ),
        AllergenMenuItem(
            name="Vegetable Curry",
            category="Main Meals",
            description="Mixed vegetable curry with a choice of chips or rice.",
            ingredients="Mixed vegetables, curry sauce",
            milk_status="free",
            nuts_status="free",
            egg_status="free",
            gluten_status="may_contain",
            vegetarian=True,
        ),
        AllergenMenuItem(
            name="Garlic Mushrooms",
            category="Starters",
            description="Breaded garlic mushrooms.",
            ingredients="Mushrooms, breadcrumb coating, garlic dressing",
            milk_status="may_contain",
            nuts_status="free",
            egg_status="may_contain",
            gluten_status="contains",
            vegetarian=True,
        ),
        AllergenMenuItem(
            name="Kids Chicken Nuggets",
            category="Kids Meals",
            description="Chicken nuggets with a choice of side.",
            ingredients="Chicken nuggets",
            milk_status="free",
            nuts_status="free",
            egg_status="may_contain",
            gluten_status="contains",
        ),
        AllergenMenuItem(
            name="Chocolate Brownie",
            category="Desserts",
            description="Chocolate brownie dessert.",
            ingredients="Chocolate, flour, butter, egg, sugar",
            milk_status="contains",
            nuts_status="may_contain",
            egg_status="contains",
            gluten_status="contains",
            vegetarian=True,
        ),
        AllergenMenuItem(
            name="Chips",
            category="Sides",
            description="Portion of chips.",
            ingredients="Potato, cooking oil",
            milk_status="free",
            nuts_status="free",
            egg_status="free",
            gluten_status="may_contain",
            vegetarian=True,
        ),
        AllergenMenuItem(
            name="Rice",
            category="Sides",
            description="Plain cooked rice.",
            ingredients="Rice",
            milk_status="free",
            nuts_status="free",
            egg_status="free",
            gluten_status="free",
            vegetarian=True,
        ),
        AllergenMenuItem(
            name="Side Salad",
            category="Sides",
            description="Mixed side salad.",
            ingredients="Lettuce, tomato, cucumber",
            milk_status="free",
            nuts_status="free",
            egg_status="free",
            gluten_status="free",
            vegetarian=True,
        ),
    ]

    db.session.add_all(rows)
    db.session.flush()

    by_name = {row.name: row for row in rows}

    for meal_name, side_names in {
        "Cheese Burger": ["Chips", "Side Salad"],
        "Chicken Curry": ["Chips", "Rice"],
        "Vegetable Curry": ["Chips", "Rice"],
        "Kids Chicken Nuggets": ["Chips", "Rice"],
    }.items():
        for side_name in side_names:
            db.session.add(
                AllergenMealSide(
                    meal_id=by_name[meal_name].id,
                    side_id=by_name[side_name].id,
                )
            )

    db.session.commit()



def seed_rota_finish_settings():
    """Estimated Finish times used only for projected weekly hours."""
    from datetime import time
    from app.models import RotaFinishSetting

    # Monday=0 ... Sunday=6.
    defaults = {
        0: time(22, 0),   # Monday
        1: time(23, 0),   # Tuesday
        2: time(22, 0),   # Wednesday
        3: time(23, 0),   # Thursday
        4: time(0, 0),    # Friday -> midnight
        5: time(0, 0),    # Saturday -> midnight
        6: time(22, 30),  # Sunday -> midpoint of 10-11pm
    }

    for weekday, finish_time in defaults.items():
        row = db.session.scalar(
            db.select(RotaFinishSetting).where(
                RotaFinishSetting.weekday == weekday
            )
        )
        if row is None:
            db.session.add(
                RotaFinishSetting(
                    weekday=weekday,
                    estimated_finish=finish_time,
                )
            )

    db.session.commit()


def seed_rota_shift_templates():
    """
    Initial shift slots inferred from the supplied historical rotas.

    Managers can edit these in Rota Settings. They are suggestions only and
    Auto-fill never publishes the rota automatically.
    """
    from datetime import time
    from app.models import RotaShiftTemplate

    if db.session.scalar(db.select(RotaShiftTemplate.id).limit(1)):
        return

    # weekday, start, end, finish?, role, qty
    rows = [
        # Monday
        (0, time(12,0), time(15,0), False, "front_of_house", 1),
        (0, time(17,0), None, True, "front_of_house", 1),

        # Tuesday
        (1, time(12,0), time(20,0), False, "front_of_house", 1),
        (1, time(17,0), None, True, "front_of_house", 1),

        # Wednesday
        (2, time(12,0), time(15,0), False, "front_of_house", 1),
        (2, time(17,0), None, True, "front_of_house", 1),

        # Thursday
        (3, time(12,0), time(16,0), False, "front_of_house", 1),
        (3, time(17,0), None, True, "front_of_house", 1),

        # Friday
        (4, time(12,0), time(16,0), False, "front_of_house", 1),
        (4, time(16,0), time(20,0), False, "front_of_house", 1),
        (4, time(17,0), time(21,0), False, "front_of_house", 1),
        (4, time(18,0), None, True, "front_of_house", 1),

        # Saturday
        (5, time(12,0), time(18,0), False, "front_of_house", 1),
        (5, time(15,0), time(20,0), False, "front_of_house", 1),
        (5, time(17,0), time(21,0), False, "front_of_house", 1),
        (5, time(18,0), None, True, "front_of_house", 1),

        # Sunday
        (6, time(12,0), time(18,0), False, "front_of_house", 2),
        (6, time(15,0), time(20,0), False, "front_of_house", 1),
        (6, time(17,0), None, True, "front_of_house", 1),
    ]

    for weekday, start, end, is_finish, role, qty in rows:
        db.session.add(
            RotaShiftTemplate(
                weekday=weekday,
                start_time=start,
                end_time=end,
                end_is_finish=is_finish,
                role=role,
                quantity=qty,
            )
        )

    db.session.commit()


def seed_initial_staff_profiles():
    """
    Create the known rota people only if they do not already exist.

    Existing profiles are NEVER forced active or archived here. Once a manager
    adds/restores Hannah, Charl, Leoni, Erin, or anybody else, that choice
    persists until a manager explicitly archives them again.
    """
    from app.models import AppUser, StaffProfile

    staff_rows = [
        ("Gemma", 10, True),
        ("Brooke", 20, True),
        ("Niamh", 30, True),
        ("Lois", 40, True),
        ("Jenna", 50, True),
        ("Maggie", 60, True),
        ("Alara", 70, True),
        ("Scott", 80, True),
        ("Kieran", 90, True),

        # These are archived only on the very first creation.
        ("Hannah", 200, False),
        ("Charlotte", 210, False),
        ("Leoni", 220, False),
        ("Erin", 230, False),
        ("Matt", 240, False),
    ]

    for name, order, initial_active in staff_rows:
        profile = db.session.scalar(
            db.select(StaffProfile).where(
                db.func.lower(StaffProfile.display_name) == name.lower()
            )
        )

        user = db.session.scalar(
            db.select(AppUser).where(
                db.func.lower(AppUser.username) == name.lower()
            )
        )

        if profile is None:
            profile = StaffProfile(
                display_name=name,
                user_id=user.id if user else None,
                sort_order=order,
                active=initial_active,
            )
            db.session.add(profile)
            db.session.flush()
        else:
            # Sort order can be refreshed, but the active/archive state is
            # manager-controlled and must never be overwritten here.
            profile.sort_order = order

            if profile.user_id is None and user is not None:
                profile.user_id = user.id

            if user is not None:
                profile.display_name = user.username

    db.session.commit()
