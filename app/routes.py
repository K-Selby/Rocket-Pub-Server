from datetime import date, datetime, timedelta
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
    ExtraDishOption,
    InquiryExtraDish,
    LargePartyInquiry,
    LargePartyMenuOption,
    PubTable,
    RepeatBooking,
    RepeatBookingOccurrence,
    TablePairing,
)

main = Blueprint("main", __name__)

STANDARD_BOOKING_DURATION = 180
EARLIEST_BOOKING = "12:15"
LATEST_BOOKING = "19:30"
SUNDAY_LATEST_BOOKING = "19:00"


def normalise_phone(phone):
    cleaned = re.sub(r"\D", "", phone or "")

    if cleaned.startswith("44") and len(cleaned) >= 12:
        cleaned = "0" + cleaned[2:]

    return cleaned


def table_order_clause():
    return (cast(PubTable.number, Integer), PubTable.number)


def calculate_deposit(party_size):
    if not party_size or party_size <= 10:
        return 0.0

    return float(min(party_size * 5, 100))


def latest_booking_time_for_date(date_value):
    if date_value.weekday() == 6:
        return datetime.strptime(SUNDAY_LATEST_BOOKING, "%H:%M").time()

    return datetime.strptime(LATEST_BOOKING, "%H:%M").time()


def validate_booking_time(date_value, booking_time):
    earliest = datetime.strptime(EARLIEST_BOOKING, "%H:%M").time()
    latest = latest_booking_time_for_date(date_value)

    if not (earliest <= booking_time <= latest):
        return False

    # A normal booking must also be in the future.
    requested = datetime.combine(date_value, booking_time)

    if requested <= datetime.now():
        return False

    return True


def booking_time_error_message(date_value, booking_time=None):
    latest_text = "7:00pm" if date_value.weekday() == 6 else "7:30pm"

    if date_value < date.today():
        return "Bookings cannot be created for a previous day."

    if (
        date_value == date.today()
        and booking_time
        and datetime.combine(date_value, booking_time) <= datetime.now()
    ):
        return "That time has already passed. Please choose a later time."

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
    is_eating_food,
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

    # Food-unsuitable tables remain possible, but only as a last resort.
    if is_eating_food:
        score -= sum(60 for table in tables if table.unsuitable_for_food)

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
    is_eating_food=True,
    exclude_booking_id=None,
):
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
            is_eating_food,
        )

        if score is not None:
            candidates.append((score, [table]))

    for pairing in db.session.scalars(db.select(TablePairing)).all():
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
            is_eating_food,
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
        return "No suitable table is currently available."

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


def repeat_prompts_for_dashboard(selected_date):
    """
    Show repeat occurrences exactly one week before they are due.

    Example: viewing Sunday shows recurring Sunday bookings for the following
    Sunday with Confirm / Skip / Edit controls.
    """
    target_date = selected_date + timedelta(days=7)

    rules = db.session.scalars(
        db.select(RepeatBooking)
        .where(
            RepeatBooking.active.is_(True),
            RepeatBooking.weekday == target_date.weekday(),
        )
        .order_by(RepeatBooking.booking_time)
    ).all()

    prompts = []

    for rule in rules:
        occurrence = db.session.scalar(
            db.select(RepeatBookingOccurrence).where(
                RepeatBookingOccurrence.repeat_booking_id == rule.id,
                RepeatBookingOccurrence.occurrence_date == target_date,
            )
        )

        if occurrence is None:
            prompts.append(rule)

    return target_date, prompts


