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
from app.models import (
    Area,
    Booking,
    BookingTable,
    Customer,
    LargePartyInquiry,
    LargePartyMenuOption,
    PubTable,
    TablePairing,
)

main = Blueprint("main", __name__)

STANDARD_BOOKING_DURATION = 180
EARLIEST_BOOKING = "12:15"
LATEST_BOOKING = "19:30"
SUNDAY_LATEST_BOOKING = "19:00"


def normalise_phone(phone):
    """Normalise common UK phone formats for matching recurring customers."""
    cleaned = re.sub(r"\D", "", phone or "")

    if cleaned.startswith("44") and len(cleaned) >= 12:
        cleaned = "0" + cleaned[2:]

    return cleaned


def table_order_clause():
    """Sort table text like 1, 2, 3, 10 instead of 1, 10, 2, 3."""
    return (cast(PubTable.number, Integer), PubTable.number)


def calculate_deposit(party_size):
    """£5/head above 10 people, capped at £100."""
    if not party_size or party_size <= 10:
        return 0.0

    return float(min(party_size * 5, 100))


def latest_booking_time_for_date(date_value):
    """Sunday closes bookings earlier than the rest of the week."""
    if date_value.weekday() == 6:
        return datetime.strptime(SUNDAY_LATEST_BOOKING, "%H:%M").time()

    return datetime.strptime(LATEST_BOOKING, "%H:%M").time()


def validate_booking_time(date_value, booking_time):
    earliest = datetime.strptime(EARLIEST_BOOKING, "%H:%M").time()
    latest = latest_booking_time_for_date(date_value)
    return earliest <= booking_time <= latest


def booking_time_error_message(date_value):
    latest_text = "7:00pm" if date_value.weekday() == 6 else "7:30pm"
    return (
        "The earliest available booking time is 12:15pm and the latest "
        f"available time is {latest_text}."
    )


def booking_datetime_range(booking):
    start = datetime.combine(booking.booking_date, booking.booking_time)
    end = start + timedelta(minutes=booking.duration_minutes)
    return start, end


def table_is_available(
    table_id,
    date_value,
    time_value,
    duration_minutes,
    exclude_booking_id=None,
):
    """Check availability, optionally ignoring the booking currently being edited."""
    requested_start = datetime.combine(date_value, time_value)
    requested_end = requested_start + timedelta(minutes=duration_minutes)

    stmt = (
        db.select(BookingTable)
        .join(Booking)
        .where(
            BookingTable.table_id == table_id,
            Booking.booking_date == date_value,
            Booking.status != "Cancelled",
        )
    )

    if exclude_booking_id:
        stmt = stmt.where(Booking.id != exclude_booking_id)

    existing_links = db.session.scalars(stmt).all()

    for link in existing_links:
        existing_start, existing_end = booking_datetime_range(link.booking)

        if requested_start < existing_end and requested_end > existing_start:
            return False

    return True


def score_candidate(
    tables,
    party_size,
    preferred_area_id,
    preferred_table_id,
    wants_near_tv,
    avoids_bench,
):
    capacity = sum(table.capacity for table in tables)

    if capacity < party_size:
        return None

    if avoids_bench and any(table.has_bench for table in tables):
        return None

    score = 100
    score -= (capacity - party_size) * 5
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


