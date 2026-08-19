from datetime import datetime
from app import db


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
    active = db.Column(db.Boolean, default=True)

    x_position = db.Column(db.Float, default=0)
    y_position = db.Column(db.Float, default=0)

    area = db.relationship("Area", back_populates="tables")

    booking_links = db.relationship(
        "BookingTable",
        back_populates="table",
        cascade="all, delete-orphan"
    )


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


class Booking(db.Model):
    """A normal table booking. Standard table time is three hours."""

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)

    booking_date = db.Column(db.Date, nullable=False, index=True)
    booking_time = db.Column(db.Time, nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False, default=180)

    party_size = db.Column(db.Integer, nullable=False)
    number_of_children = db.Column(db.Integer, nullable=False, default=0)
    occasion = db.Column(db.String(120))

    preferred_area_id = db.Column(db.Integer, db.ForeignKey("area.id"))
    preferred_table_id = db.Column(db.Integer, db.ForeignKey("pub_table.id"))
    wants_near_tv = db.Column(db.Boolean, default=False)
    avoids_bench = db.Column(db.Boolean, default=False)

    # For parties above 10 people the system calculates £5/head capped at £100.
    deposit_required_amount = db.Column(db.Float, nullable=False, default=0)
    deposit_paid_amount = db.Column(db.Float, nullable=False, default=0)

    notes = db.Column(db.Text)
    status = db.Column(db.String(30), nullable=False, default="Booked")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer = db.relationship("Customer", back_populates="bookings")
    preferred_area = db.relationship("Area")
    preferred_table = db.relationship("PubTable", foreign_keys=[preferred_table_id])

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
    """Configurable food/buffet option used for large-party enquiries."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    price_per_head = db.Column(db.Float)
    active = db.Column(db.Boolean, nullable=False, default=True)


class LargePartyInquiry(db.Model):
    """
    A flexible enquiry rather than a confirmed table booking.

    Most details can be filled in later because callers may initially only ask
    about availability and then call back with food/final-number information.
    """

    id = db.Column(db.Integer, primary_key=True)

    customer_name = db.Column(db.String(120), nullable=False)
    customer_phone = db.Column(db.String(30), nullable=False, index=True)

    event_date = db.Column(db.Date, index=True)
    event_time = db.Column(db.Time)

    party_size = db.Column(db.Integer, nullable=False)
    number_of_children = db.Column(db.Integer, nullable=False, default=0)

    # "Menu", "Buffet", or blank/undecided.
    food_type = db.Column(db.String(30))

    menu_option_id = db.Column(
        db.Integer,
        db.ForeignKey("large_party_menu_option.id")
    )

    # Food can be ordered for fewer people than the total party size.
    catered_people = db.Column(db.Integer)

    quoted_price_per_head = db.Column(db.Float)
    quoted_food_total = db.Column(db.Float)

    deposit_required_amount = db.Column(db.Float, nullable=False, default=0)
    deposit_paid_amount = db.Column(db.Float, nullable=False, default=0)

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

    @property
    def deposit_balance(self):
        return max(
            float(self.deposit_required_amount or 0)
            - float(self.deposit_paid_amount or 0),
            0,
        )
