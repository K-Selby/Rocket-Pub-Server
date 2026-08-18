from datetime import datetime, timedelta
import re

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from app import db
from app.models import Area, Booking, BookingTable, Customer, PubTable, TablePairing

main = Blueprint("main", __name__)


def normalise_phone(phone):
    """
    Convert common UK phone number formats into a consistent stored value.

    Examples:
    07700 123456  -> 07700123456
    +44 7700 ...  -> 07700...
    """
    cleaned = re.sub(r"\D", "", phone or "")

    if cleaned.startswith("44") and len(cleaned) >= 12:
        cleaned = "0" + cleaned[2:]

    return cleaned


def booking_datetime_range(booking):
    """Return start and end datetime values for an existing booking."""
    start = datetime.combine(booking.booking_date, booking.booking_time)
    end = start + timedelta(minutes=booking.duration_minutes)
    return start, end


def table_is_available(table_id, date_value, time_value, duration_minutes):
    """Check whether a table is free for the whole requested booking period."""
    requested_start = datetime.combine(date_value, time_value)
    requested_end = requested_start + timedelta(minutes=duration_minutes)

    existing_links = db.session.scalars(
        db.select(BookingTable)
        .join(Booking)
        .where(
            BookingTable.table_id == table_id,
            Booking.booking_date == date_value,
            Booking.status != "Cancelled",
        )
    ).all()

    for link in existing_links:
        existing_start, existing_end = booking_datetime_range(link.booking)

        # Standard interval-overlap test.
        if requested_start < existing_end and requested_end > existing_start:
            return False

    return True


def suggest_tables(party_size, date_value, time_value, duration_minutes,
                   preferred_area_id=None, wants_near_tv=False):
    """
    Basic first version of automatic allocation.

    Scoring priorities:
    - table must fit the party
    - smaller suitable tables are preferred over wasting a large table
    - preferred area adds a strong bonus
    - near-TV preference adds a bonus
    """
    available = []

    tables = db.session.scalars(
        db.select(PubTable)
        .where(PubTable.active.is_(True))
        .order_by(PubTable.capacity, PubTable.number)
    ).all()

    for table in tables:
        if table.capacity < party_size:
            continue

        if not table_is_available(
            table.id, date_value, time_value, duration_minutes
        ):
            continue

        score = 100

        # Penalise unused seats.
        score -= (table.capacity - party_size) * 5

        if preferred_area_id and table.area_id == preferred_area_id:
            score += 25

        if wants_near_tv and table.near_tv:
            score += 15

        available.append((score, table))

    available.sort(key=lambda item: (-item[0], item[1].capacity))
    return [table for _, table in available]


@main.route("/")
def dashboard():
    today = datetime.now().date()

    todays_bookings = db.session.scalars(
        db.select(Booking)
        .where(
            Booking.booking_date == today,
            Booking.status != "Cancelled"
        )
        .order_by(Booking.booking_time)
    ).all()

    return render_template(
        "dashboard.html",
        bookings=todays_bookings,
        today=today
    )


# -------------------------
# Customers
# -------------------------

@main.route("/customers")
def customers():
    search = request.args.get("q", "").strip()

    stmt = db.select(Customer).order_by(Customer.name)

    if search:
        normalised = normalise_phone(search)
        stmt = stmt.where(
            db.or_(
                Customer.name.ilike(f"%{search}%"),
                Customer.phone.ilike(f"%{normalised}%"),
            )
        )

    customer_list = db.session.scalars(stmt).all()

    return render_template(
        "customers.html",
        customers=customer_list,
        search=search
    )


@main.route("/customers/new", methods=["GET", "POST"])
def new_customer():
    areas = db.session.scalars(db.select(Area).order_by(Area.name)).all()
    tables = db.session.scalars(
        db.select(PubTable).where(PubTable.active.is_(True)).order_by(PubTable.number)
    ).all()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = normalise_phone(request.form.get("phone", ""))

        if not name or not phone:
            flash("Name and phone number are required.", "error")
            return redirect(url_for("main.new_customer"))

        existing = db.session.scalar(
            db.select(Customer).where(Customer.phone == phone)
        )

        if existing:
            flash("A customer with that phone number already exists.", "error")
            return redirect(url_for("main.customers", q=phone))

        customer = Customer(
            name=name,
            phone=phone,
            email=request.form.get("email", "").strip() or None,
            preferred_area_id=request.form.get("preferred_area_id", type=int),
            preferred_table_id=request.form.get("preferred_table_id", type=int),
            prefers_near_tv=request.form.get("prefers_near_tv") == "on",
            notes=request.form.get("notes", "").strip() or None,
        )

        db.session.add(customer)
        db.session.commit()

        flash("Customer added.", "success")
        return redirect(url_for("main.customers"))

    return render_template("customer_form.html", areas=areas, tables=tables)


# -------------------------
# Tables
# -------------------------

@main.route("/tables")
def tables():
    table_list = db.session.scalars(
        db.select(PubTable).order_by(PubTable.area_id, PubTable.number)
    ).all()

    pairings = db.session.scalars(db.select(TablePairing)).all()

    return render_template(
        "tables.html",
        tables=table_list,
        pairings=pairings
    )


@main.route("/tables/new", methods=["GET", "POST"])
def new_table():
    areas = db.session.scalars(db.select(Area).order_by(Area.name)).all()

    if request.method == "POST":
        number = request.form.get("number", "").strip()
        capacity = request.form.get("capacity", type=int)
        area_id = request.form.get("area_id", type=int)

        if not number or not capacity or not area_id:
            flash("Table number, capacity and area are required.", "error")
            return redirect(url_for("main.new_table"))

        existing = db.session.scalar(
            db.select(PubTable).where(PubTable.number == number)
        )

        if existing:
            flash("That table number already exists.", "error")
            return redirect(url_for("main.new_table"))

        table = PubTable(
            number=number,
            capacity=capacity,
            area_id=area_id,
            near_tv=request.form.get("near_tv") == "on",
            accessible=request.form.get("accessible") == "on",
            window_seat=request.form.get("window_seat") == "on",
        )

        db.session.add(table)
        db.session.commit()

        flash(f"Table {number} added.", "success")
        return redirect(url_for("main.tables"))

    return render_template("table_form.html", areas=areas)


