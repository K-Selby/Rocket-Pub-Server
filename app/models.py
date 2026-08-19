from datetime import datetime
from app import db



class AppUser(db.Model):
    """
    Login account for Rocket Pub Server.

    Roles:
      staff   - normal operational access
      manager - staff access + table/layout management + staff accounts
      admin   - full access, including manager accounts
    """

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(
        db.String(80),
        nullable=False,
        unique=True,
        index=True,
    )
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(
        db.String(20),
        nullable=False,
        default="staff",
        index=True,
    )
    must_change_password = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    # Email is optional for now, but can be verified using a six-digit code.
    email = db.Column(db.String(255), unique=True, index=True)
    pending_email = db.Column(db.String(255))
    email_verified = db.Column(db.Boolean, nullable=False, default=False)
    email_verification_code_hash = db.Column(db.String(255))
    email_verification_expires_at = db.Column(db.DateTime)

    # Forgotten-password verification.
    password_reset_code_hash = db.Column(db.String(255))
    password_reset_expires_at = db.Column(db.DateTime)

    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime)

    @property
    def is_manager(self):
        return self.role in {"manager", "admin"}

    @property
    def is_admin(self):
        return self.role == "admin"


class Customer(db.Model):
    """Recurring customer details and saved seating preferences."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    phone = db.Column(db.String(30), nullable=False, unique=True, index=True)

    preferred_area_id = db.Column(db.Integer, db.ForeignKey("area.id"))
    preferred_table_id = db.Column(db.Integer, db.ForeignKey("pub_table.id"))
    prefers_near_tv = db.Column(db.Boolean, default=False)
    avoids_bench = db.Column(db.Boolean, default=False)

    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    preferred_area = db.relationship("Area", foreign_keys=[preferred_area_id])
    preferred_table = db.relationship("PubTable", foreign_keys=[preferred_table_id])

    bookings = db.relationship(
        "Booking",
        back_populates="customer",
        cascade="all, delete-orphan"
    )

    repeat_bookings = db.relationship(
        "RepeatBooking",
        back_populates="customer",
        cascade="all, delete-orphan"
    )


class Area(db.Model):
    """Named sections of the pub."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)

    tables = db.relationship("PubTable", back_populates="area")


class PubTable(db.Model):
    """One physical pub table and its allocation characteristics."""

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(20), nullable=False, unique=True, index=True)
    capacity = db.Column(db.Integer, nullable=False)
    area_id = db.Column(db.Integer, db.ForeignKey("area.id"), nullable=False)

    near_tv = db.Column(db.Boolean, default=False)
    has_bench = db.Column(db.Boolean, default=False)
    accessible = db.Column(db.Boolean, default=False)

    # This table can still be used for food, but should be a last-resort choice.
    unsuitable_for_food = db.Column(db.Boolean, default=False)

    active = db.Column(db.Boolean, default=True)

    # Visual floor-plan layout values are stored as percentages/pixels within
    # the editable canvas so the same layout works on different screen sizes.
    x_position = db.Column(db.Float, default=40)
    y_position = db.Column(db.Float, default=40)
    layout_width = db.Column(db.Float, default=90)
    layout_height = db.Column(db.Float, default=60)
    layout_shape = db.Column(db.String(20), default="rectangle")
    layout_rotation = db.Column(db.Float, default=0)

    area = db.relationship("Area", back_populates="tables")

    booking_links = db.relationship(
        "BookingTable",
        back_populates="table",
        cascade="all, delete-orphan"
    )