def suggest_tables(
    party_size,
    date_value,
    time_value,
    duration_minutes,
    preferred_area_id=None,
    preferred_table_id=None,
    wants_near_tv=False,
    avoids_bench=False,
    exclude_booking_id=None,
):
    """Return the highest-scoring available table or configured table pair."""
    tables = db.session.scalars(
        db.select(PubTable)
        .where(PubTable.active.is_(True))
        .order_by(*table_order_clause())
    ).all()

    candidates = []

    for table in tables:
        if not table_is_available(
            table.id,
            date_value,
            time_value,
            duration_minutes,
            exclude_booking_id,
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

    pairings = db.session.scalars(db.select(TablePairing)).all()

    for pairing in pairings:
        pair = [pairing.table_a, pairing.table_b]

        if not all(table.active for table in pair):
            continue

        if not all(
            table_is_available(
                table.id,
                date_value,
                time_value,
                duration_minutes,
                exclude_booking_id,
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


def validate_selected_tables(
    selected_tables,
    party_size,
    booking_date,
    booking_time,
    exclude_booking_id=None,
):
    if not selected_tables:
        return "No table was selected or available."

    for table in selected_tables:
        if not table_is_available(
            table.id,
            booking_date,
            booking_time,
            STANDARD_BOOKING_DURATION,
            exclude_booking_id,
        ):
            return f"Table {table.number} overlaps another booking."

    total_capacity = sum(table.capacity for table in selected_tables)

    if total_capacity < party_size:
        return f"Selected tables only hold {total_capacity} people."

    if len(selected_tables) == 2:
        first, second = sorted(table.id for table in selected_tables)
        valid_pair = db.session.scalar(
            db.select(TablePairing).where(
                TablePairing.table_a_id == first,
                TablePairing.table_b_id == second,
            )
        )

        if not valid_pair:
            return "Those two tables are not configured as a valid pairing."

    if len(selected_tables) > 2:
        return "The current version supports a maximum of two paired tables."

    return None


def get_or_create_customer(name, phone):
    customer = db.session.scalar(
        db.select(Customer).where(Customer.phone == phone)
    )

    if customer is None:
        customer = Customer(name=name, phone=phone)
        db.session.add(customer)
        db.session.flush()
    else:
        customer.name = name

    return customer


def save_customer_preferences(
    customer,
    preferred_area_id,
    preferred_table_id,
    wants_near_tv,
    avoids_bench,
):
    customer.preferred_area_id = preferred_area_id
    customer.preferred_table_id = preferred_table_id
    customer.prefers_near_tv = wants_near_tv
    customer.avoids_bench = avoids_bench


def customer_lookup_payload():
    customers = db.session.scalars(
        db.select(Customer).order_by(Customer.name)
    ).all()

    return [
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


@main.route("/")
def dashboard():
    today = datetime.now().date()

    todays_bookings = db.session.scalars(
        db.select(Booking)
        .where(
            Booking.booking_date == today,
            Booking.status != "Cancelled",
        )
        .order_by(Booking.booking_time)
    ).all()

    return render_template(
        "dashboard.html",
        bookings=todays_bookings,
        today=today,
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

    return render_template(
        "customers.html",
        customers=db.session.scalars(stmt).all(),
        search=search,
    )


# -------------------------
# Tables
# -------------------------

@main.route("/tables")
def tables():
    return render_template(
        "tables.html",
        tables=db.session.scalars(
            db.select(PubTable).order_by(*table_order_clause())
        ).all(),
        pairings=db.session.scalars(db.select(TablePairing)).all(),
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

        if db.session.scalar(
            db.select(PubTable).where(PubTable.number == number)
        ):
            flash("That table number already exists.", "error")
            return redirect(url_for("main.new_table"))

        db.session.add(
            PubTable(
                number=number,
                capacity=capacity,
                area_id=area_id,
                near_tv=request.form.get("near_tv") == "on",
                has_bench=request.form.get("has_bench") == "on",
                accessible=request.form.get("accessible") == "on",
            )
        )
        db.session.commit()

        flash(f"Table {number} added.", "success")
        return redirect(url_for("main.tables"))

    return render_template("table_form.html", areas=areas, table=None)


@main.route("/tables/<int:table_id>/edit", methods=["GET", "POST"])
def edit_table(table_id):
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

    if db.session.scalar(
        db.select(TablePairing).where(
            TablePairing.table_a_id == first,
            TablePairing.table_b_id == second,
        )
    ):
        flash("Those tables are already paired.", "error")
        return redirect(url_for("main.tables"))

    db.session.add(TablePairing(table_a_id=first, table_b_id=second))
    db.session.commit()

    flash("Table pairing added.", "success")
    return redirect(url_for("main.tables"))


# -------------------------
# Normal bookings
# -------------------------

@main.route("/bookings")
def bookings():
    selected_date_text = request.args.get("date")

    try:
        selected_date = (
            datetime.strptime(selected_date_text, "%Y-%m-%d").date()
            if selected_date_text
            else datetime.now().date()
        )
    except ValueError:
        selected_date = datetime.now().date()

    booking_list = db.session.scalars(
        db.select(Booking)
        .where(Booking.booking_date == selected_date)
        .order_by(Booking.booking_time)
    ).all()

    return render_template(
        "bookings.html",
        bookings=booking_list,
        selected_date=selected_date,
    )


@main.route("/bookings/new", methods=["GET", "POST"])
def new_booking():
    return booking_form_handler()


@main.route("/bookings/<int:booking_id>/edit", methods=["GET", "POST"])
def edit_booking(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    return booking_form_handler(booking)


def booking_form_handler(booking=None):
    areas = db.session.scalars(db.select(Area).order_by(Area.name)).all()
    tables = db.session.scalars(
        db.select(PubTable)
        .where(PubTable.active.is_(True))
        .order_by(*table_order_clause())
    ).all()

    if request.method == "POST":
        customer_name = request.form.get("customer_name", "").strip()
        customer_phone = normalise_phone(request.form.get("customer_phone", ""))
        party_size = request.form.get("party_size", type=int)
        number_of_children = request.form.get("number_of_children", type=int) or 0

        if not customer_name or not customer_phone or not party_size:
            flash(
                "Customer name, phone number and party size are required.",
                "error",
            )
            return redirect(request.url)

        if number_of_children < 0 or number_of_children > party_size:
            flash(
                "Number of children cannot be greater than the total party size.",
                "error",
            )
            return redirect(request.url)

        try:
            booking_date = datetime.strptime(
                request.form["booking_date"], "%Y-%m-%d"
            ).date()
            booking_time = datetime.strptime(
                request.form["booking_time"], "%H:%M"
            ).time()
        except (ValueError, KeyError):
            flash("Please enter a valid booking date and time.", "error")
            return redirect(request.url)

        if not validate_booking_time(booking_date, booking_time):
            flash(booking_time_error_message(booking_date), "error")
            return redirect(request.url)

        preferred_area_id = request.form.get("preferred_area_id", type=int)
        preferred_table_id = request.form.get("preferred_table_id", type=int)
        wants_near_tv = request.form.get("wants_near_tv") == "on"
        avoids_bench = request.form.get("avoids_bench") == "on"

        selected_table_ids = request.form.getlist("table_ids", type=int)

        current_customer = get_or_create_customer(
            customer_name,
            customer_phone,
        )

        save_customer_preferences(
            current_customer,
            preferred_area_id,
            preferred_table_id,
            wants_near_tv,
            avoids_bench,
        )

        exclude_id = booking.id if booking else None

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
                exclude_booking_id=exclude_id,
            )
            selected_table_ids = [table.id for table in suggested]

        selected_tables = db.session.scalars(
            db.select(PubTable)
            .where(PubTable.id.in_(selected_table_ids))
            .order_by(*table_order_clause())
        ).all()

        table_error = validate_selected_tables(
            selected_tables,
            party_size,
            booking_date,
            booking_time,
            exclude_booking_id=exclude_id,
        )

        if table_error:
            flash(table_error, "error")
            return redirect(request.url)

        deposit_due = calculate_deposit(party_size)
        deposit_paid = request.form.get("deposit_paid_amount", type=float) or 0.0
        deposit_paid = max(0.0, min(deposit_paid, deposit_due))

        if booking is None:
            booking = Booking(customer_id=current_customer.id)
            db.session.add(booking)
        else:
            booking.customer_id = current_customer.id
            BookingTable.query.filter_by(booking_id=booking.id).delete()

        booking.booking_date = booking_date
        booking.booking_time = booking_time
        booking.duration_minutes = STANDARD_BOOKING_DURATION
        booking.party_size = party_size
        booking.number_of_children = number_of_children
        booking.occasion = request.form.get("occasion", "").strip() or None
        booking.preferred_area_id = preferred_area_id
        booking.preferred_table_id = preferred_table_id
        booking.wants_near_tv = wants_near_tv
        booking.avoids_bench = avoids_bench
        booking.deposit_required_amount = deposit_due
        booking.deposit_paid_amount = deposit_paid
        booking.notes = request.form.get("notes", "").strip() or None

        db.session.flush()

        for table in selected_tables:
            db.session.add(
                BookingTable(booking_id=booking.id, table_id=table.id)
            )

        db.session.commit()

        flash(
            "Booking updated." if exclude_id else "Booking created.",
            "success",
        )
        return redirect(
            url_for("main.bookings", date=booking_date.isoformat())
        )

    return render_template(
        "booking_form.html",
        areas=areas,
        tables=tables,
        customer_lookup=customer_lookup_payload(),
        today=datetime.now().date(),
        booking=booking,
        selected_table_ids=(
            [table.id for table in booking.tables] if booking else []
        ),
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


# -------------------------
# Large-party enquiries
# -------------------------

@main.route("/large-parties")
def large_parties():
    inquiries = db.session.scalars(
        db.select(LargePartyInquiry)
        .order_by(
            LargePartyInquiry.event_date.is_(None),
            LargePartyInquiry.event_date,
            LargePartyInquiry.created_at.desc(),
        )
    ).all()

    options = db.session.scalars(
        db.select(LargePartyMenuOption)
        .order_by(LargePartyMenuOption.id)
    ).all()

    return render_template(
        "large_parties.html",
        inquiries=inquiries,
        options=options,
    )


@main.route("/large-parties/new", methods=["GET", "POST"])
def new_large_party():
    return large_party_form_handler()


@main.route("/large-parties/<int:inquiry_id>/edit", methods=["GET", "POST"])
def edit_large_party(inquiry_id):
    inquiry = db.get_or_404(LargePartyInquiry, inquiry_id)
    return large_party_form_handler(inquiry)


def large_party_form_handler(inquiry=None):
    options = db.session.scalars(
        db.select(LargePartyMenuOption)
        .where(LargePartyMenuOption.active.is_(True))
        .order_by(LargePartyMenuOption.id)
    ).all()

    if request.method == "POST":
        customer_name = request.form.get("customer_name", "").strip()
        customer_phone = normalise_phone(request.form.get("customer_phone", ""))
        party_size = request.form.get("party_size", type=int)
        number_of_children = request.form.get("number_of_children", type=int) or 0

        if not customer_name or not customer_phone or not party_size:
            flash(
                "Name, phone number and estimated party size are required.",
                "error",
            )
            return redirect(request.url)

        if number_of_children < 0 or number_of_children > party_size:
            flash(
                "Number of children cannot be greater than the total party size.",
                "error",
            )
            return redirect(request.url)

        event_date = None
        event_time = None

        if request.form.get("event_date"):
            try:
                event_date = datetime.strptime(
                    request.form["event_date"],
                    "%Y-%m-%d",
                ).date()
            except ValueError:
                flash("Please enter a valid event date.", "error")
                return redirect(request.url)

        if request.form.get("event_time"):
            try:
                event_time = datetime.strptime(
                    request.form["event_time"],
                    "%H:%M",
                ).time()
            except ValueError:
                flash("Please enter a valid event time.", "error")
                return redirect(request.url)

        food_type = request.form.get("food_type", "").strip() or None
        menu_option_id = request.form.get("menu_option_id", type=int)
        catered_people = request.form.get("catered_people", type=int)

        if catered_people is not None:
            if catered_people < 0 or catered_people > party_size:
                flash(
                    "People being catered for cannot exceed the total party size.",
                    "error",
                )
                return redirect(request.url)

        selected_option = (
            db.session.get(LargePartyMenuOption, menu_option_id)
            if menu_option_id
            else None
        )

        # Save the current option price into the enquiry as a quote snapshot.
        price_per_head = (
            selected_option.price_per_head
            if selected_option and selected_option.price_per_head is not None
            else None
        )

        food_total = (
            round(price_per_head * catered_people, 2)
            if price_per_head is not None and catered_people is not None
            else None
        )

        deposit_due = calculate_deposit(party_size)
        deposit_paid = request.form.get("deposit_paid_amount", type=float) or 0.0
        deposit_paid = max(0.0, min(deposit_paid, deposit_due))

        if inquiry is None:
            inquiry = LargePartyInquiry()
            db.session.add(inquiry)

        inquiry.customer_name = customer_name
        inquiry.customer_phone = customer_phone
        inquiry.event_date = event_date
        inquiry.event_time = event_time
        inquiry.party_size = party_size
        inquiry.number_of_children = number_of_children
        inquiry.food_type = food_type
        inquiry.menu_option_id = menu_option_id
        inquiry.catered_people = catered_people
        inquiry.quoted_price_per_head = price_per_head
        inquiry.quoted_food_total = food_total
        inquiry.deposit_required_amount = deposit_due
        inquiry.deposit_paid_amount = deposit_paid
        inquiry.occasion = request.form.get("occasion", "").strip() or None
        inquiry.notes = request.form.get("notes", "").strip() or None
        inquiry.status = request.form.get("status", "Enquiry").strip() or "Enquiry"

        db.session.commit()

        flash(
            "Large party enquiry updated."
            if request.endpoint == "main.edit_large_party"
            else "Large party enquiry created.",
            "success",
        )
        return redirect(url_for("main.large_parties"))

    return render_template(
        "large_party_form.html",
        inquiry=inquiry,
        options=options,
        today=datetime.now().date(),
    )


@main.route("/large-party-options/<int:option_id>/price", methods=["POST"])
def update_large_party_option_price(option_id):
    option = db.get_or_404(LargePartyMenuOption, option_id)

    raw_price = request.form.get("price_per_head", "").strip()

    if raw_price == "":
        option.price_per_head = None
    else:
        try:
            price = float(raw_price)
            if price < 0:
                raise ValueError
            option.price_per_head = round(price, 2)
        except ValueError:
            flash("Enter a valid non-negative price.", "error")
            return redirect(url_for("main.large_parties"))

    db.session.commit()
    flash(f"{option.name} price updated.", "success")
    return redirect(url_for("main.large_parties"))
