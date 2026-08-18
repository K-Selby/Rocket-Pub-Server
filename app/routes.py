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
from sqlalchemy import Integer, cast

from app import db
from app.models import Area, Booking, BookingTable, Customer, PubTable, TablePairing

main = Blueprint("main", __name__)

STANDARD_BOOKING_DURATION = 180
EARLIEST_BOOKING = "12:15"
LATEST_BOOKING = "19:30"


def normalise_phone(phone):
    """
    Convert common UK phone formats into one consistent stored value.

    07700 123456 -> 07700123456
    +44 7700 ... -> 07700...
    """
    cleaned = re.sub(r"\D", "", phone or "")

    if cleaned.startswith("44") and len(cleaned) >= 12:
        cleaned = "0" + cleaned[2:]

    return cleaned


def table_order_clause():
    """
    Sort ordinary numeric table numbers numerically rather than alphabetically.

    Without this, text sorting gives 1, 10, 11, 2, 3...
    """
    return (cast(PubTable.number, Integer), PubTable.number)


def generate_booking_times():
    """Generate every 15-minute booking time from 12:15 through 19:30."""
    start = datetime.strptime(EARLIEST_BOOKING, "%H:%M")
    end = datetime.strptime(LATEST_BOOKING, "%H:%M")

    times = []
    current = start

    while current <= end:
        times.append(current.strftime("%H:%M"))
        current += timedelta(minutes=15)

    return times


def booking_datetime_range(booking):
    """Return start/end datetime values for an existing booking."""
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

        if requested_start < existing_end and requested_end > existing_start:
            return False

    return True


def score_candidate(tables, party_size, preferred_area_id, preferred_table_id,
                    wants_near_tv, avoids_bench):
    """
    Score one table or a valid paired-table combination.

    Higher is better. Hard preferences such as avoiding benches are filtered
    before scoring; softer preferences influence the score.
    """
    capacity = sum(table.capacity for table in tables)

    if capacity < party_size:
        return None

    if avoids_bench and any(table.has_bench for table in tables):
        return None

    score = 100

    # Avoid wasting seats where possible.
    score -= (capacity - party_size) * 5

    # Prefer one table over pushing two together if both solve the problem.
    score -= (len(tables) - 1) * 8

    if preferred_area_id:
        if all(table.area_id == preferred_area_id for table in tables):
            score += 25
        elif any(table.area_id == preferred_area_id for table in tables):
            score += 10

    if preferred_table_id and any(
        table.id == preferred_table_id for table in tables
    ):
        score += 35

    if wants_near_tv and any(table.near_tv for table in tables):
        score += 15

    return score


def suggest_tables(party_size, date_value, time_value, duration_minutes,
                   preferred_area_id=None, preferred_table_id=None,
                   wants_near_tv=False, avoids_bench=False):
    """
    Return the best available allocation.

    It checks:
    1. suitable single tables
    2. table pairs explicitly configured as physically pushable together
    """
    tables = db.session.scalars(
        db.select(PubTable)
        .where(PubTable.active.is_(True))
        .order_by(*table_order_clause())
    ).all()

    candidates = []

    # Single-table candidates.
    for table in tables:
        if not table_is_available(
            table.id, date_value, time_value, duration_minutes
        ):
            continue

        score = score_candidate(
            [table],
            party_size,
            preferred_area_id,
            preferred_table_id,
            wants_near_tv,
            avoids_bench,
        )

        if score is not None:
            candidates.append((score, [table]))

    # Valid paired-table candidates.
    pairings = db.session.scalars(db.select(TablePairing)).all()

    for pairing in pairings:
        pair = [pairing.table_a, pairing.table_b]

        if not all(table.active for table in pair):
            continue

        if not all(
            table_is_available(
                table.id, date_value, time_value, duration_minutes
            )
            for table in pair
        ):
            continue

        score = score_candidate(
            pair,
            party_size,
            preferred_area_id,
            preferred_table_id,
            wants_near_tv,
            avoids_bench,
        )

        if score is not None:
            candidates.append((score, pair))

    if not candidates:
        return []

    candidates.sort(
        key=lambda item: (
            -item[0],
            len(item[1]),
            sum(table.capacity for table in item[1]),
        )
    )

    return candidates[0][1]


