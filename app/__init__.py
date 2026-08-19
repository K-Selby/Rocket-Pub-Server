from flask import Flask
import os
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import inspect, text

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__, instance_relative_config=True)

    app.config["SECRET_KEY"] = os.environ.get("ROCKET_SECRET_KEY", "rocket-dev-change-this-later")
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
        seed_floor_plan_settings()
        seed_default_admin()
        seed_allergen_test_menu()

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


    allergen_item_additions = {
        "milk_status": "VARCHAR(20) DEFAULT 'free'",
        "nuts_status": "VARCHAR(20) DEFAULT 'free'",
        "egg_status": "VARCHAR(20) DEFAULT 'free'",
        "gluten_status": "VARCHAR(20) DEFAULT 'free'",
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
