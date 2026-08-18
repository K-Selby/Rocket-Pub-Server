from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import inspect, text

db = SQLAlchemy()
migrate = Migrate()


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__, instance_relative_config=True)

    # Development key only. Before the finished pub deployment we will move
    # secrets/configuration outside the source code.
    app.config["SECRET_KEY"] = "dev-change-this-later"
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///pub_booking.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    migrate.init_app(app, db)

    # Import models before creating tables so SQLAlchemy knows the schema.
    from app import models  # noqa: F401

    from app.routes import main
    app.register_blueprint(main)

    with app.app_context():
        db.create_all()

        # This tiny compatibility helper lets the updated starter run against
        # the database created by the previous version without forcing you to
        # delete all of your test data.
        ensure_starter_schema_updates()
        seed_default_areas()

    return app


def ensure_starter_schema_updates():
    """
    Add newly introduced starter columns to an existing SQLite database.

    Flask's db.create_all() creates missing tables but does not add columns to
    tables that already exist. Proper migrations will take over later; this is
    just convenient while the project is still in its first development stage.
    """
    inspector = inspect(db.engine)

    if "pub_table" in inspector.get_table_names():
        table_columns = {column["name"] for column in inspector.get_columns("pub_table")}
        if "has_bench" not in table_columns:
            db.session.execute(
                text("ALTER TABLE pub_table ADD COLUMN has_bench BOOLEAN DEFAULT 0")
            )

    if "customer" in inspector.get_table_names():
        customer_columns = {column["name"] for column in inspector.get_columns("customer")}
        if "avoids_bench" not in customer_columns:
            db.session.execute(
                text("ALTER TABLE customer ADD COLUMN avoids_bench BOOLEAN DEFAULT 0")
            )

    if "booking" in inspector.get_table_names():
        booking_columns = {column["name"] for column in inspector.get_columns("booking")}
        if "avoids_bench" not in booking_columns:
            db.session.execute(
                text("ALTER TABLE booking ADD COLUMN avoids_bench BOOLEAN DEFAULT 0")
            )
        if "preferred_table_id" not in booking_columns:
            db.session.execute(
                text("ALTER TABLE booking ADD COLUMN preferred_table_id INTEGER")
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
