from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()


def create_app():
    """Application factory used to create and configure the Flask app."""
    app = Flask(__name__, instance_relative_config=True)

    # Development key only. We can move this to an environment variable later.
    app.config["SECRET_KEY"] = "dev-change-this-later"

    # SQLite is ideal for our small local pub system.
    # Flask stores this database inside the instance folder.
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///pub_booking.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    migrate.init_app(app, db)

    # Import models before creating the database so SQLAlchemy knows about them.
    from app import models  # noqa: F401

    from app.routes import main
    app.register_blueprint(main)

    # Create database tables automatically for the starter build.
    # Later, Flask-Migrate will handle schema changes more formally.
    with app.app_context():
        db.create_all()
        seed_default_areas()

    return app


def seed_default_areas():
    """Add a few pub areas on first launch."""
    from app.models import Area

    default_areas = ["Restaurant", "Bar", "Snug / Cubby", "Pool Room"]

    for area_name in default_areas:
        exists = db.session.scalar(
            db.select(Area).where(Area.name == area_name)
        )
        if not exists:
            db.session.add(Area(name=area_name))

    db.session.commit()