class FloorPlanSetting(db.Model):
    """Stores global visual settings for the pub layout editor."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True, default="main")
    canvas_width = db.Column(db.Integer, nullable=False, default=1200)
    canvas_height = db.Column(db.Integer, nullable=False, default=760)
    background_note = db.Column(db.String(200))



class FloorPlanObject(db.Model):
    """
    A non-bookable object drawn on the master pub floor plan.

    Examples: walls, doors, bar counters, pillars, TVs, fixed tables, pool
    tables, stairs, area blocks and text labels.
    """

    id = db.Column(db.Integer, primary_key=True)

    object_type = db.Column(db.String(40), nullable=False, index=True)
    label = db.Column(db.String(120))

    x_position = db.Column(db.Float, nullable=False, default=80)
    y_position = db.Column(db.Float, nullable=False, default=80)
    layout_width = db.Column(db.Float, nullable=False, default=100)
    layout_height = db.Column(db.Float, nullable=False, default=60)
    layout_rotation = db.Column(db.Float, nullable=False, default=0)

    # rectangle, square, round or oval. Some object types visually override
    # this but it remains editable for flexibility.
    layout_shape = db.Column(
        db.String(20),
        nullable=False,
        default="rectangle"
    )

    z_index = db.Column(db.Integer, nullable=False, default=1)

    # Optional area link is useful for area blocks/labels and future filtering.
    area_id = db.Column(db.Integer, db.ForeignKey("area.id"))

    area = db.relationship("Area")

class TablePairing(db.Model):
    """Two tables that can physically be pushed together."""

    id = db.Column(db.Integer, primary_key=True)
    table_a_id = db.Column(db.Integer, db.ForeignKey("pub_table.id"), nullable=False)
    table_b_id = db.Column(db.Integer, db.ForeignKey("pub_table.id"), nullable=False)

    table_a = db.relationship("PubTable", foreign_keys=[table_a_id])
    table_b = db.relationship("PubTable", foreign_keys=[table_b_id])

    __table_args__ = (
        db.UniqueConstraint("table_a_id", "table_b_id", name="uq_table_pair"),
    )


class RepeatBooking(db.Model):
    """
    Weekly repeat-booking rule.

    It does not automatically create reservations. A prompt appears one week
    before the next occurrence so staff can Confirm, Skip, or edit the rule.
    """

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)

    weekday = db.Column(db.Integer, nullable=False)  # Monday=0 ... Sunday=6
    booking_time = db.Column(db.Time, nullable=False)

    party_size = db.Column(db.Integer, nullable=False)
    number_of_children = db.Column(db.Integer, nullable=False, default=0)
    high_chairs_required = db.Column(db.Integer, nullable=False, default=0)
    is_eating_food = db.Column(db.Boolean, nullable=False, default=True)

    preferred_area_id = db.Column(db.Integer, db.ForeignKey("area.id"))
    preferred_table_id = db.Column(db.Integer, db.ForeignKey("pub_table.id"))
    wants_near_tv = db.Column(db.Boolean, default=False)
    avoids_bench = db.Column(db.Boolean, default=False)

    occasion = db.Column(db.String(120))
    notes = db.Column(db.Text)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer = db.relationship("Customer", back_populates="repeat_bookings")
    preferred_area = db.relationship("Area")
    preferred_table = db.relationship("PubTable", foreign_keys=[preferred_table_id])

    occurrences = db.relationship(
        "RepeatBookingOccurrence",
        back_populates="repeat_booking",
        cascade="all, delete-orphan"
    )


class RepeatBookingOccurrence(db.Model):
    """Records whether a specific repeat occurrence was confirmed or skipped."""

    id = db.Column(db.Integer, primary_key=True)
    repeat_booking_id = db.Column(
        db.Integer,
        db.ForeignKey("repeat_booking.id"),
        nullable=False
    )
    occurrence_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False)  # Confirmed / Skipped
    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    repeat_booking = db.relationship("RepeatBooking", back_populates="occurrences")
    booking = db.relationship("Booking", foreign_keys=[booking_id])

    __table_args__ = (
        db.UniqueConstraint(
            "repeat_booking_id",
            "occurrence_date",
            name="uq_repeat_occurrence"
        ),
    )


class Booking(db.Model):
    """A normal table booking. Standard table time is two hours 30 minutes."""

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    repeat_booking_id = db.Column(db.Integer, db.ForeignKey("repeat_booking.id"))

    booking_date = db.Column(db.Date, nullable=False, index=True)
    booking_time = db.Column(db.Time, nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False, default=150)

    party_size = db.Column(db.Integer, nullable=False)
    number_of_children = db.Column(db.Integer, nullable=False, default=0)
    is_eating_food = db.Column(db.Boolean, nullable=False, default=True)
    occasion = db.Column(db.String(120))

    preferred_area_id = db.Column(db.Integer, db.ForeignKey("area.id"))
    preferred_table_id = db.Column(db.Integer, db.ForeignKey("pub_table.id"))
    wants_near_tv = db.Column(db.Boolean, default=False)
    avoids_bench = db.Column(db.Boolean, default=False)

    deposit_required_amount = db.Column(db.Float, nullable=False, default=0)
    deposit_paid_amount = db.Column(db.Float, nullable=False, default=0)

    notes = db.Column(db.Text)
    status = db.Column(db.String(30), nullable=False, default="Booked")

    # Set when staff explicitly mark the booking as finished/left early.
    # Bookings also appear completed visually once their scheduled end time
    # passes, even when this remains blank.
    completed_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer = db.relationship("Customer", back_populates="bookings")
    preferred_area = db.relationship("Area")
    preferred_table = db.relationship("PubTable", foreign_keys=[preferred_table_id])
    repeat_booking = db.relationship("RepeatBooking", foreign_keys=[repeat_booking_id])

    table_links = db.relationship(
        "BookingTable",
        back_populates="booking",
        cascade="all, delete-orphan"
    )

    @property
    def tables(self):
        return [link.table for link in self.table_links]

    @property
    def deposit_balance(self):
        return max(
            float(self.deposit_required_amount or 0)
            - float(self.deposit_paid_amount or 0),
            0,
        )


class BookingTable(db.Model):
    """Join table allowing one booking to use one or more physical tables."""

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id"), nullable=False)
    table_id = db.Column(db.Integer, db.ForeignKey("pub_table.id"), nullable=False)

    booking = db.relationship("Booking", back_populates="table_links")
    table = db.relationship("PubTable", back_populates="booking_links")

    __table_args__ = (
        db.UniqueConstraint("booking_id", "table_id", name="uq_booking_table"),
    )


class LargePartyMenuOption(db.Model):
    """One of the pub's four buffet packages."""

    id = db.Column(db.Integer, primary_key=True)
    option_number = db.Column(db.Integer, unique=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    price_per_head = db.Column(db.Float)
    items_text = db.Column(db.Text)
    active = db.Column(db.Boolean, nullable=False, default=True)


class ExtraDishOption(db.Model):
    """Standard additional hot dish available for buffet enquiries."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    default_price_per_head = db.Column(db.Float, nullable=False, default=6.50)
    minimum_people = db.Column(db.Integer, nullable=False, default=25)
    active = db.Column(db.Boolean, nullable=False, default=True)


class LargePartyInquiry(db.Model):
    """Open/editable large-party enquiry rather than an automatic reservation."""

    id = db.Column(db.Integer, primary_key=True)

    customer_name = db.Column(db.String(120), nullable=False)
    customer_phone = db.Column(db.String(30), nullable=False, index=True)

    event_date = db.Column(db.Date, index=True)
    event_time = db.Column(db.Time)
    expected_end_time = db.Column(db.Time)

    # When true, any reserved area/table remains blocked from the event start
    # until the end of the day rather than only until expected_end_time.
    reserve_for_rest_of_day = db.Column(db.Boolean, nullable=False, default=False)

    party_size = db.Column(db.Integer, nullable=False)
    number_of_children = db.Column(db.Integer, nullable=False, default=0)
    high_chairs_required = db.Column(db.Integer, nullable=False, default=0)

    food_type = db.Column(db.String(30))  # Menu / Buffet / blank
    menu_option_id = db.Column(
        db.Integer,
        db.ForeignKey("large_party_menu_option.id")
    )
    catered_people = db.Column(db.Integer)

    quoted_price_per_head = db.Column(db.Float)
    quoted_food_total = db.Column(db.Float)

    deposit_required_amount = db.Column(db.Float, nullable=False, default=0)
    deposit_paid_amount = db.Column(db.Float, nullable=False, default=0)

    # Optional promised date can be entered before any money is received.
    deposit_due_date = db.Column(db.Date)

    # Payment date becomes mandatory once deposit_paid_amount > 0.
    deposit_paid_date = db.Column(db.Date)
    deposit_payment_method = db.Column(db.String(20))
    deposit_taken_by = db.Column(db.String(120))

    occasion = db.Column(db.String(120))
    notes = db.Column(db.Text)
    status = db.Column(db.String(40), nullable=False, default="Enquiry")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    menu_option = db.relationship("LargePartyMenuOption")

    reserved_areas = db.relationship(
        "LargePartyReservedArea",
        back_populates="inquiry",
        cascade="all, delete-orphan"
    )

    reserved_tables = db.relationship(
        "LargePartyReservedTable",
        back_populates="inquiry",
        cascade="all, delete-orphan"
    )

    extra_dishes = db.relationship(
        "InquiryExtraDish",
        back_populates="inquiry",
        cascade="all, delete-orphan"
    )

    reminders = db.relationship(
        "InquiryReminder",
        back_populates="inquiry",
        cascade="all, delete-orphan"
    )

    @property
    def deposit_balance(self):
        return max(
            float(self.deposit_required_amount or 0)
            - float(self.deposit_paid_amount or 0),
            0,
        )

    @property
    def extras_total(self):
        return sum(float(item.total_price or 0) for item in self.extra_dishes)

    @property
    def total_amount(self):
        """Main buffet quote plus all extra dishes."""
        return round(
            float(self.quoted_food_total or 0) + float(self.extras_total or 0),
            2,
        )

    @property
    def total_remainder(self):
        """
        Amount still outstanding from the currently quoted food total after
        any deposit already recorded.
        """
        return max(
            round(
                float(self.total_amount or 0)
                - float(self.deposit_paid_amount or 0),
                2,
            ),
            0,
        )


class LargePartyReservedArea(db.Model):
    """An entire pub area blocked out for a large-party enquiry."""

    id = db.Column(db.Integer, primary_key=True)
    inquiry_id = db.Column(
        db.Integer,
        db.ForeignKey("large_party_inquiry.id"),
        nullable=False
    )
    area_id = db.Column(db.Integer, db.ForeignKey("area.id"), nullable=False)

    inquiry = db.relationship("LargePartyInquiry", back_populates="reserved_areas")
    area = db.relationship("Area")

    __table_args__ = (
        db.UniqueConstraint(
            "inquiry_id",
            "area_id",
            name="uq_large_party_reserved_area"
        ),
    )


class LargePartyReservedTable(db.Model):
    """A specific physical table blocked out for a large-party enquiry."""

    id = db.Column(db.Integer, primary_key=True)
    inquiry_id = db.Column(
        db.Integer,
        db.ForeignKey("large_party_inquiry.id"),
        nullable=False
    )
    table_id = db.Column(db.Integer, db.ForeignKey("pub_table.id"), nullable=False)

    inquiry = db.relationship("LargePartyInquiry", back_populates="reserved_tables")
    table = db.relationship("PubTable")

    __table_args__ = (
        db.UniqueConstraint(
            "inquiry_id",
            "table_id",
            name="uq_large_party_reserved_table"
        ),
    )



class InquiryReminder(db.Model):
    """A callback/follow-up reminder attached to a large-party enquiry."""

    id = db.Column(db.Integer, primary_key=True)
    inquiry_id = db.Column(
        db.Integer,
        db.ForeignKey("large_party_inquiry.id"),
        nullable=False
    )

    reminder_date = db.Column(db.Date, nullable=False, index=True)
    note = db.Column(db.String(250), nullable=False)

    # "manual" reminders come from the enquiry form. "deposit_due" is kept in
    # sync automatically with the expected/promised deposit date.
    reminder_kind = db.Column(
        db.String(30),
        nullable=False,
        default="manual",
        index=True,
    )

    completed = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    inquiry = db.relationship("LargePartyInquiry", back_populates="reminders")


class InquiryExtraDish(db.Model):
    """
    Extra hot dish attached to a large-party enquiry.

    The name/price/quantity are snapshots so staff can use a standard listed
    dish or enter a custom dish with a custom price and headcount.
    """

    id = db.Column(db.Integer, primary_key=True)
    inquiry_id = db.Column(
        db.Integer,
        db.ForeignKey("large_party_inquiry.id"),
        nullable=False
    )

    dish_name = db.Column(db.String(150), nullable=False)
    price_per_head = db.Column(db.Float, nullable=False)
    quantity_people = db.Column(db.Integer, nullable=False)
    is_custom = db.Column(db.Boolean, nullable=False, default=False)

    inquiry = db.relationship("LargePartyInquiry", back_populates="extra_dishes")

    @property
    def total_price(self):
        return round(
            float(self.price_per_head or 0) * int(self.quantity_people or 0),
            2,
        )
