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
        seed_large_party_menu_options()

    return app


def ensure_starter_schema_updates():
    """
    Keep the early development database compatible with newer starter versions.

    Proper Flask-Migrate migrations can replace this helper once the schema
    settles down. For now it lets you keep existing test data between versions.
    """
    inspector = inspect(db.engine)
    table_names = inspector.get_table_names()

    if "pub_table" in table_names:
        columns = {c["name"] for c in inspector.get_columns("pub_table")}
        if "has_bench" not in columns:
            db.session.execute(
                text("ALTER TABLE pub_table ADD COLUMN has_bench BOOLEAN DEFAULT 0")
            )

    if "customer" in table_names:
        columns = {c["name"] for c in inspector.get_columns("customer")}
        if "avoids_bench" not in columns:
            db.session.execute(
                text("ALTER TABLE customer ADD COLUMN avoids_bench BOOLEAN DEFAULT 0")
            )

    if "booking" in table_names:
        columns = {c["name"] for c in inspector.get_columns("booking")}

        additions = {
            "avoids_bench": "BOOLEAN DEFAULT 0",
            "preferred_table_id": "INTEGER",
            "number_of_children": "INTEGER DEFAULT 0",
            "deposit_required_amount": "FLOAT DEFAULT 0",
            "deposit_paid_amount": "FLOAT DEFAULT 0",
        }

        for name, sql_type in additions.items():
            if name not in columns:
                db.session.execute(
                    text(f"ALTER TABLE booking ADD COLUMN {name} {sql_type}")
                )

    db.session.commit()


def seed_default_areas():
    """Add the pub's initial named areas on first launch."""
    from app.models import Area

    default_areas = ["Restaurant", "Bar", "Snug / Cubby", "Pool Room"]

    for area_name in default_areas:
        exists = db.session.scalar(
            db.select(Area).where(Area.name == area_name)
        )
        if not exists:
            db.session.add(Area(name=area_name))

    db.session.commit()


def seed_large_party_menu_options():
    """
    Create four configurable menu/buffet options.

    Prices are deliberately left blank because no actual pub prices have been
    supplied yet. They can be edited from the Large Party area.
    """
    from app.models import LargePartyMenuOption

    for option_number in range(1, 5):
        name = f"Option {option_number}"
        exists = db.session.scalar(
            db.select(LargePartyMenuOption).where(
                LargePartyMenuOption.name == name
            )
        )

        if not exists:
            db.session.add(
                LargePartyMenuOption(
                    name=name,
                    price_per_head=None,
                    active=True,
                )
            )

    db.session.commit()