def validate_booking_time(booking_time):
    """Ensure submitted times stay inside the pub's booking window."""
    earliest = datetime.strptime(EARLIEST_BOOKING, "%H:%M").time()
    latest = datetime.strptime(LATEST_BOOKING, "%H:%M").time()
    return earliest <= booking_time <= latest


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


# -------------------------
# Tables
# -------------------------

@main.route("/tables")
def tables():
    table_list = db.session.scalars(
        db.select(PubTable).order_by(*table_order_clause())
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
            has_bench=request.form.get("has_bench") == "on",
            accessible=request.form.get("accessible") == "on",
        )

        db.session.add(table)
        db.session.commit()

        flash(f"Table {number} added.", "success")
        return redirect(url_for("main.tables"))

    return render_template("table_form.html", areas=areas, table=None)


@main.route("/tables/<int:table_id>/edit", methods=["GET", "POST"])
def edit_table(table_id):
    """Edit a table after it has already been created."""
    table = db.get_or_404(PubTable, table_id)
    areas = db.session.scalars(db.select(Area).order_by(Area.name)).all()

    if request.method == "POST":
        number = request.form.get("number", "").strip()
        capacity = request.form.get("capacity", type=int)
        area_id = request.form.get("area_id", type=int)

        if not number or not capacity or not area_id:
            flash("Table number, capacity and area are required.", "error")
            return redirect(url_for("main.edit_table", table_id=table.id))

        duplicate = db.session.scalar(
            db.select(PubTable).where(
                PubTable.number == number,
                PubTable.id != table.id,
            )
        )

        if duplicate:
            flash("Another table already uses that number.", "error")
            return redirect(url_for("main.edit_table", table_id=table.id))

        table.number = number
        table.capacity = capacity
        table.area_id = area_id
        table.near_tv = request.form.get("near_tv") == "on"
        table.has_bench = request.form.get("has_bench") == "on"
        table.accessible = request.form.get("accessible") == "on"
        table.active = request.form.get("active") == "on"

        db.session.commit()

        flash(f"Table {table.number} updated.", "success")
        return redirect(url_for("main.tables"))

    return render_template("table_form.html", areas=areas, table=table)


