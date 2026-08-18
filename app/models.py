from datetime import datetime
from app import db


class Customer(db.Model):
    """Stores customer details once so repeat bookings can reuse them."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    phone = db.Column(db.String(30), nullable=False, unique=True, index=True)
    email = db.Column(db.String(120))
    preferred_area_id = db.Column(db.Integer, db.ForeignKey("area.id"))
    preferred_table_id = db.Column(db.Integer, db.ForeignKey("pub_table.id"))
    prefers_near_tv = db.Column(db.Boolean, default=False)
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
    """Named sections of the pub, such as Restaurant or Pool Room."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)

    tables = db.relationship("PubTable", back_populates="area")


class PubTable(db.Model):
    """Represents one physical table in the pub."""

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(20), nullable=False, unique=True, index=True)
    capacity = db.Column(db.Integer, nullable=False)
    area_id = db.Column(db.Integer, db.ForeignKey("area.id"), nullable=False)

    near_tv = db.Column(db.Boolean, default=False)
    accessible = db.Column(db.Boolean, default=False)
    window_seat = db.Column(db.Boolean, default=False)
    active = db.Column(db.Boolean, default=True)

    # Stored now so a future floor-plan editor can position tables visually.
    x_position = db.Column(db.Float, default=0)
    y_position = db.Column(db.Float, default=0)

    area = db.relationship("Area", back_populates="tables")

    booking_links = db.relationship(
        "BookingTable",
        back_populates="table",
        cascade="all, delete-orphan"
    )


class TablePairing(db.Model):
    """Defines two tables that are physically able to be pushed together."""

    id = db.Column(db.Integer, primary_key=True)
    table_a_id = db.Column(db.Integer, db.ForeignKey("pub_table.id"), nullable=False)
    table_b_id = db.Column(db.Integer, db.ForeignKey("pub_table.id"), nullable=False)

    table_a = db.relationship("PubTable", foreign_keys=[table_a_id])
    table_b = db.relationship("PubTable", foreign_keys=[table_b_id])

    __table_args__ = (
        db.UniqueConstraint("table_a_id", "table_b_id", name="uq_table_pair"),
    )


class Booking(db.Model):
    """One customer reservation."""

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)

    booking_date = db.Column(db.Date, nullable=False, index=True)
    booking_time = db.Column(db.Time, nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False, default=120)

    party_size = db.Column(db.Integer, nullable=False)
    occasion = db.Column(db.String(120))
    preferred_area_id = db.Column(db.Integer, db.ForeignKey("area.id"))
    wants_near_tv = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)

    status = db.Column(db.String(30), nullable=False, default="Booked")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer = db.relationship("Customer", back_populates="bookings")
    preferred_area = db.relationship("Area")

    table_links = db.relationship(
        "BookingTable",
        back_populates="booking",
        cascade="all, delete-orphan"
    )

    @property
    def tables(self):
        """Convenient list of tables attached to the booking."""
        return [link.table for link in self.table_links]


class BookingTable(db.Model):
    """
    Join table between bookings and physical tables.

    We use this instead of putting one table number directly on Booking
    so a booking can use Table 1 + Table 2 together.
    """

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id"), nullable=False)
    table_id = db.Column(db.Integer, db.ForeignKey("pub_table.id"), nullable=False)

    booking = db.relationship("Booking", back_populates="table_links")
    table = db.relationship("PubTable", back_populates="booking_links")

    __table_args__ = (
        db.UniqueConstraint("booking_id", "table_id", name="uq_booking_table"),
    )