@main.route("/")
def dashboard():
    selected_text = request.args.get("date")

    try:
        selected_date = (
            datetime.strptime(selected_text, "%Y-%m-%d").date()
            if selected_text
            else date.today()
        )
    except ValueError:
        selected_date = date.today()

    bookings = db.session.scalars(
        db.select(Booking)
        .where(
            Booking.booking_date == selected_date,
            Booking.status != "Cancelled",
        )
        .order_by(Booking.booking_time)
    ).all()

    repeat_target_date, repeat_prompts = repeat_prompts_for_dashboard(
        selected_date
    )

    return render_template(
        "dashboard.html",
        bookings=bookings,
        selected_date=selected_date,
        previous_date=selected_date - timedelta(days=1),
        next_date=selected_date + timedelta(days=1),
        repeat_target_date=repeat_target_date,
        repeat_prompts=repeat_prompts,
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


@main.route("/customers/<int:customer_id>/edit", methods=["GET", "POST"])
def edit_customer(customer_id):
    customer = db.get_or_404(Customer, customer_id)
    areas = db.session.scalars(db.select(Area).order_by(Area.name)).all()
    tables = db.session.scalars(
        db.select(PubTable).order_by(*table_order_clause())
    ).all()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = normalise_phone(request.form.get("phone", ""))

        if not name or not phone:
            flash("Name and phone number are required.", "error")
            return redirect(request.url)

        duplicate = db.session.scalar(
            db.select(Customer).where(
                Customer.phone == phone,
                Customer.id != customer.id,
            )
        )

        if duplicate:
            flash("Another customer already uses that phone number.", "error")
            return redirect(request.url)

        customer.name = name
        customer.phone = phone
        customer.preferred_area_id = request.form.get(
            "preferred_area_id", type=int
        )
        customer.preferred_table_id = request.form.get(
            "preferred_table_id", type=int
        )
        customer.prefers_near_tv = request.form.get(
            "prefers_near_tv"
        ) == "on"
        customer.avoids_bench = request.form.get("avoids_bench") == "on"
        customer.notes = request.form.get("notes", "").strip() or None

        db.session.commit()
        flash("Customer updated.", "success")
        return redirect(url_for("main.customers"))

    return render_template(
        "customer_edit.html",
        customer=customer,
        areas=areas,
        tables=tables,
    )


@main.route("/customers/<int:customer_id>/delete", methods=["POST"])
def delete_customer(customer_id):
    customer = db.get_or_404(Customer, customer_id)

    # Because normal bookings belong to a customer, a true delete also removes
    # their normal booking history and repeat schedules.
    db.session.delete(customer)
    db.session.commit()

    flash("Customer and their linked booking history were deleted.", "success")
    return redirect(url_for("main.customers"))


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
            return redirect(request.url)

        if db.session.scalar(
            db.select(PubTable).where(PubTable.number == number)
        ):
            flash("That table number already exists.", "error")
            return redirect(request.url)

        db.session.add(
            PubTable(
                number=number,
                capacity=capacity,
                area_id=area_id,
                near_tv=request.form.get("near_tv") == "on",
                has_bench=request.form.get("has_bench") == "on",
                accessible=request.form.get("accessible") == "on",
                unsuitable_for_food=(
                    request.form.get("unsuitable_for_food") == "on"
                ),
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
            return redirect(request.url)

        duplicate = db.session.scalar(
            db.select(PubTable).where(
                PubTable.number == number,
                PubTable.id != table.id,
            )
        )

        if duplicate:
            flash("Another table already uses that number.", "error")
            return redirect(request.url)

        table.number = number
        table.capacity = capacity
        table.area_id = area_id
        table.near_tv = request.form.get("near_tv") == "on"
        table.has_bench = request.form.get("has_bench") == "on"
        table.accessible = request.form.get("accessible") == "on"
        table.unsuitable_for_food = (
            request.form.get("unsuitable_for_food") == "on"
        )
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
            else date.today()
        )
    except ValueError:
        selected_date = date.today()

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

        if booking is None and not validate_booking_time(
            booking_date, booking_time
        ):
            flash(
                booking_time_error_message(booking_date, booking_time),
                "error",
            )
            return redirect(request.url)

        # Existing bookings may be edited after their date/time has passed,
        # but changing them onto a new past slot is not allowed.
        if booking is not None:
            changed_slot = (
                booking.booking_date != booking_date
                or booking.booking_time != booking_time
            )

            if changed_slot and not validate_booking_time(
                booking_date, booking_time
            ):
                flash(
                    booking_time_error_message(booking_date, booking_time),
                    "error",
                )
                return redirect(request.url)

        preferred_area_id = request.form.get("preferred_area_id", type=int)
        preferred_table_id = request.form.get("preferred_table_id", type=int)
        wants_near_tv = request.form.get("wants_near_tv") == "on"
        avoids_bench = request.form.get("avoids_bench") == "on"
        is_eating_food = request.form.get("is_eating_food") == "on"

        selected_table_ids = request.form.getlist("table_ids", type=int)

        customer = get_or_create_customer(customer_name, customer_phone)
        customer.preferred_area_id = preferred_area_id
        customer.preferred_table_id = preferred_table_id
        customer.prefers_near_tv = wants_near_tv
        customer.avoids_bench = avoids_bench

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
                is_eating_food,
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
            booking = Booking(customer_id=customer.id)
            db.session.add(booking)
        else:
            booking.customer_id = customer.id
            BookingTable.query.filter_by(booking_id=booking.id).delete()

        booking.booking_date = booking_date
        booking.booking_time = booking_time
        booking.duration_minutes = STANDARD_BOOKING_DURATION
        booking.party_size = party_size
        booking.number_of_children = number_of_children
        booking.is_eating_food = is_eating_food
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

        repeat_weekly = request.form.get("repeat_weekly") == "on"

        if repeat_weekly:
            repeat_rule = booking.repeat_booking

            if repeat_rule is None:
                # All NOT NULL fields must be populated BEFORE the first flush.
                # The previous version created an empty RepeatBooking and then
                # flushed it to obtain an ID, which caused SQLite to reject the
                # row because weekday/time/party_size were still NULL.
                repeat_rule = RepeatBooking(
                    customer_id=customer.id,
                    weekday=booking_date.weekday(),
                    booking_time=booking_time,
                    party_size=party_size,
                    number_of_children=number_of_children,
                    is_eating_food=is_eating_food,
                    preferred_area_id=preferred_area_id,
                    preferred_table_id=preferred_table_id,
                    wants_near_tv=wants_near_tv,
                    avoids_bench=avoids_bench,
                    occasion=booking.occasion,
                    notes=booking.notes,
                    active=True,
                )
                db.session.add(repeat_rule)

                # Flush is now safe because every required field has a value.
                db.session.flush()
                booking.repeat_booking_id = repeat_rule.id
            else:
                # Existing repeat rules can simply be updated in place.
                repeat_rule.customer_id = customer.id
                repeat_rule.weekday = booking_date.weekday()
                repeat_rule.booking_time = booking_time
                repeat_rule.party_size = party_size
                repeat_rule.number_of_children = number_of_children
                repeat_rule.is_eating_food = is_eating_food
                repeat_rule.preferred_area_id = preferred_area_id
                repeat_rule.preferred_table_id = preferred_table_id
                repeat_rule.wants_near_tv = wants_near_tv
                repeat_rule.avoids_bench = avoids_bench
                repeat_rule.occasion = booking.occasion
                repeat_rule.notes = booking.notes
                repeat_rule.active = True

        elif booking.repeat_booking:
            booking.repeat_booking.active = False

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
        today=date.today(),
        now_time=datetime.now().strftime("%H:%M"),
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
# Repeat booking prompts
# -------------------------

@main.route("/repeat-bookings/<int:repeat_id>/confirm", methods=["POST"])
def confirm_repeat_booking(repeat_id):
    rule = db.get_or_404(RepeatBooking, repeat_id)
    occurrence_date = datetime.strptime(
        request.form["occurrence_date"], "%Y-%m-%d"
    ).date()

    existing_occurrence = db.session.scalar(
        db.select(RepeatBookingOccurrence).where(
            RepeatBookingOccurrence.repeat_booking_id == rule.id,
            RepeatBookingOccurrence.occurrence_date == occurrence_date,
        )
    )

    if existing_occurrence:
        flash("That repeat occurrence has already been handled.", "error")
        return redirect(url_for("main.dashboard"))

    if not validate_booking_time(occurrence_date, rule.booking_time):
        flash("That repeat occurrence is no longer a valid future slot.", "error")
        return redirect(url_for("main.dashboard"))

    tables = suggest_tables(
        rule.party_size,
        occurrence_date,
        rule.booking_time,
        STANDARD_BOOKING_DURATION,
        rule.preferred_area_id,
        rule.preferred_table_id,
        rule.wants_near_tv,
        rule.avoids_bench,
        rule.is_eating_food,
    )

    if not tables:
        flash(
            "No suitable table is available for that repeat booking. "
            "Edit the repeat booking or create it manually.",
            "error",
        )
        return redirect(
            url_for(
                "main.dashboard",
                date=(occurrence_date - timedelta(days=7)).isoformat(),
            )
        )

    booking = Booking(
        customer_id=rule.customer_id,
        repeat_booking_id=rule.id,
        booking_date=occurrence_date,
        booking_time=rule.booking_time,
        duration_minutes=STANDARD_BOOKING_DURATION,
        party_size=rule.party_size,
        number_of_children=rule.number_of_children,
        is_eating_food=rule.is_eating_food,
        occasion=rule.occasion,
        preferred_area_id=rule.preferred_area_id,
        preferred_table_id=rule.preferred_table_id,
        wants_near_tv=rule.wants_near_tv,
        avoids_bench=rule.avoids_bench,
        deposit_required_amount=calculate_deposit(rule.party_size),
        notes=rule.notes,
    )

    db.session.add(booking)
    db.session.flush()

    for table in tables:
        db.session.add(
            BookingTable(booking_id=booking.id, table_id=table.id)
        )

    db.session.add(
        RepeatBookingOccurrence(
            repeat_booking_id=rule.id,
            occurrence_date=occurrence_date,
            status="Confirmed",
            booking_id=booking.id,
        )
    )

    db.session.commit()
    flash("Repeat booking confirmed for next week.", "success")

    return redirect(
        url_for(
            "main.dashboard",
            date=(occurrence_date - timedelta(days=7)).isoformat(),
        )
    )


@main.route("/repeat-bookings/<int:repeat_id>/skip", methods=["POST"])
def skip_repeat_booking(repeat_id):
    rule = db.get_or_404(RepeatBooking, repeat_id)
    occurrence_date = datetime.strptime(
        request.form["occurrence_date"], "%Y-%m-%d"
    ).date()

    existing = db.session.scalar(
        db.select(RepeatBookingOccurrence).where(
            RepeatBookingOccurrence.repeat_booking_id == rule.id,
            RepeatBookingOccurrence.occurrence_date == occurrence_date,
        )
    )

    if not existing:
        db.session.add(
            RepeatBookingOccurrence(
                repeat_booking_id=rule.id,
                occurrence_date=occurrence_date,
                status="Skipped",
            )
        )
        db.session.commit()

    flash("This week's repeat booking was skipped.", "success")

    return redirect(
        url_for(
            "main.dashboard",
            date=(occurrence_date - timedelta(days=7)).isoformat(),
        )
    )


@main.route("/repeat-bookings/<int:repeat_id>/edit", methods=["GET", "POST"])
def edit_repeat_booking(repeat_id):
    rule = db.get_or_404(RepeatBooking, repeat_id)
    areas = db.session.scalars(db.select(Area).order_by(Area.name)).all()
    tables = db.session.scalars(
        db.select(PubTable)
        .where(PubTable.active.is_(True))
        .order_by(*table_order_clause())
    ).all()

    if request.method == "POST":
        weekday = request.form.get("weekday", type=int)
        party_size = request.form.get("party_size", type=int)
        children = request.form.get("number_of_children", type=int) or 0

        try:
            booking_time = datetime.strptime(
                request.form["booking_time"], "%H:%M"
            ).time()
        except (ValueError, KeyError):
            flash("Enter a valid repeat booking time.", "error")
            return redirect(request.url)

        if weekday is None or not party_size:
            flash("Day, time and party size are required.", "error")
            return redirect(request.url)

        earliest = datetime.strptime(EARLIEST_BOOKING, "%H:%M").time()
        latest = (
            datetime.strptime(SUNDAY_LATEST_BOOKING, "%H:%M").time()
            if weekday == 6
            else datetime.strptime(LATEST_BOOKING, "%H:%M").time()
        )

        if not earliest <= booking_time <= latest:
            flash(
                "Repeat booking time is outside the allowed booking window.",
                "error",
            )
            return redirect(request.url)

        if children < 0 or children > party_size:
            flash("Children cannot exceed total party size.", "error")
            return redirect(request.url)

        rule.weekday = weekday
        rule.booking_time = booking_time
        rule.party_size = party_size
        rule.number_of_children = children
        rule.is_eating_food = request.form.get("is_eating_food") == "on"
        rule.preferred_area_id = request.form.get("preferred_area_id", type=int)
        rule.preferred_table_id = request.form.get("preferred_table_id", type=int)
        rule.wants_near_tv = request.form.get("wants_near_tv") == "on"
        rule.avoids_bench = request.form.get("avoids_bench") == "on"
        rule.occasion = request.form.get("occasion", "").strip() or None
        rule.notes = request.form.get("notes", "").strip() or None
        rule.active = request.form.get("active") == "on"

        db.session.commit()
        flash("Repeat booking rule updated.", "success")
        return redirect(url_for("main.dashboard"))

    return render_template(
        "repeat_booking_form.html",
        rule=rule,
        areas=areas,
        tables=tables,
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
        .order_by(LargePartyMenuOption.option_number)
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
        .order_by(LargePartyMenuOption.option_number)
    ).all()

    extra_options = db.session.scalars(
        db.select(ExtraDishOption)
        .where(ExtraDishOption.active.is_(True))
        .order_by(ExtraDishOption.name)
    ).all()

    if request.method == "POST":
        customer_name = request.form.get("customer_name", "").strip()
        customer_phone = normalise_phone(request.form.get("customer_phone", ""))
        party_size = request.form.get("party_size", type=int)
        children = request.form.get("number_of_children", type=int) or 0

        if not customer_name or not customer_phone or not party_size:
            flash(
                "Name, phone number and estimated party size are required.",
                "error",
            )
            return redirect(request.url)

        if children < 0 or children > party_size:
            flash(
                "Number of children cannot exceed the total party size.",
                "error",
            )
            return redirect(request.url)

        event_date = None
        event_time = None

        if request.form.get("event_date"):
            try:
                event_date = datetime.strptime(
                    request.form["event_date"], "%Y-%m-%d"
                ).date()
            except ValueError:
                flash("Please enter a valid event date.", "error")
                return redirect(request.url)

        if request.form.get("event_time"):
            try:
                event_time = datetime.strptime(
                    request.form["event_time"], "%H:%M"
                ).time()
            except ValueError:
                flash("Please enter a valid event time.", "error")
                return redirect(request.url)

        food_type = request.form.get("food_type", "").strip() or None
        menu_option_id = request.form.get("menu_option_id", type=int)
        catered_people = request.form.get("catered_people", type=int)

        if catered_people is not None and (
            catered_people < 0 or catered_people > party_size
        ):
            flash(
                "People being catered for cannot exceed total attendance.",
                "error",
            )
            return redirect(request.url)

        selected_option = (
            db.session.get(LargePartyMenuOption, menu_option_id)
            if menu_option_id
            else None
        )

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
        inquiry.number_of_children = children
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

        db.session.flush()

        # Rebuild the extra-dish rows from the editable form.
        InquiryExtraDish.query.filter_by(inquiry_id=inquiry.id).delete()

        names = request.form.getlist("extra_dish_name")
        prices = request.form.getlist("extra_dish_price")
        quantities = request.form.getlist("extra_dish_quantity")
        custom_flags = request.form.getlist("extra_dish_custom")

        for index, raw_name in enumerate(names):
            dish_name = raw_name.strip()

            if not dish_name:
                continue

            try:
                price = float(prices[index])
                quantity = int(quantities[index])
            except (ValueError, IndexError):
                flash(
                    "Every extra dish needs a valid price and quantity.",
                    "error",
                )
                db.session.rollback()
                return redirect(request.url)

            if price < 0 or quantity <= 0:
                flash(
                    "Extra dish price must be non-negative and quantity above zero.",
                    "error",
                )
                db.session.rollback()
                return redirect(request.url)

            db.session.add(
                InquiryExtraDish(
                    inquiry_id=inquiry.id,
                    dish_name=dish_name,
                    price_per_head=round(price, 2),
                    quantity_people=quantity,
                    is_custom=(
                        index < len(custom_flags)
                        and custom_flags[index] == "1"
                    ),
                )
            )

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
        extra_options=extra_options,
        today=date.today(),
    )