@main.route("/tables/pair", methods=["POST"])
def pair_tables():
    table_a_id = request.form.get("table_a_id", type=int)
    table_b_id = request.form.get("table_b_id", type=int)

    if not table_a_id or not table_b_id or table_a_id == table_b_id:
        flash("Choose two different tables.", "error")
        return redirect(url_for("main.tables"))

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
    areas = db.session.scalars(db.select(Area).order_by(Area.name)).all()

    all_tables = db.session.scalars(
        db.select(PubTable)
        .where(PubTable.active.is_(True))
        .order_by(*table_order_clause())
    ).all()

    customers = db.session.scalars(
        db.select(Customer).order_by(Customer.name)
    ).all()

    if request.method == "POST":
        customer_name = request.form.get("customer_name", "").strip()
        customer_phone = normalise_phone(request.form.get("customer_phone", ""))
        party_size = request.form.get("party_size", type=int)

        if not customer_name or not customer_phone or not party_size:
            flash("Customer name, phone number and party size are required.", "error")
            return redirect(url_for("main.new_booking"))

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

        if not validate_booking_time(booking_time):
            flash(
                "Bookings must be between 12:15 and 19:30.",
                "error"
            )
            return redirect(url_for("main.new_booking"))

        preferred_area_id = request.form.get("preferred_area_id", type=int)
        preferred_table_id = request.form.get("preferred_table_id", type=int)
        wants_near_tv = request.form.get("wants_near_tv") == "on"
        avoids_bench = request.form.get("avoids_bench") == "on"
        selected_table_ids = request.form.getlist("table_ids", type=int)

        # Reuse an existing customer if their phone number already exists.
        customer = db.session.scalar(
            db.select(Customer).where(Customer.phone == customer_phone)
        )

        if customer is None:
            customer = Customer(
                name=customer_name,
                phone=customer_phone,
            )
            db.session.add(customer)
            db.session.flush()
        else:
            # Keep the latest spelling/name entered by staff.
            customer.name = customer_name

        # The latest booking preferences become the saved recurring defaults.
        customer.preferred_area_id = preferred_area_id
        customer.preferred_table_id = preferred_table_id
        customer.prefers_near_tv = wants_near_tv
        customer.avoids_bench = avoids_bench

        if not selected_table_ids:
            suggested = suggest_tables(
                party_size,
                booking_date,
                booking_time,
                STANDARD_BOOKING_DURATION,
                preferred_area_id,
                preferred_table_id,
                wants_near_tv,
                avoids_bench,
            )
            selected_table_ids = [table.id for table in suggested]

        if not selected_table_ids:
            flash(
                "No suitable table is currently available. "
                "Try a different time or manually review the tables.",
                "error",
            )
            return redirect(url_for("main.new_booking"))

        selected_tables = db.session.scalars(
            db.select(PubTable)
            .where(PubTable.id.in_(selected_table_ids))
            .order_by(*table_order_clause())
        ).all()

        for table in selected_tables:
            if not table_is_available(
                table.id,
                booking_date,
                booking_time,
                STANDARD_BOOKING_DURATION,
            ):
                flash(
                    f"Table {table.number} overlaps another booking.",
                    "error"
                )
                return redirect(url_for("main.new_booking"))

        total_capacity = sum(table.capacity for table in selected_tables)

        if total_capacity < party_size:
            flash(
                f"Selected tables only hold {total_capacity} people.",
                "error"
            )
            return redirect(url_for("main.new_booking"))

        # If exactly two tables were selected manually, make sure that pairing
        # is one we have explicitly configured as physically possible.
        if len(selected_tables) == 2:
            first, second = sorted(table.id for table in selected_tables)
            valid_pair = db.session.scalar(
                db.select(TablePairing).where(
                    TablePairing.table_a_id == first,
                    TablePairing.table_b_id == second,
                )
            )

            if not valid_pair:
                flash(
                    "Those two tables are not configured as a valid pairing.",
                    "error"
                )
                return redirect(url_for("main.new_booking"))

        if len(selected_tables) > 2:
            flash(
                "The starter currently supports a maximum of two paired tables.",
                "error"
            )
            return redirect(url_for("main.new_booking"))

        booking = Booking(
            customer_id=customer.id,
            booking_date=booking_date,
            booking_time=booking_time,
            duration_minutes=STANDARD_BOOKING_DURATION,
            party_size=party_size,
            occasion=request.form.get("occasion", "").strip() or None,
            preferred_area_id=preferred_area_id,
            preferred_table_id=preferred_table_id,
            wants_near_tv=wants_near_tv,
            avoids_bench=avoids_bench,
            notes=request.form.get("notes", "").strip() or None,
        )

        db.session.add(booking)
        db.session.flush()

        for table in selected_tables:
            db.session.add(
                BookingTable(booking_id=booking.id, table_id=table.id)
            )

        db.session.commit()

        flash("Booking created.", "success")
        return redirect(
            url_for("main.bookings", date=booking_date.isoformat())
        )

    # Send customer details to JavaScript so entering a known name/phone can
    # refill saved preferences without a separate "create customer" step.
    customer_lookup = [
        {
            "name": customer.name,
            "phone": customer.phone,
            "preferred_area_id": customer.preferred_area_id,
            "preferred_table_id": customer.preferred_table_id,
            "prefers_near_tv": bool(customer.prefers_near_tv),
            "avoids_bench": bool(customer.avoids_bench),
        }
        for customer in customers
    ]

    return render_template(
        "booking_form.html",
        areas=areas,
        tables=all_tables,
        customer_lookup=customer_lookup,
        booking_times=generate_booking_times(),
        today=datetime.now().date(),
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