@main.route("/tables/pair", methods=["POST"])
def pair_tables():
    table_a_id = request.form.get("table_a_id", type=int)
    table_b_id = request.form.get("table_b_id", type=int)

    if not table_a_id or not table_b_id or table_a_id == table_b_id:
        flash("Choose two different tables.", "error")
        return redirect(url_for("main.tables"))

    # Store pairings in consistent numerical order.
    first, second = sorted([table_a_id, table_b_id])

    existing = db.session.scalar(
        db.select(TablePairing).where(
            TablePairing.table_a_id == first,
            TablePairing.table_b_id == second,
        )
    )

    if existing:
        flash("Those tables are already paired.", "error")
        return redirect(url_for("main.tables"))

    db.session.add(TablePairing(table_a_id=first, table_b_id=second))
    db.session.commit()

    flash("Table pairing added.", "success")
    return redirect(url_for("main.tables"))


# -------------------------
# Bookings
# -------------------------

@main.route("/bookings")
def bookings():
    selected_date_text = request.args.get("date")

    if selected_date_text:
        try:
            selected_date = datetime.strptime(
                selected_date_text, "%Y-%m-%d"
            ).date()
        except ValueError:
            selected_date = datetime.now().date()
    else:
        selected_date = datetime.now().date()

    booking_list = db.session.scalars(
        db.select(Booking)
        .where(Booking.booking_date == selected_date)
        .order_by(Booking.booking_time)
    ).all()

    return render_template(
        "bookings.html",
        bookings=booking_list,
        selected_date=selected_date
    )


@main.route("/bookings/new", methods=["GET", "POST"])
def new_booking():
    customers = db.session.scalars(
        db.select(Customer).order_by(Customer.name)
    ).all()
    areas = db.session.scalars(db.select(Area).order_by(Area.name)).all()
    all_tables = db.session.scalars(
        db.select(PubTable)
        .where(PubTable.active.is_(True))
        .order_by(PubTable.number)
    ).all()

    if request.method == "POST":
        customer_id = request.form.get("customer_id", type=int)
        party_size = request.form.get("party_size", type=int)
        duration = request.form.get("duration_minutes", type=int) or 120

        try:
            booking_date = datetime.strptime(
                request.form["booking_date"], "%Y-%m-%d"
            ).date()
            booking_time = datetime.strptime(
                request.form["booking_time"], "%H:%M"
            ).time()
        except (ValueError, KeyError):
            flash("Please enter a valid booking date and time.", "error")
            return redirect(url_for("main.new_booking"))

        if not customer_id or not party_size:
            flash("Customer and party size are required.", "error")
            return redirect(url_for("main.new_booking"))

        preferred_area_id = request.form.get("preferred_area_id", type=int)
        wants_near_tv = request.form.get("wants_near_tv") == "on"
        selected_table_ids = request.form.getlist("table_ids", type=int)

        # If staff did not manually choose a table, make a basic suggestion.
        if not selected_table_ids:
            suggestions = suggest_tables(
                party_size,
                booking_date,
                booking_time,
                duration,
                preferred_area_id,
                wants_near_tv,
            )
            if suggestions:
                selected_table_ids = [suggestions[0].id]

        if not selected_table_ids:
            flash(
                "No suitable table is currently available. "
                "Try a different time or manually review the floor plan.",
                "error",
            )
            return redirect(url_for("main.new_booking"))

        # Check every manually/automatically selected table is free.
        for table_id in selected_table_ids:
            if not table_is_available(
                table_id, booking_date, booking_time, duration
            ):
                flash(
                    "One of the selected tables overlaps another booking.",
                    "error"
                )
                return redirect(url_for("main.new_booking"))

        # Make sure the combined capacity is enough.
        selected_tables = db.session.scalars(
            db.select(PubTable).where(PubTable.id.in_(selected_table_ids))
        ).all()

        total_capacity = sum(table.capacity for table in selected_tables)

        if total_capacity < party_size:
            flash(
                f"Selected tables only hold {total_capacity} people.",
                "error"
            )
            return redirect(url_for("main.new_booking"))

        booking = Booking(
            customer_id=customer_id,
            booking_date=booking_date,
            booking_time=booking_time,
            duration_minutes=duration,
            party_size=party_size,
            occasion=request.form.get("occasion", "").strip() or None,
            preferred_area_id=preferred_area_id,
            wants_near_tv=wants_near_tv,
            notes=request.form.get("notes", "").strip() or None,
        )

        db.session.add(booking)
        db.session.flush()

        for table_id in selected_table_ids:
            db.session.add(
                BookingTable(booking_id=booking.id, table_id=table_id)
            )

        db.session.commit()

        flash("Booking created.", "success")
        return redirect(
            url_for("main.bookings", date=booking_date.isoformat())
        )

    return render_template(
        "booking_form.html",
        customers=customers,
        areas=areas,
        tables=all_tables,
        today=datetime.now().date()
    )


@main.route("/bookings/<int:booking_id>/cancel", methods=["POST"])
def cancel_booking(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    booking.status = "Cancelled"
    db.session.commit()

    flash("Booking cancelled.", "success")
    return redirect(
        url_for("main.bookings", date=booking.booking_date.isoformat())
    )
