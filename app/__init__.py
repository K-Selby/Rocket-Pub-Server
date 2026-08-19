from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import inspect, text

db = SQLAlchemy()
migrate = Migrate()


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__, instance_relative_config=True)

    app.config["SECRET_KEY"] = "dev-change-this-later"
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///pub_booking.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    migrate.init_app(app, db)

    from app import models  # noqa: F401
    from app.routes import main
    app.register_blueprint(main)

    with app.app_context():
        db.create_all()
        ensure_starter_schema_updates()
        seed_default_areas()
        seed_buffet_options()
        seed_extra_dishes()

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
    }

    for name, sql_type in booking_additions.items():
        add_column_if_missing(inspector, "booking", name, sql_type)

    add_column_if_missing(
        inspector, "repeat_booking", "high_chairs_required", "INTEGER DEFAULT 0"
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
