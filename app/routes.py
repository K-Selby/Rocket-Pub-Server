from datetime import date, datetime, time, timedelta
from sqlalchemy import inspect, text

import calendar
import json
import uuid

import msal
import requests
import re
import secrets
import os

MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")
MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET")
MICROSOFT_TENANT_ID = os.getenv("MICROSOFT_TENANT_ID")

# The sender mailbox is a personal Outlook.com account, so use the consumers
# authority. The redirect URI must exactly match the URI registered in Entra.
MICROSOFT_AUTHORITY = "https://login.microsoftonline.com/consumers"
MICROSOFT_REDIRECT_URI = os.getenv(
    "MICROSOFT_REDIRECT_URI",
    "http://localhost:8000/auth/microsoft/callback",
)
MICROSOFT_SCOPES = ["Mail.Send"]


def microsoft_token_cache_path():
    """
    Store Microsoft's OAuth token cache locally beside the SQLite database.

    The cache may contain refresh-token material, so it is deliberately kept
    out of Git via .gitignore.
    """
    project_root = os.path.dirname(os.path.dirname(__file__))
    return os.path.join(
        project_root,
        "instance",
        "microsoft_token_cache.bin",
    )


def load_microsoft_token_cache():
    cache = msal.SerializableTokenCache()
    path = microsoft_token_cache_path()

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as file:
            cache.deserialize(file.read())

    return cache


def save_microsoft_token_cache(cache):
    if not cache.has_state_changed:
        return

    path = microsoft_token_cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        file.write(cache.serialize())


def build_cached_msal_app():
    cache = load_microsoft_token_cache()

    app = msal.ConfidentialClientApplication(
        MICROSOFT_CLIENT_ID,
        authority=MICROSOFT_AUTHORITY,
        client_credential=MICROSOFT_CLIENT_SECRET,
        token_cache=cache,
    )

    return app, cache


def get_microsoft_access_token():
    """
    Silently obtain a current Microsoft Graph access token.

    MSAL uses the cached account/refresh token and refreshes access tokens when
    required, so the pub mailbox does not need to sign in for every email.
    """
    if not MICROSOFT_CLIENT_ID or not MICROSOFT_CLIENT_SECRET:
        return None

    app, cache = build_cached_msal_app()
    accounts = app.get_accounts()

    if not accounts:
        return None

    result = app.acquire_token_silent(
        MICROSOFT_SCOPES,
        account=accounts[0],
    )

    save_microsoft_token_cache(cache)

    if result and "access_token" in result:
        return result["access_token"]

    return None


def microsoft_email_connected():
    return get_microsoft_access_token() is not None


from flask import (
    Blueprint,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import Integer, cast
from werkzeug.security import check_password_hash, generate_password_hash
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from flask import send_file, send_from_directory

from app import db
from app.models import (
    AppUser,
    AllergenMealSide,
    AllergenMenuItem,
    RotaFinishSetting,
    RotaShift,
    RotaShiftTemplate,
    RotaWeek,
    ShiftSwapRequest,
    StaffAvailabilityRule,
    StaffDiaryEntry,
    StaffProfile,
    Area,
    Booking,
    BookingTable,
    Customer,
    ExtraDishOption,
    FloorPlanObject,
    FloorPlanSetting,
    InquiryExtraDish,
    InquiryReminder,
    LargePartyInquiry,
    LargePartyMenuOption,
    LargePartyReservedArea,
    LargePartyReservedTable,
    PubTable,
    PubCalendarEvent,
    RepeatBooking,
    RepeatBookingOccurrence,
    TablePairing,
)

main = Blueprint("main", __name__)

STANDARD_BOOKING_DURATION = 150
EARLIEST_BOOKING = "12:15"
LATEST_BOOKING = "19:30"
SUNDAY_LATEST_BOOKING = "19:00"


ROLE_ORDER = {
    "staff": 1,
    "manager": 2,
    "admin": 3,
}

MANAGER_ENDPOINTS = {
    # Table records.
    "main.tables",
    "main.new_table",
    "main.edit_table",

    # Floor-plan editor and all write APIs behind it.

    # Permanent deletion is intentionally restricted.
    "main.delete_cancelled_booking",
    "main.delete_cancelled_large_party",

    # Allergen menu editing.
    "main.allergen_new",
    "main.allergen_edit",
    "main.allergen_delete",

    # Rota management.
    "main.rota_profiles",
    "main.rota_profile_new",
    "main.rota_profile_edit",
    "main.rota_profile_delete",
    "main.rota_profile_archive",
    "main.rota_profile_restore",
    "main.rota_create",
    "main.rota_edit",
    "main.rota_save_draft",
    "main.rota_add_shift",
    "main.rota_use_availability",
    "main.rota_edit_shift",
    "main.rota_delete_shift",
    "main.rota_publish",
    "main.rota_settings",
    "main.rota_template_add",
    "main.rota_template_delete",
    "main.diary_manager_update",
    "main.staff_request_inbox",
    "main.calendar_event_add",
    "main.calendar_event_delete",
    "main.swap_manager_decision",
}


ADMIN_ENDPOINTS = {
    "main.table_map",
    "main.table_layout",
    "main.save_table_layout",
    "main.update_layout_table",
    "main.create_layout_pairing",
    "main.delete_layout_pairing",
    "main.create_floor_object",
    "main.update_floor_object",
    "main.delete_floor_object",
    "main.duplicate_floor_object",
}




def normalise_email(value):
    return (value or "").strip().lower()


def email_delivery_mode():
    """
    Use Microsoft Graph by default.

    Setting ROCKET_EMAIL_MODE=console remains useful for development/testing
    without actually sending an email.
    """
    return os.environ.get(
        "ROCKET_EMAIL_MODE",
        "microsoft",
    ).strip().lower()


def send_rocket_email(recipient, subject, body):
    """
    Send a Rocket Pub Server email through Microsoft Graph.

    Console mode remains available for local development.
    """
    sender = os.environ.get(
        "ROCKET_EMAIL_FROM",
        "rocketpubserver@outlook.com",
    )

    if email_delivery_mode() == "console":
        print("\n" + "=" * 60)
        print("ROCKET PUB SERVER EMAIL")
        print(f"To: {recipient}")
        print(f"From: {sender}")
        print(f"Subject: {subject}")
        print(body)
        print("=" * 60 + "\n")
        return True, "Email content printed in the server Terminal."

    access_token = get_microsoft_access_token()

    if not access_token:
        return False, (
            "Rocket Pub Server email is not connected. "
            "An administrator needs to connect the Outlook mailbox first."
        )

    payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "Text",
                "content": body,
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": recipient,
                    }
                }
            ],
        },
        "saveToSentItems": True,
    }

    try:
        response = requests.post(
            "https://graph.microsoft.com/v1.0/me/sendMail",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )
    except requests.RequestException as exc:
        print(f"Microsoft Graph email request failed: {exc}")
        return False, "The email could not be sent."

    if response.status_code == 202:
        return True, f"Email sent to {recipient}."

    print(
        "Microsoft Graph sendMail failed:",
        response.status_code,
        response.text,
    )

    return False, (
        "Microsoft could not send the email. "
        "Check the Rocket Email connection in Users."
    )


def send_verification_email(recipient, code):
    subject = "Rocket Pub Server email verification"
    body = (
        "Your Rocket Pub Server verification code is:\n\n"
        f"{code}\n\n"
        "This code expires in 15 minutes.\n\n"
        "If you did not request this code, you can ignore this email."
    )

    success, message = send_rocket_email(recipient, subject, body)

    if success:
        return True, f"Verification code sent to {recipient}."

    return False, message


def send_password_reset_email(recipient, code):
    subject = "Rocket Pub Server password reset"
    body = (
        "A password reset was requested for your Rocket Pub Server account.\n\n"
        "Your reset code is:\n\n"
        f"{code}\n\n"
        "This code expires in 15 minutes.\n\n"
        "If you did not request a password reset, you can ignore this email."
    )

    success, message = send_rocket_email(recipient, subject, body)

    if success:
        return True, f"Password reset code sent to {recipient}."

    return False, message



def start_email_verification(user, email):
    email = normalise_email(email)

    if not email or "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        return False, "Enter a valid email address."

    duplicate = db.session.scalar(
        db.select(AppUser).where(
            db.or_(
                AppUser.email == email,
                AppUser.pending_email == email,
            ),
            AppUser.id != user.id,
        )
    )

    if duplicate:
        return False, "That email address is already attached to another user."

    code = f"{secrets.randbelow(1000000):06d}"

    user.pending_email = email
    user.email_verification_code_hash = generate_password_hash(code)
    user.email_verification_expires_at = (
        datetime.now() + timedelta(minutes=15)
    )
    db.session.commit()

    success, delivery_message = send_verification_email(email, code)

    if not success:
        return False, delivery_message

    return True, delivery_message


def manager_can_manage_user(target):
    user = current_user()

    if user is None or not user.is_manager:
        return False

    if user.is_admin:
        return target.role != "admin" or target.id == user.id

    return target.role == "staff"



def current_user():
    return getattr(g, "current_user", None)


def user_has_role(minimum_role):
    user = current_user()

    if user is None:
        return False

    return ROLE_ORDER.get(user.role, 0) >= ROLE_ORDER.get(minimum_role, 99)


@main.before_app_request
def load_and_protect_user():
    """
    Protect the whole local application behind a login.

    Static assets and the login screen remain public. First-login password
    change is mandatory before any operational screen can be opened.
    """
    user_id = session.get("user_id")

    g.current_user = (
        db.session.get(AppUser, user_id)
        if user_id is not None
        else None
    )

    endpoint = request.endpoint or ""

    if endpoint == "static":
        return None

    public_endpoints = {
        "main.login",
        "main.forgot_password",
        "main.forgot_password_verify",
        "main.forgot_password_new",

        # Public customer portal - no staff login required.
        "main.customer_home",
        "main.customer_food_menu",
        "main.customer_allergens",
    }

    if endpoint in public_endpoints:
        return None

    if g.current_user is None or not g.current_user.active:
        session.clear()
        return redirect(url_for("main.login", next=request.path))

    if (
        g.current_user.must_change_password
        and endpoint not in {
            "main.change_password",
            "main.logout",
        }
    ):
        return redirect(url_for("main.change_password"))

    if endpoint in MANAGER_ENDPOINTS and not g.current_user.is_manager:
        flash("Manager access is required for that screen.", "error")
        return redirect(url_for("main.dashboard"))

    if endpoint in ADMIN_ENDPOINTS and not g.current_user.is_admin:
        flash("Admin access is required for table layout changes.", "error")
        return redirect(url_for("main.table_map"))

    return None


@main.app_context_processor
def inject_current_user():
    user = current_user()
    request_count = 0

    if user and user.is_manager:
        pending = db.session.scalars(
            db.select(StaffDiaryEntry).where(
                StaffDiaryEntry.status == "requested",
                StaffDiaryEntry.entry_type.in_(
                    ["day_off_request", "available_window"]
                ),
            )
        ).all()

        request_count = len({
            entry.request_group_id or f"entry-{entry.id}"
            for entry in pending
        })

    incoming_swap_count = 0
    profile = current_staff_profile()

    if user and profile:
        incoming_swap_count = db.session.scalar(
            db.select(db.func.count(ShiftSwapRequest.id)).where(
                ShiftSwapRequest.target_staff_id == profile.id,
                ShiftSwapRequest.status == "pending_target",
            )
        ) or 0

    return {
        "current_user": user,
        "manager_request_count": request_count,
        "incoming_swap_count": incoming_swap_count,
    }



@main.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """
    Start a forgotten-password flow.

    The user supplies their username. We only continue if the account has a
    verified email address. The response is intentionally generic where
    possible so the page does not unnecessarily expose account information.
    """
    if request.method == "POST":
        username = request.form.get("username", "").strip()

        user = db.session.scalar(
            db.select(AppUser).where(
                db.func.lower(AppUser.username) == username.lower(),
                AppUser.active.is_(True),
            )
        )

        if user is None:
            flash(
                "If that account exists and has a verified email, a reset code will be sent.",
                "success",
            )
            return redirect(url_for("main.forgot_password"))

        if not user.email_verified or not user.email:
            flash(
                "This account does not have a verified email. "
                "Please ask a manager or administrator to reset the password.",
                "error",
            )
            return redirect(url_for("main.forgot_password"))

        code = f"{secrets.randbelow(1000000):06d}"

        user.password_reset_code_hash = generate_password_hash(code)
        user.password_reset_expires_at = (
            datetime.now() + timedelta(minutes=15)
        )
        db.session.commit()

        success, message = send_password_reset_email(
            user.email,
            code,
        )

        if not success:
            flash(message, "error")
            return redirect(url_for("main.forgot_password"))

        session["password_reset_user_id"] = user.id
        session["password_reset_verified"] = False

        flash(
            "A six-digit password reset code has been sent to your email.",
            "success",
        )
        return redirect(url_for("main.forgot_password_verify"))

    return render_template("forgot_password.html")


@main.route("/forgot-password/verify", methods=["GET", "POST"])
def forgot_password_verify():
    user_id = session.get("password_reset_user_id")

    if not user_id:
        flash("Start the password reset again.", "error")
        return redirect(url_for("main.forgot_password"))

    user = db.session.get(AppUser, user_id)

    if user is None:
        session.pop("password_reset_user_id", None)
        session.pop("password_reset_verified", None)
        return redirect(url_for("main.forgot_password"))

    if request.method == "POST":
        action = request.form.get("action", "verify")

        if action == "resend":
            if not user.email_verified or not user.email:
                flash("This account has no verified email.", "error")
                return redirect(url_for("main.forgot_password"))

            code = f"{secrets.randbelow(1000000):06d}"
            user.password_reset_code_hash = generate_password_hash(code)
            user.password_reset_expires_at = (
                datetime.now() + timedelta(minutes=15)
            )
            db.session.commit()

            success, message = send_password_reset_email(
                user.email,
                code,
            )
            flash(message, "success" if success else "error")
            return redirect(request.url)

        code = request.form.get("code", "").strip()

        if (
            not user.password_reset_code_hash
            or not user.password_reset_expires_at
        ):
            flash("Request a new password reset code.", "error")
            return redirect(url_for("main.forgot_password"))

        if datetime.now() > user.password_reset_expires_at:
            flash(
                "That reset code has expired. Request a new one.",
                "error",
            )
            return redirect(request.url)

        if not check_password_hash(
            user.password_reset_code_hash,
            code,
        ):
            flash("Incorrect reset code.", "error")
            return redirect(request.url)

        session["password_reset_verified"] = True
        return redirect(url_for("main.forgot_password_new"))

    return render_template(
        "forgot_password_verify.html",
        email=user.email,
    )


@main.route("/forgot-password/new", methods=["GET", "POST"])
def forgot_password_new():
    user_id = session.get("password_reset_user_id")
    verified = session.get("password_reset_verified")

    if not user_id or not verified:
        flash("Verify your reset code first.", "error")
        return redirect(url_for("main.forgot_password"))

    user = db.session.get(AppUser, user_id)

    if user is None:
        session.pop("password_reset_user_id", None)
        session.pop("password_reset_verified", None)
        return redirect(url_for("main.forgot_password"))

    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(new_password) < 8:
            flash("New passwords must be at least 8 characters.", "error")
            return redirect(request.url)

        if new_password == "Password":
            flash(
                "Choose a password other than the default Password.",
                "error",
            )
            return redirect(request.url)

        if new_password != confirm_password:
            flash("The new passwords do not match.", "error")
            return redirect(request.url)

        user.password_hash = generate_password_hash(new_password)
        user.must_change_password = False
        user.password_reset_code_hash = None
        user.password_reset_expires_at = None
        db.session.commit()

        session.pop("password_reset_user_id", None)
        session.pop("password_reset_verified", None)

        flash(
            "Your password has been reset. You can now sign in.",
            "success",
        )
        return redirect(url_for("main.login"))

    return render_template("forgot_password_new.html")


@main.route("/login", methods=["GET", "POST"])
def login():
    if current_user() is not None and current_user().active:
        if current_user().must_change_password:
            return redirect(url_for("main.change_password"))
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = db.session.scalar(
            db.select(AppUser).where(
                AppUser.username == username,
                AppUser.active.is_(True),
            )
        )

        if user is None or not check_password_hash(
            user.password_hash,
            password,
        ):
            flash("Incorrect username or password.", "error")
            return render_template(
                "login.html",
                username=username,
            )

        session.clear()
        session.permanent = True
        session["user_id"] = user.id
        user.last_login_at = datetime.now()
        db.session.commit()

        if user.must_change_password:
            return redirect(url_for("main.change_password"))

        return redirect(url_for("main.dashboard"))

    return render_template("login.html")


@main.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("main.login"))


@main.route("/change-password", methods=["GET", "POST"])
def change_password():
    user = current_user()
    first_login_was_required = bool(user.must_change_password)

    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not check_password_hash(user.password_hash, current_password):
            flash("Your current password is incorrect.", "error")
            return redirect(url_for("main.change_password"))

        if len(new_password) < 8:
            flash("New passwords must be at least 8 characters.", "error")
            return redirect(url_for("main.change_password"))

        if new_password == "Password":
            flash(
                "Choose a password other than the default Password.",
                "error",
            )
            return redirect(url_for("main.change_password"))

        if new_password != confirm_password:
            flash("The new passwords do not match.", "error")
            return redirect(url_for("main.change_password"))

        user.password_hash = generate_password_hash(new_password)
        user.must_change_password = False
        db.session.commit()

        flash("Password changed successfully.", "success")

        # First-login sequence: password first, then optional email setup.
        if first_login_was_required:
            return redirect(url_for("main.email_setup", first_login="1"))

        return redirect(url_for("main.dashboard"))

    return render_template(
        "change_password.html",
        first_login=bool(user.must_change_password),
    )



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



def large_party_datetime_range(inquiry):
    """
    Return the blocking window for a large-party enquiry.

    - If "rest of day" is selected, the reservation runs until 23:59:59.
    - Otherwise it uses the expected end time.
    - For older enquiries without an end time, fall back to three hours so
      existing test records remain usable.
    """
    if not inquiry.event_date or not inquiry.event_time:
        return None, None

    start = datetime.combine(inquiry.event_date, inquiry.event_time)

    if inquiry.reserve_for_rest_of_day:
        end = datetime.combine(
            inquiry.event_date,
            datetime.strptime("23:59:59", "%H:%M:%S").time(),
        )
    elif inquiry.expected_end_time:
        end = datetime.combine(inquiry.event_date, inquiry.expected_end_time)

        # If an end time earlier than the start somehow exists on an old/test
        # record, fall back rather than creating a negative reservation window.
        if end <= start:
            end = start + timedelta(minutes=STANDARD_BOOKING_DURATION)
    else:
        end = start + timedelta(minutes=STANDARD_BOOKING_DURATION)

    return start, end


def large_party_blocked_table_ids(
    date_value,
    time_value,
    duration_minutes,
    exclude_inquiry_id=None,
):
    """
    Return tables blocked by overlapping large-party reservations.

    Reserving an area blocks every active table in that area. Explicitly
    selected tables are also blocked.
    """
    requested_start = datetime.combine(date_value, time_value)
    requested_end = requested_start + timedelta(minutes=duration_minutes)

    stmt = db.select(LargePartyInquiry).where(
        LargePartyInquiry.event_date == date_value,
        LargePartyInquiry.status != "Cancelled",
    )

    if exclude_inquiry_id:
        stmt = stmt.where(LargePartyInquiry.id != exclude_inquiry_id)

    blocked = set()

    for inquiry in db.session.scalars(stmt).all():
        start, end = large_party_datetime_range(inquiry)

        if start is None:
            continue

        if requested_start < end and requested_end > start:
            blocked.update(link.table_id for link in inquiry.reserved_tables)

            area_ids = [link.area_id for link in inquiry.reserved_areas]

            if area_ids:
                area_tables = db.session.scalars(
                    db.select(PubTable.id).where(
                        PubTable.area_id.in_(area_ids),
                        PubTable.active.is_(True),
                    )
                ).all()
                blocked.update(area_tables)

    return blocked


def selected_large_party_blocked_table_ids(inquiry):
    """Expand this enquiry's reserved areas + reserved tables into table IDs."""
    blocked = {link.table_id for link in inquiry.reserved_tables}
    area_ids = [link.area_id for link in inquiry.reserved_areas]

    if area_ids:
        blocked.update(
            db.session.scalars(
                db.select(PubTable.id).where(
                    PubTable.area_id.in_(area_ids),
                    PubTable.active.is_(True),
                )
            ).all()
        )

    return blocked


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

    if table_id in large_party_blocked_table_ids(
        date_value,
        time_value,
        duration_minutes,
    ):
        return False

    stmt = (
        db.select(BookingTable)
        .join(Booking)
        .where(
            BookingTable.table_id == table_id,
            Booking.booking_date == date_value,
            Booking.status.notin_(["Cancelled", "Completed"]),
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
    excluded_table_ids=None,
):
    tables = db.session.scalars(
        db.select(PubTable)
        .join(Area)
        .where(
            PubTable.active.is_(True),
            db.func.lower(Area.name) != "bar",
        )
        .order_by(*table_order_clause())
    ).all()

    candidates = []
    excluded_table_ids = set(excluded_table_ids or [])

    for table in tables:
        if table.id in excluded_table_ids:
            continue
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

        if any(table.id in excluded_table_ids for table in pair):
            continue

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



def selected_tables_form_valid_pairing_group(selected_tables):
    """
    Allow more than two tables, but only when they form one physically connected
    group through configured pairings.

    Example: T1+T2+T3 is valid if T1 pairs with T2 and T2 pairs with T3.
    """
    if len(selected_tables) <= 1:
        return True

    selected_ids = {table.id for table in selected_tables}
    pairings = db.session.scalars(db.select(TablePairing)).all()

    adjacency = {table_id: set() for table_id in selected_ids}

    for pairing in pairings:
        a = pairing.table_a_id
        b = pairing.table_b_id

        if a in selected_ids and b in selected_ids:
            adjacency[a].add(b)
            adjacency[b].add(a)

    # Graph connectivity check.
    start = next(iter(selected_ids))
    visited = set()
    stack = [start]

    while stack:
        current = stack.pop()

        if current in visited:
            continue

        visited.add(current)
        stack.extend(adjacency[current] - visited)

    return visited == selected_ids


def available_pairing_groups(
    party_size,
    date_value,
    time_value,
    duration_minutes,
    preferred_area_id=None,
    wants_near_tv=False,
    avoids_bench=False,
    is_eating_food=True,
    exclude_booking_id=None,
):
    """
    Configured pairing suggestions for normal bookings below 10 people.

    Large normal bookings (10+) deliberately do not use automatic pairing or
    floor-plan proximity. They use the dedicated Pool Room / Snug manual mode.
    """
    if party_size >= 10:
        return []

    tables = {
        table.id: table
        for table in db.session.scalars(
            db.select(PubTable)
            .join(Area)
            .where(
                PubTable.active.is_(True),
                db.func.lower(Area.name) != "bar",
            )
        ).all()
    }

    pairings = db.session.scalars(db.select(TablePairing)).all()
    adjacency = {table_id: set() for table_id in tables}

    for pairing in pairings:
        if pairing.table_a_id in tables and pairing.table_b_id in tables:
            adjacency[pairing.table_a_id].add(pairing.table_b_id)
            adjacency[pairing.table_b_id].add(pairing.table_a_id)

    def available_table(table):
        return (
            table_is_available(
                table.id,
                date_value,
                time_value,
                duration_minutes,
                exclude_booking_id,
            )
            and not (avoids_bench and table.has_bench)
        )

    results = []
    seen = set()

    def add_result(group_ids):
        key = tuple(sorted(group_ids))
        if key in seen:
            return
        seen.add(key)

        group_tables = [tables[table_id] for table_id in key]

        if not all(available_table(table) for table in group_tables):
            return

        capacity = sum(table.capacity for table in group_tables)
        if capacity < party_size:
            return

        score = score_candidate(
            group_tables,
            party_size,
            preferred_area_id,
            None,
            wants_near_tv,
            avoids_bench,
            is_eating_food,
        )

        if score is None:
            return

        results.append(
            {
                "table_ids": list(key),
                "numbers": [table.number for table in group_tables],
                "capacity": capacity,
                "shortage": 0,
                "score": score,
                "fallback": False,
            }
        )

    def dfs(group):
        key = tuple(sorted(group))
        if key in seen:
            return

        group_tables = [tables[table_id] for table_id in key]
        capacity = sum(table.capacity for table in group_tables)

        if (
            capacity >= party_size
            and all(available_table(table) for table in group_tables)
        ):
            add_result(group)
            return

        neighbours = set()
        for table_id in group:
            neighbours.update(adjacency.get(table_id, set()))

        for neighbour in neighbours - set(group):
            dfs(set(group) | {neighbour})

    for table_id in tables:
        dfs({table_id})

    results.sort(
        key=lambda item: (
            -item["score"],
            item["capacity"] - party_size,
            len(item["table_ids"]),
        )
    )
    return results[:12]


def is_large_booking_area(table):
    """10+ normal bookings are seated only in Pool Room / Snug / Cubby."""
    area_name = (table.area.name or "").strip().lower()
    return (
        "pool" in area_name
        or "snug" in area_name
        or "cubby" in area_name
    )


def overlapping_normal_bookings(
    table_ids,
    date_value,
    time_value,
    duration_minutes,
    exclude_booking_id=None,
):
    """Return active normal bookings overlapping any of the supplied tables."""
    table_ids = set(table_ids or [])
    if not table_ids:
        return []

    requested_start = datetime.combine(date_value, time_value)
    requested_end = requested_start + timedelta(minutes=duration_minutes)

    stmt = (
        db.select(Booking)
        .join(BookingTable)
        .where(
            BookingTable.table_id.in_(table_ids),
            Booking.booking_date == date_value,
            Booking.status.notin_(["Cancelled", "Completed"]),
        )
        .distinct()
    )

    if exclude_booking_id:
        stmt = stmt.where(Booking.id != exclude_booking_id)

    overlaps = []
    for existing in db.session.scalars(stmt).all():
        existing_start, existing_end = booking_datetime_range(existing)
        if requested_start < existing_end and requested_end > existing_start:
            overlaps.append(existing)

    return overlaps


def large_booking_recommended_groups(
    party_size,
    date_value,
    time_value,
    duration_minutes,
    exclude_booking_id=None,
):
    """
    Build simple area-based table collections for 10+ normal bookings.

    Tables are taken in table-number order within Pool Room first, then
    Snug/Cubby. This is intentionally not a proximity algorithm.
    """
    if party_size < 10:
        return []

    tables = db.session.scalars(
        db.select(PubTable)
        .join(Area)
        .where(PubTable.active.is_(True))
        .order_by(*table_order_clause())
    ).all()

    priority_tables = [table for table in tables if is_large_booking_area(table)]
    blocked_large_party = large_party_blocked_table_ids(
        date_value,
        time_value,
        duration_minutes,
    )

    grouped = {}
    for table in priority_tables:
        if table.id in blocked_large_party:
            continue

        conflicts = overlapping_normal_bookings(
            [table.id],
            date_value,
            time_value,
            duration_minutes,
            exclude_booking_id,
        )

        # A larger booking may displace only strictly smaller normal bookings.
        if any(existing.party_size >= party_size for existing in conflicts):
            continue

        grouped.setdefault(table.area.name, []).append(table)

    def area_rank(name):
        lower = (name or "").lower()
        if "pool" in lower:
            return 0
        if "snug" in lower or "cubby" in lower:
            return 1
        return 2

    results = []

    for area_name in sorted(grouped, key=lambda name: (area_rank(name), name)):
        area_tables = grouped[area_name]
        selected = []
        capacity = 0

        for table in area_tables:
            selected.append(table)
            capacity += table.capacity
            if capacity >= party_size:
                break

        if capacity >= party_size:
            results.append(
                {
                    "area_name": area_name,
                    "table_ids": [table.id for table in selected],
                    "numbers": [table.number for table in selected],
                    "capacity": capacity,
                }
            )

    return results


def relocate_smaller_bookings_for_priority_large_booking(
    selected_tables,
    party_size,
    booking_date,
    booking_time,
    exclude_booking_id=None,
):
    """
    Give a 10+ normal booking priority over smaller normal bookings.

    Smaller overlapping bookings are moved to the best available alternative.
    If one cannot be moved safely, the larger booking save is rejected.
    """
    selected_ids = {table.id for table in selected_tables}

    conflicts = overlapping_normal_bookings(
        selected_ids,
        booking_date,
        booking_time,
        STANDARD_BOOKING_DURATION,
        exclude_booking_id,
    )

    moved = []

    for existing in conflicts:
        if existing.party_size >= party_size:
            raise ValueError(
                f"Table conflict with {existing.customer.name}'s booking for "
                f"{existing.party_size}. Choose different Pool Room / Snug tables."
            )

        alternatives = suggest_tables(
            existing.party_size,
            existing.booking_date,
            existing.booking_time,
            existing.duration_minutes,
            existing.preferred_area_id,
            existing.preferred_table_id,
            existing.wants_near_tv,
            existing.avoids_bench,
            existing.is_eating_food,
            exclude_booking_id=existing.id,
            excluded_table_ids=selected_ids,
        )

        if not alternatives:
            raise ValueError(
                f"{existing.customer.name}'s smaller booking uses one of those "
                "tables and there is nowhere safe to move it."
            )

        BookingTable.query.filter_by(booking_id=existing.id).delete()
        for table in alternatives:
            db.session.add(
                BookingTable(
                    booking_id=existing.id,
                    table_id=table.id,
                )
            )

        moved.append(existing.customer.name)

    return moved



def validate_selected_tables(
    selected_tables,
    party_size,
    booking_date,
    booking_time,
    exclude_booking_id=None,
):
    if not selected_tables:
        if party_size >= 10:
            return (
                "For bookings of 10 or more, manually select enough tables "
                "from the Pool Room and/or Snug."
            )
        return "No suitable table is currently available."

    total_capacity = sum(table.capacity for table in selected_tables)

    if total_capacity < party_size:
        return f"Selected tables only hold {total_capacity} people."

    if party_size >= 10:
        blocked = large_party_blocked_table_ids(
            booking_date,
            booking_time,
            STANDARD_BOOKING_DURATION,
        )
        for table in selected_tables:
            if table.id in blocked:
                return (
                    f"Table {table.number} is reserved by a large-party enquiry."
                )

        conflicts = overlapping_normal_bookings(
            [table.id for table in selected_tables],
            booking_date,
            booking_time,
            STANDARD_BOOKING_DURATION,
            exclude_booking_id,
        )

        if any(existing.party_size >= party_size for existing in conflicts):
            return (
                "One or more selected tables are already being used by an "
                "equal or larger booking."
            )

        return None

    for table in selected_tables:
        if not table_is_available(
            table.id,
            booking_date,
            booking_time,
            STANDARD_BOOKING_DURATION,
            exclude_booking_id,
        ):
            return f"Table {table.number} overlaps another booking."

    if not selected_tables_form_valid_pairing_group(selected_tables):
        return (
            "Those tables do not form one valid connected pairing group. "
            "Only tables configured as physically pairable can be combined."
        )

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



def relocate_bookings_conflicting_with_large_party(inquiry):
    """
    Move existing normal bookings away from tables/areas now reserved by a
    large-party enquiry.

    The booking keeps its original customer/date/time/preferences; only the
    assigned table(s) change. If no alternative exists, the save is rejected
    rather than silently leaving a conflict.
    """
    if not inquiry.event_date or not inquiry.event_time:
        return []

    blocked = selected_large_party_blocked_table_ids(inquiry)

    if not blocked:
        return []

    inquiry_start, inquiry_end = large_party_datetime_range(inquiry)

    bookings = db.session.scalars(
        db.select(Booking)
        .where(
            Booking.booking_date == inquiry.event_date,
            Booking.status != "Cancelled",
        )
        .order_by(Booking.booking_time)
    ).all()

    moved = []

    for booking in bookings:
        booking_start, booking_end = booking_datetime_range(booking)

        if not (
            booking_start < inquiry_end and
            booking_end > inquiry_start
        ):
            continue

        current_ids = {table.id for table in booking.tables}

        if not current_ids.intersection(blocked):
            continue

        alternatives = suggest_tables(
            booking.party_size,
            booking.booking_date,
            booking.booking_time,
            booking.duration_minutes,
            booking.preferred_area_id,
            booking.preferred_table_id,
            booking.wants_near_tv,
            booking.avoids_bench,
            booking.is_eating_food,
            exclude_booking_id=booking.id,
            excluded_table_ids=blocked,
        )

        if not alternatives:
            raise ValueError(
                f"{booking.customer.name}'s {booking.booking_time.strftime('%H:%M')} "
                "booking cannot be moved because no alternative table is available."
            )

        BookingTable.query.filter_by(booking_id=booking.id).delete()

        for table in alternatives:
            db.session.add(
                BookingTable(booking_id=booking.id, table_id=table.id)
            )

        moved.append(
            f"{booking.customer.name} at {booking.booking_time.strftime('%H:%M')} "
            f"→ {' + '.join('T' + table.number for table in alternatives)}"
        )

    return moved


@main.route("/dashboard")
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

    reminders = db.session.scalars(
        db.select(InquiryReminder)
        .where(
            InquiryReminder.reminder_date == selected_date,
            InquiryReminder.completed.is_(False),
        )
        .order_by(
            InquiryReminder.reminder_kind.desc(),
            InquiryReminder.id,
        )
    ).all()

    # Large parties taking place on the selected dashboard date.
    dashboard_large_parties = db.session.scalars(
        db.select(LargePartyInquiry)
        .where(
            LargePartyInquiry.event_date == selected_date,
            LargePartyInquiry.status != "Cancelled",
        )
        .order_by(
            LargePartyInquiry.event_time.is_(None),
            LargePartyInquiry.event_time,
            LargePartyInquiry.customer_name,
        )
    ).all()

    # Reuse the saved master floor plan on the dashboard.
    floor_objects = db.session.scalars(
        db.select(FloorPlanObject)
        .order_by(FloorPlanObject.z_index, FloorPlanObject.id)
    ).all()

    floor_settings = db.session.scalar(
        db.select(FloorPlanSetting).where(
            FloorPlanSetting.name == "main"
        )
    )

    dashboard_tables = db.session.scalars(
        db.select(PubTable)
        .where(PubTable.active.is_(True))
        .order_by(*table_order_clause())
    ).all()

    # Build a small JSON-friendly booking summary for every table. A booking
    # using multiple paired tables appears against each physical table.
    dashboard_table_bookings = {
        str(table.id): []
        for table in dashboard_tables
    }

    for booking in bookings:
        start = datetime.combine(
            booking.booking_date,
            booking.booking_time
        )
        end = start + timedelta(minutes=booking.duration_minutes)

        booking_summary = {
            "booking_id": booking.id,
            "customer_name": booking.customer.name,
            "party_size": booking.party_size,
            "start_time": booking.booking_time.strftime("%H:%M"),
            "end_time": end.strftime("%H:%M"),
            "is_eating_food": bool(booking.is_eating_food),
            "completed": booking.status == "Completed",
        }

        for table in booking.tables:
            dashboard_table_bookings.setdefault(
                str(table.id), []
            ).append(booking_summary)

    # Expand every large-party reservation into physical table IDs for the map.
    dashboard_large_party_tables = {}
    dashboard_large_party_area_ids = set()

    for inquiry in dashboard_large_parties:
        reserved_table_ids = {
            link.table_id
            for link in inquiry.reserved_tables
        }

        area_ids = {
            link.area_id
            for link in inquiry.reserved_areas
        }
        dashboard_large_party_area_ids.update(area_ids)

        if area_ids:
            reserved_table_ids.update(
                db.session.scalars(
                    db.select(PubTable.id).where(
                        PubTable.area_id.in_(area_ids),
                        PubTable.active.is_(True),
                    )
                ).all()
            )

        if inquiry.reserve_for_rest_of_day:
            time_text = (
                f"{inquiry.event_time.strftime('%H:%M')} onwards"
                if inquiry.event_time
                else "Rest of day"
            )
        elif inquiry.event_time and inquiry.expected_end_time:
            time_text = (
                f"{inquiry.event_time.strftime('%H:%M')}–"
                f"{inquiry.expected_end_time.strftime('%H:%M')}"
            )
        elif inquiry.event_time:
            time_text = inquiry.event_time.strftime("%H:%M")
        else:
            time_text = "Time not confirmed"

        summary = {
            "inquiry_id": inquiry.id,
            "customer_name": inquiry.customer_name,
            "party_size": inquiry.party_size,
            "occasion": inquiry.occasion or "Large party",
            "status": inquiry.status,
            "time_text": time_text,
        }

        for table_id in reserved_table_ids:
            dashboard_large_party_tables.setdefault(
                str(table_id), []
            ).append(summary)

    return render_template(
        "dashboard.html",
        bookings=bookings,
        selected_date=selected_date,
        previous_date=selected_date - timedelta(days=1),
        next_date=selected_date + timedelta(days=1),
        repeat_target_date=repeat_target_date,
        repeat_prompts=repeat_prompts,
        reminders=reminders,
        floor_objects=floor_objects,
        floor_settings=floor_settings,
        dashboard_tables=dashboard_tables,
        dashboard_table_bookings=dashboard_table_bookings,
        dashboard_large_parties=dashboard_large_parties,
        dashboard_large_party_tables=dashboard_large_party_tables,
        dashboard_large_party_area_ids=list(dashboard_large_party_area_ids),
    )



@main.route("/bookings/<int:booking_id>/finish", methods=["POST"])
def finish_booking(booking_id):
    """
    Mark a booking as finished/left early.

    This immediately frees its assigned table(s) for subsequent allocation and
    leaves the booking visible on the dashboard as completed history.
    """
    booking = db.get_or_404(Booking, booking_id)

    if booking.status == "Cancelled":
        flash("A cancelled booking cannot be marked as finished.", "error")
        return redirect(
            url_for(
                "main.dashboard",
                date=booking.booking_date.isoformat(),
            )
        )

    booking.status = "Completed"
    booking.completed_at = datetime.now()
    db.session.commit()

    flash(
        f"{booking.customer.name}'s booking has been marked as finished.",
        "success",
    )

    return redirect(
        url_for(
            "main.dashboard",
            date=booking.booking_date.isoformat(),
        )
    )



@main.route("/large-parties/<int:inquiry_id>/delete", methods=["POST"])
def delete_cancelled_large_party(inquiry_id):
    """Permanently remove a cancelled large-party enquiry."""
    inquiry = db.get_or_404(LargePartyInquiry, inquiry_id)

    if inquiry.status != "Cancelled":
        flash(
            "Only cancelled large-party enquiries can be permanently deleted.",
            "error",
        )
        return redirect(url_for("main.archive"))

    customer_name = inquiry.customer_name
    db.session.delete(inquiry)
    db.session.commit()

    flash(
        f"Cancelled large-party enquiry for {customer_name} permanently removed.",
        "success",
    )
    return redirect(url_for("main.archive"))


@main.route("/archive")
def archive():
    """
    Archived/history screen.

    Cancelled records live here instead of cluttering active bookings and
    enquiries. Past completed bookings are also available as history.
    """
    cancelled_bookings = db.session.scalars(
        db.select(Booking)
        .where(Booking.status == "Cancelled")
        .order_by(
            Booking.booking_date.desc(),
            Booking.booking_time.desc(),
        )
    ).all()

    cancelled_large_parties = db.session.scalars(
        db.select(LargePartyInquiry)
        .where(LargePartyInquiry.status == "Cancelled")
        .order_by(
            LargePartyInquiry.event_date.desc(),
            LargePartyInquiry.created_at.desc(),
        )
    ).all()

    past_bookings = db.session.scalars(
        db.select(Booking)
        .where(
            Booking.status != "Cancelled",
            Booking.booking_date < date.today(),
        )
        .order_by(
            Booking.booking_date.desc(),
            Booking.booking_time.desc(),
        )
        .limit(250)
    ).all()

    past_large_parties = db.session.scalars(
        db.select(LargePartyInquiry)
        .where(
            LargePartyInquiry.status != "Cancelled",
            LargePartyInquiry.event_date.is_not(None),
            LargePartyInquiry.event_date < date.today(),
        )
        .order_by(
            LargePartyInquiry.event_date.desc(),
            LargePartyInquiry.event_time.desc(),
        )
        .limit(250)
    ).all()

    return render_template(
        "archive.html",
        cancelled_bookings=cancelled_bookings,
        cancelled_large_parties=cancelled_large_parties,
        past_bookings=past_bookings,
        past_large_parties=past_large_parties,
    )





# -------------------------
# Rocket Outlook connection
# -------------------------

@main.route("/auth/microsoft/connect")
def microsoft_connect():
    if not current_user().is_admin:
        flash("Administrator access is required.", "error")
        return redirect(url_for("main.dashboard"))

    if not MICROSOFT_CLIENT_ID or not MICROSOFT_CLIENT_SECRET:
        flash(
            "Microsoft Client ID / Client Secret are not configured in .env.",
            "error",
        )
        return redirect(url_for("main.users"))

    app, cache = build_cached_msal_app()

    flow = app.initiate_auth_code_flow(
        MICROSOFT_SCOPES,
        redirect_uri=MICROSOFT_REDIRECT_URI,
    )

    save_microsoft_token_cache(cache)

    # This contains OAuth state/PKCE information for the callback.
    session["microsoft_auth_flow"] = flow

    return redirect(flow["auth_uri"])


@main.route("/auth/microsoft/callback")
def microsoft_callback():
    if not current_user().is_admin:
        flash("Administrator access is required.", "error")
        return redirect(url_for("main.dashboard"))

    flow = session.pop("microsoft_auth_flow", None)

    if not flow:
        flash(
            "The Microsoft sign-in session expired. "
            "Press Connect Microsoft Email and try again.",
            "error",
        )
        return redirect(url_for("main.users"))

    app, cache = build_cached_msal_app()

    try:
        result = app.acquire_token_by_auth_code_flow(
            flow,
            request.args,
        )
    except ValueError:
        flash("Microsoft rejected the sign-in response.", "error")
        return redirect(url_for("main.users"))

    save_microsoft_token_cache(cache)

    if "access_token" not in result:
        flash(
            result.get(
                "error_description",
                "Microsoft authentication failed.",
            ),
            "error",
        )
        return redirect(url_for("main.users"))

    flash(
        "rocketpubserver@outlook.com is now connected.",
        "success",
    )

    return redirect(url_for("main.users"))


@main.route("/auth/microsoft/disconnect", methods=["POST"])
def microsoft_disconnect():
    if not current_user().is_admin:
        flash("Administrator access is required.", "error")
        return redirect(url_for("main.dashboard"))

    path = microsoft_token_cache_path()

    if os.path.exists(path):
        os.remove(path)

    session.pop("microsoft_auth_flow", None)

    flash("Rocket Email disconnected.", "success")
    return redirect(url_for("main.users"))


# -------------------------
# Email setup / verification
# -------------------------

@main.route("/my-email", methods=["GET", "POST"])
def email_setup():
    user = current_user()

    if request.method == "POST":
        action = request.form.get("action", "send")

        if action == "later":
            flash(
                "Email setup skipped for now. You can add it later from your account.",
                "success",
            )
            return redirect(url_for("main.dashboard"))

        email = (
            normalise_email(request.form.get("email"))
            if current_user().is_admin
            else ""
        )

        success, message = start_email_verification(user, email)
        flash(message, "success" if success else "error")

        if success:
            return redirect(url_for("main.verify_email"))

        return redirect(request.url)

    return render_template(
        "email_setup.html",
        first_login=request.args.get("first_login") == "1",
    )


@main.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    user = current_user()

    if not user.pending_email:
        flash("There is no email waiting to be verified.", "error")
        return redirect(url_for("main.email_setup"))

    if request.method == "POST":
        action = request.form.get("action", "verify")

        if action == "resend":
            success, message = start_email_verification(
                user,
                user.pending_email,
            )
            flash(message, "success" if success else "error")
            return redirect(request.url)

        code = request.form.get("code", "").strip()

        if (
            not user.email_verification_code_hash
            or not user.email_verification_expires_at
        ):
            flash("Request a new verification code.", "error")
            return redirect(request.url)

        if datetime.now() > user.email_verification_expires_at:
            flash(
                "That verification code has expired. Request a new one.",
                "error",
            )
            return redirect(request.url)

        if not check_password_hash(
            user.email_verification_code_hash,
            code,
        ):
            flash("Incorrect verification code.", "error")
            return redirect(request.url)

        user.email = user.pending_email
        user.pending_email = None
        user.email_verified = True
        user.email_verification_code_hash = None
        user.email_verification_expires_at = None
        db.session.commit()

        flash("Email address verified.", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("verify_email.html")


@main.route("/users/<int:user_id>/email", methods=["POST"])
def set_user_email(user_id):
    """
    Admin-only: set an email for another account and send its verification code.

    Managers can manage staff accounts, but email identity is reserved for the
    administrator because it will later be used for password recovery/security.
    """
    if not current_user().is_admin:
        flash("Administrator access is required to set user emails.", "error")
        return redirect(url_for("main.users"))

    target = db.get_or_404(AppUser, user_id)

    if target.email_verified and target.email:
        flash(
            "That user already has a verified email. Reset it first if it needs changing.",
            "error",
        )
        return redirect(url_for("main.users"))

    email = normalise_email(request.form.get("email"))

    success, message = start_email_verification(target, email)
    flash(message, "success" if success else "error")

    if success:
        flash(
            f"Enter the code sent to {email} below to verify {target.username}.",
            "success",
        )

    return redirect(url_for("main.users"))


@main.route("/users/<int:user_id>/email/verify", methods=["POST"])
def admin_verify_user_email(user_id):
    """Admin-only: enter the verification code for a user's pending email."""
    if not current_user().is_admin:
        flash("Administrator access is required.", "error")
        return redirect(url_for("main.users"))

    target = db.get_or_404(AppUser, user_id)

    if not target.pending_email:
        flash("That user has no email waiting for verification.", "error")
        return redirect(url_for("main.users"))

    code = request.form.get("code", "").strip()

    if (
        not target.email_verification_code_hash
        or not target.email_verification_expires_at
    ):
        flash("Request a new verification code for that user.", "error")
        return redirect(url_for("main.users"))

    if datetime.now() > target.email_verification_expires_at:
        flash(
            "That verification code has expired. Send a new code.",
            "error",
        )
        return redirect(url_for("main.users"))

    if not check_password_hash(
        target.email_verification_code_hash,
        code,
    ):
        flash("Incorrect verification code.", "error")
        return redirect(url_for("main.users"))

    target.email = target.pending_email
    target.pending_email = None
    target.email_verified = True
    target.email_verification_code_hash = None
    target.email_verification_expires_at = None
    db.session.commit()

    flash(
        f"{target.username}'s email has been verified.",
        "success",
    )
    return redirect(url_for("main.users"))


@main.route("/users/<int:user_id>/email/resend", methods=["POST"])
def admin_resend_user_email_code(user_id):
    """Admin-only: send a fresh code to a user's pending email."""
    if not current_user().is_admin:
        flash("Administrator access is required.", "error")
        return redirect(url_for("main.users"))

    target = db.get_or_404(AppUser, user_id)

    if not target.pending_email:
        flash("That user has no pending email.", "error")
        return redirect(url_for("main.users"))

    success, message = start_email_verification(
        target,
        target.pending_email,
    )
    flash(message, "success" if success else "error")

    return redirect(url_for("main.users"))


@main.route("/users/<int:user_id>/email/reset", methods=["POST"])
def reset_user_email(user_id):
    """
    Admin-only: remove a user's verified/pending email so a new one can be set.
    """
    if not current_user().is_admin:
        flash("Administrator access is required to reset user emails.", "error")
        return redirect(url_for("main.users"))

    target = db.get_or_404(AppUser, user_id)

    target.email = None
    target.pending_email = None
    target.email_verified = False
    target.email_verification_code_hash = None
    target.email_verification_expires_at = None
    db.session.commit()

    flash(
        f"{target.username}'s email has been reset.",
        "success",
    )
    return redirect(url_for("main.users"))


# -------------------------
# Users
# -------------------------

@main.route("/users")
def users():
    if not current_user().is_manager:
        flash("Manager access is required.", "error")
        return redirect(url_for("main.dashboard"))

    stmt = db.select(AppUser).order_by(
        AppUser.role.desc(),
        AppUser.username,
    )

    if current_user().role == "manager":
        # Managers can see staff and other managers, but not administrators.
        # Existing edit permissions still prevent managers changing each other.
        stmt = stmt.where(AppUser.role != "admin")

    user_list = db.session.scalars(stmt).all()

    return render_template(
        "users.html",
        users=user_list,
        microsoft_email_connected=(
            microsoft_email_connected()
            if current_user().is_admin
            else False
        ),
    )


@main.route("/users/new", methods=["GET", "POST"])
def new_user():
    if not current_user().is_manager:
        flash("Manager access is required.", "error")
        return redirect(url_for("main.dashboard"))

    allowed_roles = (
        ["staff", "manager"]
        if current_user().is_admin
        else ["staff"]
    )

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        role = request.form.get("role", "staff").strip()
        email = (
            normalise_email(request.form.get("email"))
            if current_user().is_admin
            else None
        )

        if not username:
            flash("Enter a username.", "error")
            return redirect(request.url)

        if role not in allowed_roles:
            flash("You cannot create that account type.", "error")
            return redirect(request.url)

        existing = db.session.scalar(
            db.select(AppUser).where(
                db.func.lower(AppUser.username) == username.lower()
            )
        )

        if existing:
            flash("That username is already in use.", "error")
            return redirect(request.url)

        user = AppUser(
            username=username,
            password_hash=generate_password_hash("Password"),
            role=role,
            must_change_password=True,
            active=True,
        )
        db.session.add(user)
        db.session.commit()

        flash(
            f"{username} created. Their temporary password is Password.",
            "success",
        )

        if email:
            success, message = start_email_verification(user, email)
            flash(message, "success" if success else "error")

        return redirect(url_for("main.users"))

    return render_template(
        "user_form.html",
        allowed_roles=allowed_roles,
        can_set_email=current_user().is_admin,
    )


@main.route("/users/<int:user_id>/rename", methods=["POST"])
def rename_user(user_id):
    if not current_user().is_manager:
        flash("Manager access is required.", "error")
        return redirect(url_for("main.dashboard"))

    target = db.get_or_404(AppUser, user_id)

    # Managers can rename staff. Admin can rename staff/managers.
    if target.is_admin and not current_user().is_admin:
        flash("Managers cannot rename administrator accounts.", "error")
        return redirect(url_for("main.users"))

    if target.role == "manager" and not current_user().is_admin:
        flash("Only an administrator can rename a manager.", "error")
        return redirect(url_for("main.users"))

    new_name = request.form.get("username", "").strip()

    if not new_name:
        flash("Enter a name.", "error")
        return redirect(url_for("main.users"))

    duplicate = db.session.scalar(
        db.select(AppUser).where(
            db.func.lower(AppUser.username) == new_name.lower(),
            AppUser.id != target.id,
        )
    )

    if duplicate:
        flash("That name is already in use.", "error")
        return redirect(url_for("main.users"))

    old_name = target.username
    target.username = new_name

    # If this login is linked to a rota profile, keep the displayed rota name
    # in sync with the account name.
    linked_profile = db.session.scalar(
        db.select(StaffProfile).where(
            StaffProfile.user_id == target.id
        )
    )

    if linked_profile:
        linked_profile.display_name = new_name

    db.session.commit()

    flash(f"{old_name} renamed to {new_name}.", "success")
    return redirect(url_for("main.users"))


@main.route("/users/<int:user_id>/reset-password", methods=["POST"])
def reset_user_password(user_id):
    if not current_user().is_manager:
        flash("Manager access is required.", "error")
        return redirect(url_for("main.dashboard"))

    target = db.get_or_404(AppUser, user_id)

    if target.is_admin and not current_user().is_admin:
        flash("Managers cannot change administrator accounts.", "error")
        return redirect(url_for("main.users"))

    if target.role == "manager" and not current_user().is_admin:
        flash("Only an administrator can reset a manager.", "error")
        return redirect(url_for("main.users"))

    target.password_hash = generate_password_hash("Password")
    target.must_change_password = True
    db.session.commit()

    flash(
        f"{target.username}'s password was reset to Password.",
        "success",
    )
    return redirect(url_for("main.users"))


@main.route("/users/<int:user_id>/delete", methods=["POST"])
def delete_user(user_id):
    if not current_user().is_manager:
        flash("Manager access is required.", "error")
        return redirect(url_for("main.dashboard"))

    target = db.get_or_404(AppUser, user_id)

    if target.id == current_user().id:
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("main.users"))

    if target.is_admin:
        flash("Administrator accounts cannot be deleted.", "error")
        return redirect(url_for("main.users"))

    # Managers may delete staff users. Admin may delete staff or manager users.
    if current_user().role == "manager" and target.role != "staff":
        flash("Managers can only delete staff accounts.", "error")
        return redirect(url_for("main.users"))

    # Preserve the rota person and all rota/diary history; only the login goes.
    profile = db.session.scalar(
        db.select(StaffProfile).where(
            StaffProfile.user_id == target.id
        )
    )

    if profile:
        profile.user_id = None

    for week in db.session.scalars(
        db.select(RotaWeek).where(
            db.or_(
                RotaWeek.created_by_user_id == target.id,
                RotaWeek.published_by_user_id == target.id,
            )
        )
    ).all():
        if week.created_by_user_id == target.id:
            week.created_by_user_id = None
        if week.published_by_user_id == target.id:
            week.published_by_user_id = None

    for entry in db.session.scalars(
        db.select(StaffDiaryEntry).where(
            db.or_(
                StaffDiaryEntry.created_by_user_id == target.id,
                StaffDiaryEntry.reviewed_by_user_id == target.id,
            )
        )
    ).all():
        if entry.created_by_user_id == target.id:
            entry.created_by_user_id = None
        if entry.reviewed_by_user_id == target.id:
            entry.reviewed_by_user_id = None

    for swap in db.session.scalars(
        db.select(ShiftSwapRequest).where(
            ShiftSwapRequest.manager_user_id == target.id
        )
    ).all():
        swap.manager_user_id = None

    username = target.username
    db.session.delete(target)
    db.session.commit()

    flash(f"{username}'s user account was deleted.", "success")
    return redirect(url_for("main.users"))


@main.route("/users/<int:user_id>/toggle", methods=["POST"])
def toggle_user(user_id):
    if not current_user().is_manager:
        flash("Manager access is required.", "error")
        return redirect(url_for("main.dashboard"))

    target = db.get_or_404(AppUser, user_id)

    if target.id == current_user().id:
        flash("You cannot disable your own account.", "error")
        return redirect(url_for("main.users"))

    if target.is_admin and not current_user().is_admin:
        flash("Managers cannot change administrator accounts.", "error")
        return redirect(url_for("main.users"))

    if target.role == "manager" and not current_user().is_admin:
        flash("Only an administrator can disable a manager.", "error")
        return redirect(url_for("main.users"))

    target.active = not target.active
    db.session.commit()

    flash(
        f"{target.username} is now {'active' if target.active else 'disabled'}.",
        "success",
    )
    return redirect(url_for("main.users"))


@main.route("/users/<int:user_id>/role", methods=["POST"])
def change_user_role(user_id):
    if not current_user().is_admin:
        flash("Administrator access is required.", "error")
        return redirect(url_for("main.users"))

    target = db.get_or_404(AppUser, user_id)
    role = request.form.get("role", "").strip()

    if target.id == current_user().id:
        flash("You cannot change your own administrator role.", "error")
        return redirect(url_for("main.users"))

    if role not in {"staff", "manager"}:
        flash("Choose Staff or Manager.", "error")
        return redirect(url_for("main.users"))

    target.role = role
    db.session.commit()

    flash(
        f"{target.username} is now a {role}.",
        "success",
    )
    return redirect(url_for("main.users"))




# ============================================================
# Rota / Staff Diary
# ============================================================

WEEKDAY_NAMES = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
]


def sunday_for_date(value):
    """Return the Sunday starting the rota week containing value."""
    days_since_sunday = (value.weekday() + 1) % 7
    return value - timedelta(days=days_since_sunday)


def current_staff_profile():
    user = current_user()
    if not user:
        return None

    profile = db.session.scalar(
        db.select(StaffProfile).where(
            StaffProfile.user_id == user.id
        )
    )

    if profile:
        return profile

    # Every rota member now has a login. Older rota profiles may pre-date
    # those accounts, so link them automatically by matching the name.
    profile = db.session.scalar(
        db.select(StaffProfile).where(
            db.func.lower(StaffProfile.display_name)
            == user.username.lower()
        )
    )

    if profile and profile.user_id is None:
        profile.user_id = user.id
        db.session.commit()

    return profile


def time_label(value):
    if value is None:
        return ""
    hour = value.hour
    minute = value.minute
    suffix = ""
    display_hour = hour
    if hour == 0:
        display_hour = 12
    elif hour > 12:
        display_hour = hour - 12
    return (
        str(display_hour)
        if minute == 0
        else f"{display_hour}:{minute:02d}"
    )


def shift_label(shift):
    if shift.note == "__ROTA_K__":
        return "K"

    end = "F" if shift.end_is_finish else time_label(shift.end_time)
    return f"{time_label(shift.start_time)}-{end}"


def estimated_finish_for_date(shift_date):
    row = db.session.scalar(
        db.select(RotaFinishSetting).where(
            RotaFinishSetting.weekday == shift_date.weekday()
        )
    )
    return row.estimated_finish if row else None


def projected_shift_hours(shift):
    """
    Estimate a shift length. F uses the weekday's configurable estimate.
    Midnight is treated as the following day.
    """
    end = (
        estimated_finish_for_date(shift.shift_date)
        if shift.end_is_finish
        else shift.end_time
    )
    if not end:
        return 0

    start_minutes = shift.start_time.hour * 60 + shift.start_time.minute
    end_minutes = end.hour * 60 + end.minute

    if end_minutes <= start_minutes:
        end_minutes += 24 * 60

    return round((end_minutes - start_minutes) / 60, 2)


def availability_for(profile, target_date):
    """
    Availability is now controlled only by date-specific Staff Diary entries.

    Recurring weekday availability/profile-hour rules are no longer used.
    """
    entries = db.session.scalars(
        db.select(StaffDiaryEntry).where(
            StaffDiaryEntry.staff_id == profile.id,
            StaffDiaryEntry.entry_date == target_date,
            StaffDiaryEntry.status.in_(["approved", "info"]),
        )
    ).all()

    for entry in entries:
        if entry.entry_type in {"day_off_request", "unavailable"}:
            return False, None, None, entry.note or "Unavailable"

    for entry in entries:
        if entry.entry_type == "available_window":
            return (
                True,
                entry.available_from,
                entry.available_until,
                entry.note or "Date-specific availability",
            )

    return True, None, None, None


def time_within_window(start, end, earliest, latest, end_is_finish=False):
    if earliest and start < earliest:
        return False

    if latest:
        comparison_end = end
        if end_is_finish:
            # We cannot know the real F, so use the estimated finish elsewhere.
            comparison_end = None

        if comparison_end and comparison_end > latest:
            return False

    return True


def historical_pattern_bonus(profile, weekday, start_time, end_is_finish):
    """
    Lightweight pattern prior inferred from the supplied June-August rotas.

    This never overrides availability. It only helps rank otherwise suitable
    staff for a suggested shift.
    """
    name = profile.rota_name.strip().lower()
    bonus = 0

    # Brooke: Mon-Wed daytime, often Friday close.
    if name == "brooke":
        if weekday in {0, 1, 2} and start_time.hour == 12:
            bonus += 34
        if weekday == 4 and end_is_finish:
            bonus += 24

    # Niamh: evening/finish heavy.
    if name == "niamh":
        if start_time.hour >= 17:
            bonus += 30
        if end_is_finish:
            bonus += 18

    # Lois: 3-8 / 5-F patterns; kitchen markings are handled by role matching.
    if name == "lois":
        if start_time.hour in {15, 17}:
            bonus += 22

    # Jenna/Maggie: regular Sunday daytime presence.
    if name in {"jenna", "maggie"} and weekday == 6 and start_time.hour <= 12:
        bonus += 28

    # Kieran and Scott: later-week/evening heavy.
    if name in {"kieran", "scott"}:
        if weekday in {3, 4, 5, 6} and start_time.hour >= 15:
            bonus += 28
        if weekday in {4, 5} and end_is_finish:
            bonus += 16

    # Casual staff are intentionally not aggressively selected.
    if profile.employment_type == "casual":
        bonus -= 18

    # Glass collector: Friday-Sunday evening.
    if profile.work_role == "glass_collector":
        if weekday in {4, 5, 6} and start_time.hour >= 17:
            bonus += 35
        else:
            bonus -= 50

    return bonus


def role_compatible(profile, role):
    if role == "front_of_house":
        return profile.work_role in {"front_of_house", "both"}
    if role == "kitchen":
        return profile.work_role in {"kitchen", "both"}
    if role == "glass_collector":
        return profile.work_role == "glass_collector"
    return False


def projected_hours_for_profile(profile, week):
    return round(
        sum(
            projected_shift_hours(shift)
            for shift in week.shifts
            if shift.staff_id == profile.id
        ),
        2,
    )


def rota_candidate_score(profile, week, target_date, start, end, end_is_finish, role="front_of_house"):
    available, earliest, latest, _ = availability_for(profile, target_date)

    if not available:
        return None

    effective_end = (
        estimated_finish_for_date(target_date)
        if end_is_finish
        else end
    )

    if not time_within_window(
        start,
        effective_end,
        earliest,
        latest,
        end_is_finish=False,
    ):
        return None

    # Never give the same person two Auto-fill slots on one day.
    if any(
        s.staff_id == profile.id and s.shift_date == target_date
        for s in week.shifts
    ):
        return None

    hours_so_far = projected_hours_for_profile(profile, week)

    dummy = type("ShiftLike", (), {
        "shift_date": target_date,
        "start_time": start,
        "end_time": end,
        "end_is_finish": end_is_finish,
    })()
    shift_hours = projected_shift_hours(dummy)

    if profile.max_hours and hours_so_far + shift_hours > profile.max_hours:
        return None

    # Base score is deliberately modest. Strong observed-pattern bonuses are
    # what should drive the suggestion rather than handing everyone shifts.
    score = 10

    score += historical_pattern_bonus(
        profile,
        target_date.weekday(),
        start,
        end_is_finish,
    )
    score += preferred_shift_match_bonus(
        profile,
        start,
        end,
        end_is_finish,
    )

    # Prefer staff with fewer assigned hours so one person cannot absorb the
    # entire week (the old Auto-fill problem).
    score -= hours_so_far * 2.2

    # Occasional staff are still available, but only used when they score well
    # or regular staff cannot cover the slot.
    if profile.rota_name.lower() in {"erin", "hannah", "leoni", "charl"}:
        score -= 35

    # Alara is Friday-Sunday only and generally late.
    if profile.rota_name.lower() == "alara":
        if target_date.weekday() not in {4, 5, 6}:
            return None
        if start.hour < 17:
            score -= 30
        else:
            score += 18

    return score




def parse_rota_shift_text(value):
    """
    Parse rota shorthand such as 5-9, 12-6, 4-F and K.
    """
    value = (value or "").strip().upper().replace(" ", "")

    if value == "K":
        # K is a rota code rather than a timed shift. The placeholder noon
        # start is never displayed; shift_label() returns K from the marker.
        return time(12, 0), None, False

    if not value or "-" not in value:
        raise ValueError("Enter a shift time or K.")

    start_text, end_text = value.split("-", 1)

    def parse_clock(text_value):
        if ":" in text_value:
            h_text, m_text = text_value.split(":", 1)
            hour = int(h_text)
            minute = int(m_text)
        else:
            hour = int(text_value)
            minute = 0

        if minute < 0 or minute > 59:
            raise ValueError("Invalid minutes.")

        if 1 <= hour <= 11:
            hour += 12
        elif hour == 12:
            hour = 12
        elif hour < 0 or hour > 23:
            raise ValueError("Invalid hour.")

        return time(hour, minute)

    start = parse_clock(start_text)

    if end_text == "F":
        return start, None, True

    end = parse_clock(end_text)
    return start, end, False


def preferred_shift_match_bonus(profile, start, end, end_is_finish):
    hints = [
        part.strip().upper()
        for part in (profile.preferred_shifts or "").split(",")
        if part.strip()
    ]

    if not hints:
        return 0

    candidate = (
        f"{time_label(start)}-F"
        if end_is_finish
        else f"{time_label(start)}-{time_label(end)}"
    ).upper()

    return 26 if candidate in hints else 0


def rota_context(week):
    # Active staff always appear. Archived staff appear only when they actually
    # hold a shift in this rota week (for example after accepting a cover
    # request). This keeps the normal rota tidy while still showing the real
    # post-swap assignment.
    week_staff_ids = {
        shift.staff_id
        for shift in week.shifts
        if shift.staff_id is not None
    }

    profiles = db.session.scalars(
        db.select(StaffProfile)
        .where(
            db.or_(
                StaffProfile.active.is_(True),
                StaffProfile.id.in_(week_staff_ids) if week_staff_ids else False,
            )
        )
        .order_by(
            StaffProfile.active.desc(),
            StaffProfile.sort_order,
            StaffProfile.display_name,
        )
    ).all()

    days = [week.week_start + timedelta(days=i) for i in range(7)]

    shift_map = {
        (profile.id, day): []
        for profile in profiles
        for day in days
    }

    for shift in week.shifts:
        if (shift.staff_id, shift.shift_date) in shift_map:
            shift_map[(shift.staff_id, shift.shift_date)].append(shift)

    return profiles, days, shift_map


@main.route("/rota")
def rota_home():
    selected_text = request.args.get("week")
    if selected_text:
        try:
            selected = datetime.strptime(selected_text, "%Y-%m-%d").date()
        except ValueError:
            selected = date.today()
    else:
        selected = date.today()

    week_start = sunday_for_date(selected)

    week = db.session.scalar(
        db.select(RotaWeek).where(
            RotaWeek.week_start == week_start
        )
    )

    # Staff only see an issued rota. Managers can see drafts too.
    if week and week.status == "draft" and not current_user().is_manager:
        week = None

    previous_start = week_start - timedelta(days=7)
    next_start = week_start + timedelta(days=7)

    my_profile = current_staff_profile()
    my_shifts = []

    if week and my_profile:
        my_shifts = sorted(
            [
                shift for shift in week.shifts
                if shift.staff_id == my_profile.id
            ],
            key=lambda s: (s.shift_date, s.start_time),
        )

    profiles = days = shift_map = None
    if week:
        profiles, days, shift_map = rota_context(week)

    swaps = []
    if my_profile:
        swaps = db.session.scalars(
            db.select(ShiftSwapRequest)
            .where(
                db.or_(
                    ShiftSwapRequest.requester_staff_id == my_profile.id,
                    ShiftSwapRequest.target_staff_id == my_profile.id,
                )
            )
            .order_by(ShiftSwapRequest.created_at.desc())
        ).all()

    pending_swaps = db.session.scalars(
        db.select(ShiftSwapRequest).where(
            ShiftSwapRequest.status == "pending_target",
            ShiftSwapRequest.requester_shift.has(
                RotaShift.rota_week_id == week.id
            ) if week else False,
        )
    ).all() if week else []

    pending_shift_ids = set()
    pending_staff_ids = set()

    for pending_swap in pending_swaps:
        if pending_swap.requester_shift_id:
            pending_shift_ids.add(pending_swap.requester_shift_id)
        if pending_swap.target_shift_id:
            pending_shift_ids.add(pending_swap.target_shift_id)

        if pending_swap.requester_staff_id:
            pending_staff_ids.add(pending_swap.requester_staff_id)
        if pending_swap.target_staff_id:
            pending_staff_ids.add(pending_swap.target_staff_id)

    swap_profiles = db.session.scalars(
        db.select(StaffProfile)
        .order_by(
            StaffProfile.active.desc(),
            StaffProfile.sort_order,
            StaffProfile.display_name,
        )
    ).all()

    # `rota_name` is a Python property because linked profiles display the
    # current username. It cannot be used in SQL ORDER BY. Sort once the rows
    # are loaded so the picker still displays alphabetically by the actual
    # rota name inside active/archived groups.
    swap_profiles = sorted(
        swap_profiles,
        key=lambda profile: (
            0 if profile.active else 1,
            (profile.rota_name or "").lower(),
        ),
    )

    return render_template(
        "rota.html",
        week=week,
        week_start=week_start,
        previous_start=previous_start,
        next_start=next_start,
        profiles=profiles or [],
        days=days or [week_start + timedelta(days=i) for i in range(7)],
        shift_map=shift_map or {},
        my_profile=my_profile,
        my_shifts=my_shifts,
        swaps=swaps,
        shift_label=shift_label,
        pending_shift_ids=pending_shift_ids,
        pending_staff_ids=pending_staff_ids,
        swap_profiles=swap_profiles,
    )


@main.route("/rota/create", methods=["POST"])
def rota_create():
    start_text = request.form.get("week_start", "")
    try:
        chosen = datetime.strptime(start_text, "%Y-%m-%d").date()
    except ValueError:
        flash("Choose a valid week.", "error")
        return redirect(url_for("main.rota_home"))

    chosen = sunday_for_date(chosen)

    week = db.session.scalar(
        db.select(RotaWeek).where(RotaWeek.week_start == chosen)
    )

    if week is None:
        week = RotaWeek(
            week_start=chosen,
            status="draft",
            created_by_user_id=current_user().id,
        )
        db.session.add(week)
        db.session.commit()

    return redirect(url_for("main.rota_edit", rota_id=week.id))


@main.route("/rota/<int:rota_id>/edit")
def rota_edit(rota_id):
    week = db.get_or_404(RotaWeek, rota_id)
    profiles, days, shift_map = rota_context(week)

    diary_by_day = {}
    cell_diary = {}

    for day in days:
        entries = db.session.scalars(
            db.select(StaffDiaryEntry)
            .where(
                StaffDiaryEntry.entry_date == day,
                StaffDiaryEntry.status.in_(
                    ["approved", "info", "requested"]
                ),
            )
            .order_by(StaffDiaryEntry.created_at)
        ).all()

        diary_by_day[day] = entries

        for entry in entries:
            if entry.staff_id is None:
                continue

            key = (entry.staff_id, day)
            state = cell_diary.setdefault(
                key,
                {
                    "unavailable": False,
                    "unavailable_status": None,
                    "availability": [],
                },
            )

            if entry.entry_type in {
                "day_off_request",
                "unavailable",
            }:
                state["unavailable"] = True
                state["unavailable_status"] = entry.status

            elif entry.entry_type == "available_window":
                # The first part of note stores the original rota-style
                # shorthand, e.g. "4-9" or "5-F".
                availability_text = None

                if entry.note:
                    possible_shift = entry.note.split(" · ", 1)[0].strip()

                    if "-" in possible_shift:
                        availability_text = possible_shift

                if not availability_text:
                    if entry.available_from or entry.available_until:
                        start_label = (
                            time_label(entry.available_from)
                            if entry.available_from
                            else "Any"
                        )
                        end_label = (
                            time_label(entry.available_until)
                            if entry.available_until
                            else "F"
                        )
                        availability_text = (
                            f"{start_label}-{end_label}"
                        )
                    else:
                        availability_text = "Available"

                # If this exact requested shift has already been added to
                # the rota, do not show the availability suggestion as a
                # second visual slot in the same cell.
                existing_shift_labels = {
                    shift_label(existing_shift).upper()
                    for existing_shift in shift_map.get(key, [])
                }

                if availability_text.upper() not in existing_shift_labels:
                    state["availability"].append(
                        {
                            "id": entry.id,
                            "text": availability_text,
                            "status": entry.status,
                            "note": entry.note,
                        }
                    )

    archived_staff = db.session.scalars(
        db.select(StaffProfile)
        .where(
            StaffProfile.active.is_(False),
            db.func.lower(StaffProfile.display_name) != "matt",
        )
        .order_by(StaffProfile.sort_order, StaffProfile.display_name)
    ).all()

    return render_template(
        "rota_edit.html",
        week=week,
        profiles=profiles,
        archived_staff=archived_staff,
        days=days,
        shift_map=shift_map,
        diary_by_day=diary_by_day,
        cell_diary=cell_diary,
        shift_label=shift_label,
    )


def parse_shift_form():
    shift_date = datetime.strptime(
        request.form["shift_date"],
        "%Y-%m-%d",
    ).date()

    start_time, end_time, end_is_finish = parse_rota_shift_text(
        request.form.get("shift_text", "")
    )

    return shift_date, start_time, end_time, end_is_finish


@main.route(
    "/rota/<int:rota_id>/availability/<int:entry_id>/use",
    methods=["POST"],
)
def rota_use_availability(rota_id, entry_id):
    """
    Put a Staff Diary specific-shift request straight onto the rota.

    The manager clicks + beside A 4-8 / A 5-F. The diary request is approved
    at the same time because the requested shift has been accepted.
    """
    week = db.get_or_404(RotaWeek, rota_id)
    entry = db.get_or_404(StaffDiaryEntry, entry_id)

    if (
        entry.entry_type != "available_window"
        or entry.staff_id is None
        or not (
            week.week_start
            <= entry.entry_date
            <= week.week_start + timedelta(days=6)
        )
    ):
        flash("That availability request cannot be added to this rota.", "error")
        return redirect(url_for("main.rota_edit", rota_id=week.id))

    shift_text = None

    if entry.note:
        possible_shift = entry.note.split(" · ", 1)[0].strip()

        if "-" in possible_shift:
            shift_text = possible_shift

    if not shift_text:
        if not entry.available_from:
            flash("That availability request has no shift time.", "error")
            return redirect(url_for("main.rota_edit", rota_id=week.id))

        start_text = time_label(entry.available_from)
        end_text = (
            time_label(entry.available_until)
            if entry.available_until
            else "F"
        )
        shift_text = f"{start_text}-{end_text}"

    try:
        start_time, end_time, end_is_finish = parse_rota_shift_text(
            shift_text
        )
    except ValueError:
        flash("That requested shift time is invalid.", "error")
        return redirect(url_for("main.rota_edit", rota_id=week.id))

    # Do not create a duplicate shift in the same staff/date cell.
    existing = db.session.scalar(
        db.select(RotaShift).where(
            RotaShift.rota_week_id == week.id,
            RotaShift.staff_id == entry.staff_id,
            RotaShift.shift_date == entry.entry_date,
        )
    )

    if existing:
        flash("That staff member already has a shift on this day.", "error")
        return redirect(url_for("main.rota_edit", rota_id=week.id))

    db.session.add(
        RotaShift(
            rota_week_id=week.id,
            staff_id=entry.staff_id,
            shift_date=entry.entry_date,
            start_time=start_time,
            end_time=end_time,
            end_is_finish=end_is_finish,
            shift_role="front_of_house",
            note=None,
            auto_suggested=False,
        )
    )

    if entry.status == "requested":
        entry.status = "approved"
        entry.reviewed_by_user_id = current_user().id
        entry.reviewed_at = datetime.now()

    db.session.commit()

    flash(
        f"{entry.staff.display_name}'s {shift_text} availability added to the rota.",
        "success",
    )
    return redirect(url_for("main.rota_edit", rota_id=week.id))


@main.route("/rota/<int:rota_id>/save", methods=["POST"])
def rota_save_draft(rota_id):
    """
    Save the whole on-screen rota in one transaction.

    Cell editors are intentionally client-side until this button is pressed,
    avoiding a page refresh for every individual time entry.
    """
    week = db.get_or_404(RotaWeek, rota_id)
    state_text = request.form.get("rota_state", "[]")

    try:
        rows = json.loads(state_text)
    except json.JSONDecodeError:
        flash("The rota draft could not be read.", "error")
        return redirect(url_for("main.rota_edit", rota_id=week.id))

    if not isinstance(rows, list):
        flash("The rota draft is invalid.", "error")
        return redirect(url_for("main.rota_edit", rota_id=week.id))

    profiles = {
        p.id: p
        for p in db.session.scalars(
            db.select(StaffProfile).where(StaffProfile.active.is_(True))
        ).all()
    }

    parsed = []

    try:
        for row in rows:
            staff_id = int(row["staff_id"])
            shift_date = datetime.strptime(
                row["date"],
                "%Y-%m-%d",
            ).date()

            if staff_id not in profiles:
                continue

            if not (
                week.week_start
                <= shift_date
                <= week.week_start + timedelta(days=6)
            ):
                raise ValueError("A shift is outside this rota week.")

            shift_values = row.get("shifts", [])
            if not isinstance(shift_values, list):
                raise ValueError("Invalid shift data.")

            for shift_text in shift_values:
                shift_text = str(shift_text or "").strip().upper()
                if not shift_text:
                    continue

                start, end, is_finish = parse_rota_shift_text(shift_text)

                available, _, _, reason = availability_for(
                    profiles[staff_id],
                    shift_date,
                )

                if not available:
                    raise ValueError(
                        f"{profiles[staff_id].rota_name} is unavailable "
                        f"on {shift_date.strftime('%a %d %b')}: "
                        f"{reason or 'Unavailable'}."
                    )

                parsed.append(
                    (
                        staff_id,
                        shift_date,
                        shift_text,
                        start,
                        end,
                        is_finish,
                    )
                )
    except (KeyError, TypeError, ValueError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("main.rota_edit", rota_id=week.id))

    # The browser state is authoritative for this week.
    db.session.query(RotaShift).filter(
        RotaShift.rota_week_id == week.id
    ).delete(synchronize_session=False)

    for staff_id, shift_date, shift_text, start, end, is_finish in parsed:
        db.session.add(
            RotaShift(
                rota_week_id=week.id,
                staff_id=staff_id,
                shift_date=shift_date,
                start_time=start,
                end_time=end,
                end_is_finish=is_finish,
                shift_role="front_of_house",
                note="__ROTA_K__" if shift_text == "K" else None,
                auto_suggested=False,
            )
        )

    if request.form.get("issue") == "1":
        week.status = "published"
        week.published_at = datetime.now()
        week.published_by_user_id = current_user().id
        message = "Rota saved and issued to staff."
        destination = url_for(
            "main.rota_home",
            week=week.week_start.isoformat(),
        )
    else:
        message = (
            "Rota draft saved."
            if week.status == "draft"
            else "Rota changes saved."
        )
        destination = url_for("main.rota_edit", rota_id=week.id)

    db.session.commit()

    if request.headers.get("X-Rota-Autosave") == "1":
        return jsonify(
            {
                "ok": True,
                "status": week.status,
                "saved_at": datetime.now().strftime("%H:%M:%S"),
            }
        )

    flash(message, "success")
    return redirect(destination)


@main.route("/rota/<int:rota_id>/shift/add", methods=["POST"])
def rota_add_shift(rota_id):
    week = db.get_or_404(RotaWeek, rota_id)

    try:
        shift_date, start, end, is_finish = parse_shift_form()
        staff_id = int(request.form["staff_id"])
    except KeyError:
        flash("Check the shift details.", "error")
        return redirect(url_for("main.rota_edit", rota_id=rota_id))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("main.rota_edit", rota_id=rota_id))

    if not (
        week.week_start
        <= shift_date
        <= week.week_start + timedelta(days=6)
    ):
        flash("That date is outside this rota week.", "error")
        return redirect(url_for("main.rota_edit", rota_id=rota_id))

    profile = db.get_or_404(StaffProfile, staff_id)

    available, earliest, latest, reason = availability_for(
        profile,
        shift_date,
    )

    if not available:
        flash(
            f"{profile.rota_name} is marked unavailable: {reason or 'Unavailable'}.",
            "error",
        )
        return redirect(url_for("main.rota_edit", rota_id=rota_id))

    raw_shift_text = request.form.get("shift_text", "").strip().upper()

    db.session.add(
        RotaShift(
            rota_week_id=week.id,
            staff_id=profile.id,
            shift_date=shift_date,
            start_time=start,
            end_time=end,
            end_is_finish=is_finish,
            shift_role="front_of_house",
            note="__ROTA_K__" if raw_shift_text == "K" else None,
        )
    )
    db.session.commit()

    return redirect(url_for("main.rota_edit", rota_id=rota_id))


@main.route("/rota/shift/<int:shift_id>/edit", methods=["POST"])
def rota_edit_shift(shift_id):
    shift = db.get_or_404(RotaShift, shift_id)

    try:
        _, start, end, is_finish = parse_shift_form()
    except KeyError:
        flash("Check the shift details.", "error")
        return redirect(url_for("main.rota_edit", rota_id=shift.rota_week_id))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("main.rota_edit", rota_id=shift.rota_week_id))

    raw_shift_text = request.form.get("shift_text", "").strip().upper()

    shift.start_time = start
    shift.end_time = end
    shift.end_is_finish = is_finish
    shift.note = "__ROTA_K__" if raw_shift_text == "K" else None
    shift.auto_suggested = False

    db.session.commit()

    return redirect(url_for("main.rota_edit", rota_id=shift.rota_week_id))


@main.route("/rota/shift/<int:shift_id>/delete", methods=["POST"])
def rota_delete_shift(shift_id):
    shift = db.get_or_404(RotaShift, shift_id)
    rota_id = shift.rota_week_id
    db.session.delete(shift)
    db.session.commit()
    return redirect(url_for("main.rota_edit", rota_id=rota_id))


@main.route("/rota/<int:rota_id>/clear", methods=["POST"])
def rota_clear_draft(rota_id):
    week = db.get_or_404(RotaWeek, rota_id)

    if week.status != "draft":
        flash(
            "Only a draft rota can be cleared. Return it to draft first.",
            "error",
        )
        return redirect(url_for("main.rota_edit", rota_id=week.id))

    shifts = db.session.scalars(
        db.select(RotaShift).where(
            RotaShift.rota_week_id == week.id
        )
    ).all()

    removed = len(shifts)

    for shift in shifts:
        db.session.delete(shift)

    db.session.commit()

    flash(
        f"Rota draft cleared. {removed} shift"
        f"{'' if removed == 1 else 's'} removed.",
        "success",
    )
    return redirect(url_for("main.rota_edit", rota_id=week.id))


@main.route("/rota/<int:rota_id>/publish", methods=["POST"])
def rota_publish(rota_id):
    week = db.get_or_404(RotaWeek, rota_id)
    week.status = "published"
    week.published_at = datetime.now()
    week.published_by_user_id = current_user().id
    db.session.commit()

    flash("Rota issued to staff.", "success")
    return redirect(url_for("main.rota_home", week=week.week_start.isoformat()))


@main.route("/rota/<int:rota_id>/return-to-draft", methods=["POST"])
def rota_return_to_draft(rota_id):
    if not current_user().is_manager:
        flash("Manager access is required.", "error")
        return redirect(url_for("main.rota_home"))

    week = db.get_or_404(RotaWeek, rota_id)
    week.status = "draft"
    db.session.commit()

    flash("Rota returned to draft.", "success")
    return redirect(url_for("main.rota_edit", rota_id=rota_id))


@main.route("/rota/<int:rota_id>/image")
def rota_image(rota_id):
    week = db.get_or_404(RotaWeek, rota_id)

    if week.status != "published" and not current_user().is_manager:
        flash("That rota has not been issued.", "error")
        return redirect(url_for("main.rota_home"))

    profiles, days, shift_map = rota_context(week)

    # High-resolution, phone-friendly PNG generated locally.
    width = 2200
    row_h = 92
    header_h = 220
    bottom_padding = 40

    # One row is used by the Sun-Sat column headings in addition to every
    # staff row. Include it in the canvas height so nobody is clipped.
    table_rows = max(len(profiles), 1) + 1
    height = header_h + (table_rows * row_h) + bottom_padding

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    try:
        title_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 60)
        head_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 34)
        text_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 30)
        small_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 24)
    except Exception:
        title_font = ImageFont.load_default()
        head_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    deep = (14, 53, 40)
    pale = (236, 245, 234)
    line = (190, 205, 194)
    text = (25, 48, 37)

    draw.rectangle((0, 0, width, 130), fill=deep)
    draw.text(
        (55, 32),
        "THE ROCKET PUB — STAFF ROTA",
        fill="white",
        font=title_font,
    )

    draw.text(
        (55, 150),
        f"Week from Sunday {week.week_start.strftime('%d %B %Y')}",
        fill=text,
        font=head_font,
    )

    name_w = 330
    day_w = (width - name_w - 80) // 7
    x0 = 40
    y0 = header_h

    headers = ["Staff"] + [d.strftime("%a\n%d") for d in days]
    widths = [name_w] + [day_w]*7

    x = x0
    for label, col_w in zip(headers, widths):
        draw.rectangle((x, y0, x+col_w, y0+row_h), fill=pale, outline=line, width=2)
        draw.multiline_text(
            (x+12, y0+18),
            label,
            fill=text,
            font=head_font if label in {"Staff", "Hours"} else small_font,
            spacing=4,
        )
        x += col_w

    y = y0 + row_h

    for profile in profiles:
        x = x0
        draw.rectangle((x, y, x+name_w, y+row_h), fill="white", outline=line, width=2)
        draw.text((x+12, y+26), profile.rota_name, fill=text, font=text_font)
        x += name_w

        for day in days:
            draw.rectangle((x, y, x+day_w, y+row_h), fill="white", outline=line, width=2)
            labels = [
                shift_label(s)
                + (" K" if s.shift_role == "kitchen" else "")
                for s in shift_map.get((profile.id, day), [])
            ]
            draw.multiline_text(
                (x+10, y+25),
                "\n".join(labels) if labels else "",
                fill=text,
                font=text_font,
                spacing=3,
            )
            x += day_w


        y += row_h

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    output.seek(0)

    filename = f"rocket-rota-{week.week_start.isoformat()}.png"

    return send_file(
        output,
        mimetype="image/png",
        as_attachment=True,
        download_name=filename,
    )


# -------------------------
# Staff profiles
# -------------------------

@main.route("/rota/staff")
def rota_profiles():
    return redirect(url_for("main.rota_home"))


@main.route("/rota/staff/new", methods=["GET", "POST"])
def rota_profile_new():
    """
    Add Staff does not create new people.

    It restores one of the known archived staff members to the active rota.
    Login-account linking can be handled separately later.
    """
    allowed_names = {"hannah", "charl", "leoni", "erin"}

    archived_staff = db.session.scalars(
        db.select(StaffProfile)
        .where(
            StaffProfile.active.is_(False),
            db.func.lower(StaffProfile.display_name).in_(allowed_names),
        )
        .order_by(StaffProfile.sort_order, StaffProfile.display_name)
    ).all()

    if request.method == "POST":
        try:
            profile_id = int(request.form.get("profile_id", ""))
        except ValueError:
            flash("Choose a staff member to add.", "error")
            return redirect(url_for("main.rota_profile_new"))

        profile = db.session.get(StaffProfile, profile_id)

        if (
            profile is None
            or profile.active
            or profile.rota_name.strip().lower() not in allowed_names
        ):
            flash("That archived staff member cannot be added here.", "error")
            return redirect(url_for("main.rota_profile_new"))

        profile.active = True
        db.session.commit()

        flash(
            f"{profile.rota_name} added back to future rotas.",
            "success",
        )
        return redirect(url_for("main.rota_home"))

    return render_template(
        "rota_add_staff.html",
        archived_staff=archived_staff,
    )


@main.route("/rota/staff/<int:profile_id>/edit", methods=["GET", "POST"])
def rota_profile_edit(profile_id):
    profile = db.get_or_404(StaffProfile, profile_id)

    if profile.user_id:
        flash(
            "Change this person's name from Management → Users.",
            "info",
        )

    rota_id_text = (
        request.form.get("rota_id", "")
        if request.method == "POST"
        else request.args.get("rota_id", "")
    )

    if str(rota_id_text).isdigit():
        return redirect(
            url_for("main.rota_edit", rota_id=int(rota_id_text))
        )

    return redirect(url_for("main.rota_home"))


@main.route("/rota/staff/<int:profile_id>/delete", methods=["POST"])
def rota_profile_delete(profile_id):
    # Keep this old endpoint working, but treat removal as archiving so
    # historical rotas are never broken.
    profile = db.get_or_404(StaffProfile, profile_id)
    profile.active = False
    db.session.commit()

    flash(
        f"{profile.rota_name} archived from future rotas.",
        "success",
    )
    return redirect(url_for("main.rota_profiles"))


@main.route("/rota/staff/<int:profile_id>/archive", methods=["POST"])
def rota_profile_archive(profile_id):
    profile = db.get_or_404(StaffProfile, profile_id)
    archived_name = profile.rota_name

    profile.active = False
    db.session.commit()
    db.session.expire_all()

    flash(
        f"{archived_name} moved to Archived staff.",
        "success",
    )

    rota_id_text = request.form.get("rota_id", "").strip()

    if rota_id_text.isdigit():
        return redirect(
            url_for("main.rota_edit", rota_id=int(rota_id_text))
        )

    return redirect(url_for("main.rota_home"))


@main.route("/rota/staff/<int:profile_id>/restore", methods=["POST"])
def rota_profile_restore(profile_id):
    profile = db.get_or_404(StaffProfile, profile_id)
    profile.active = True

    if profile.user_id is None:
        matching_user = db.session.scalar(
            db.select(AppUser).where(
                db.func.lower(AppUser.username)
                == profile.rota_name.lower()
            )
        )
        if matching_user:
            profile.user_id = matching_user.id

    restored_name = profile.rota_name

    db.session.commit()
    db.session.expire_all()

    flash(
        f"{restored_name} added back to the rota.",
        "success",
    )

    rota_id_text = request.form.get("rota_id", "").strip()

    if rota_id_text.isdigit():
        return redirect(
            url_for("main.rota_edit", rota_id=int(rota_id_text))
        )

    return redirect(url_for("main.rota_home"))


# -------------------------
# Staff diary
# -------------------------

def day_off_limit_for_date(day):
    """Mon-Thu: first 3 are favourable. Fri-Sun: first 2."""
    return 3 if day.weekday() <= 3 else 2


def ordinal(value):
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def day_off_request_positions(start_date, end_date):
    """
    Rank all non-rejected day-off requests by submission time for each date.

    Approved requests keep their original place in the queue. Rejected
    requests no longer consume a place.
    """
    requests = db.session.scalars(
        db.select(StaffDiaryEntry)
        .where(
            StaffDiaryEntry.entry_type == "day_off_request",
            StaffDiaryEntry.status.in_(["requested", "approved"]),
            StaffDiaryEntry.entry_date >= start_date,
            StaffDiaryEntry.entry_date <= end_date,
        )
        .order_by(
            StaffDiaryEntry.entry_date,
            StaffDiaryEntry.created_at,
            StaffDiaryEntry.id,
        )
    ).all()

    positions = {}
    counters = {}

    for entry in requests:
        counters[entry.entry_date] = counters.get(entry.entry_date, 0) + 1
        position = counters[entry.entry_date]
        limit = day_off_limit_for_date(entry.entry_date)

        positions[entry.id] = {
            "position": position,
            "position_label": ordinal(position),
            "limit": limit,
            "good_chance": position <= limit,
        }

    return positions


def no_one_off_dates(start_date, end_date):
    return set(
        db.session.scalars(
            db.select(StaffDiaryEntry.entry_date).where(
                StaffDiaryEntry.entry_type == "no_one_off",
                StaffDiaryEntry.status.in_(["info", "approved"]),
                StaffDiaryEntry.entry_date >= start_date,
                StaffDiaryEntry.entry_date <= end_date,
            )
        ).all()
    )


@main.route("/staff-diary", methods=["GET", "POST"])
def staff_diary():
    profile = current_staff_profile()

    if profile is None and not current_user().is_manager:
        flash(
            "Your login is not linked to a rota staff profile yet.",
            "error",
        )
        return redirect(url_for("main.dashboard"))

    month_text = request.args.get("month", "").strip()

    try:
        month_date = (
            datetime.strptime(month_text, "%Y-%m").date().replace(day=1)
            if month_text
            else date.today().replace(day=1)
        )
    except ValueError:
        month_date = date.today().replace(day=1)

    previous_month = (
        month_date.replace(day=1) - timedelta(days=1)
    ).replace(day=1)

    next_month = (
        date(month_date.year + 1, 1, 1)
        if month_date.month == 12
        else date(month_date.year, month_date.month + 1, 1)
    )

    cal = calendar.Calendar(firstweekday=0)
    calendar_weeks = cal.monthdatescalendar(
        month_date.year,
        month_date.month,
    )
    visible_dates = [day for week in calendar_weeks for day in week]
    visible_start = min(visible_dates)
    visible_end = max(visible_dates)

    if request.method == "POST":
        action = request.form.get("request_action", "").strip()

        selected_dates = []
        for item in request.form.get("selected_dates", "").split(","):
            item = item.strip()
            if not item:
                continue
            try:
                selected_dates.append(
                    datetime.strptime(item, "%Y-%m-%d").date()
                )
            except ValueError:
                pass

        selected_dates = sorted(set(selected_dates))

        if not selected_dates:
            flash("Select at least one date.", "error")
            return redirect(
                url_for("main.staff_diary", month=month_date.strftime("%Y-%m"))
            )

        if len(selected_dates) > 63:
            flash("You can select up to 63 dates in one request.", "error")
            return redirect(
                url_for("main.staff_diary", month=month_date.strftime("%Y-%m"))
            )

        if action not in {"day_off", "shift_request", "no_one_off"}:
            flash("Choose a request type.", "error")
            return redirect(
                url_for("main.staff_diary", month=month_date.strftime("%Y-%m"))
            )

        if action in {"day_off", "shift_request"} and profile is None:
            flash(
                "You do not have a rota profile for personal requests.",
                "error",
            )
            return redirect(
                url_for("main.staff_diary", month=month_date.strftime("%Y-%m"))
            )

        if action == "no_one_off" and not current_user().is_manager:
            flash("Only managers can mark NO ONE OFF.", "error")
            return redirect(
                url_for("main.staff_diary", month=month_date.strftime("%Y-%m"))
            )

        shorthand = None
        available_from = None
        available_until = None

        if action == "shift_request":
            shorthand = request.form.get(
                "availability_shift",
                "",
            ).strip().upper().replace(" ", "")

            try:
                (
                    available_from,
                    available_until,
                    end_is_finish,
                ) = parse_rota_shift_text(shorthand)
            except ValueError:
                flash("Enter a valid shift.", "error")
                return redirect(
                    url_for("main.staff_diary", month=month_date.strftime("%Y-%m"))
                )

            if end_is_finish:
                available_until = None

        request_group_id = str(uuid.uuid4())

        selected_no_one_off = no_one_off_dates(
            min(selected_dates),
            max(selected_dates),
        ).intersection(selected_dates)

        for entry_date in selected_dates:
            if action == "no_one_off":
                entry = StaffDiaryEntry(
                    staff_id=None,
                    entry_date=entry_date,
                    entry_type="no_one_off",
                    request_group_id=request_group_id,
                    note=None,
                    status="info",
                    created_by_user_id=current_user().id,
                    reviewed_by_user_id=current_user().id,
                    reviewed_at=datetime.now(),
                )
            elif action == "day_off":
                entry = StaffDiaryEntry(
                    staff_id=profile.id,
                    entry_date=entry_date,
                    entry_type="day_off_request",
                    request_group_id=request_group_id,
                    note=None,
                    status="requested",
                    created_by_user_id=current_user().id,
                )
            else:
                entry = StaffDiaryEntry(
                    staff_id=profile.id,
                    entry_date=entry_date,
                    entry_type="available_window",
                    request_group_id=request_group_id,
                    available_from=available_from,
                    available_until=available_until,
                    note=shorthand,
                    status="requested",
                    created_by_user_id=current_user().id,
                )

            db.session.add(entry)

        db.session.commit()

        if action == "no_one_off":
            flash("NO ONE OFF added.", "success")
        elif action == "day_off" and selected_no_one_off:
            flash(
                "Request sent. One or more selected dates are marked "
                "NO ONE OFF, so the chance of approval is low.",
                "success",
            )
        else:
            flash("Request sent to managers.", "success")

        return redirect(
            url_for(
                "main.staff_diary",
                month=selected_dates[0].strftime("%Y-%m"),
            )
        )

    all_entries = db.session.scalars(
        db.select(StaffDiaryEntry)
        .where(
            StaffDiaryEntry.entry_date >= visible_start,
            StaffDiaryEntry.entry_date <= visible_end,
        )
        .order_by(StaffDiaryEntry.entry_date, StaffDiaryEntry.created_at)
    ).all()

    entries_by_date = {d: [] for d in visible_dates}

    for entry in all_entries:
        visible = (
            current_user().is_manager
            or entry.status in {"approved", "info"}
            or (
                profile is not None
                and entry.staff_id == profile.id
            )
        )

        if visible:
            entries_by_date.setdefault(entry.entry_date, []).append(entry)

    day_off_positions = day_off_request_positions(
        visible_start,
        visible_end,
    )
    no_off_dates = no_one_off_dates(
        visible_start,
        visible_end,
    )

    large_parties = db.session.scalars(
        db.select(LargePartyInquiry)
        .where(
            LargePartyInquiry.event_date >= visible_start,
            LargePartyInquiry.event_date <= visible_end,
            LargePartyInquiry.status != "Cancelled",
        )
        .order_by(
            LargePartyInquiry.event_date,
            LargePartyInquiry.event_time,
        )
    ).all()

    large_parties_by_date = {d: [] for d in visible_dates}
    for inquiry in large_parties:
        large_parties_by_date.setdefault(
            inquiry.event_date,
            [],
        ).append(inquiry)

    pub_events = db.session.scalars(
        db.select(PubCalendarEvent)
        .where(
            PubCalendarEvent.event_date >= visible_start,
            PubCalendarEvent.event_date <= visible_end,
        )
        .order_by(
            PubCalendarEvent.event_date,
            PubCalendarEvent.event_time,
            PubCalendarEvent.id,
        )
    ).all()

    events_by_date = {d: [] for d in visible_dates}
    for event in pub_events:
        events_by_date.setdefault(
            event.event_date,
            [],
        ).append(event)

    my_pending_requests = []

    if profile is not None:
        own_pending = db.session.scalars(
            db.select(StaffDiaryEntry)
            .where(
                StaffDiaryEntry.staff_id == profile.id,
                StaffDiaryEntry.status == "requested",
                StaffDiaryEntry.entry_type.in_(
                    ["day_off_request", "available_window"]
                ),
            )
            .order_by(
                StaffDiaryEntry.created_at,
                StaffDiaryEntry.entry_date,
            )
        ).all()

        grouped_pending = {}

        for entry in own_pending:
            key = entry.request_group_id or f"entry-{entry.id}"

            if key not in grouped_pending:
                grouped_pending[key] = {
                    "key": key,
                    "entry_type": entry.entry_type,
                    "shift_text": (
                        entry.note
                        if entry.entry_type == "available_window"
                        else None
                    ),
                    "dates": [],
                }

            grouped_pending[key]["dates"].append(entry.entry_date)

        my_pending_requests = list(grouped_pending.values())

    removable_by_date = {d: [] for d in visible_dates}

    for entry in all_entries:
        if entry.entry_type in {"day_off_request", "available_window"}:
            can_remove = current_user().is_admin or (
                profile is not None
                and entry.staff_id == profile.id
            )

            if can_remove:
                removable_by_date.setdefault(entry.entry_date, []).append(
                    {
                        "kind": "request",
                        "id": entry.id,
                        "label": (
                            f"{entry.staff.rota_name} - Day off"
                            if entry.entry_type == "day_off_request"
                            else f"{entry.staff.rota_name} - Shift {entry.note or ''}"
                        ),
                        "url": url_for(
                            "main.remove_staff_diary_request",
                            entry_id=entry.id,
                        ),
                    }
                )

        elif (
            entry.entry_type == "no_one_off"
            and current_user().is_manager
        ):
            removable_by_date.setdefault(entry.entry_date, []).append(
                {
                    "kind": "no_one_off",
                    "id": entry.id,
                    "label": "NO ONE OFF",
                    "url": url_for(
                        "main.remove_no_one_off",
                        entry_id=entry.id,
                    ),
                }
            )

    if current_user().is_manager:
        for event in pub_events:
            removable_by_date.setdefault(event.event_date, []).append(
                {
                    "kind": "event",
                    "id": event.id,
                    "label": event.title,
                    "url": url_for(
                        "main.calendar_event_delete",
                        event_id=event.id,
                    ),
                }
            )


    return render_template(
        "staff_diary.html",
        month_date=month_date,
        previous_month=previous_month,
        next_month=next_month,
        calendar_weeks=calendar_weeks,
        entries_by_date=entries_by_date,
        large_parties_by_date=large_parties_by_date,
        events_by_date=events_by_date,
        day_off_positions=day_off_positions,
        no_off_dates=no_off_dates,
        my_profile=profile,
        my_pending_requests=my_pending_requests,
        removable_by_date=removable_by_date,
        preselected_date=request.args.get("selected", "").strip(),
    )


@main.route("/staff-diary/request/<int:entry_id>/remove", methods=["POST"])
def remove_staff_diary_request(entry_id):
    entry = db.get_or_404(StaffDiaryEntry, entry_id)
    profile = current_staff_profile()

    if entry.entry_type not in {"day_off_request", "available_window"}:
        flash("That diary item cannot be removed here.", "error")
        return redirect(
            url_for(
                "main.staff_diary",
                month=entry.entry_date.strftime("%Y-%m"),
            )
        )

    # Admin can remove anybody's request. Everyone else can only remove
    # a request that belongs to their own linked rota profile.
    can_remove = current_user().is_admin or (
        profile is not None
        and entry.staff_id == profile.id
    )

    if not can_remove:
        flash(
            "You can only remove your own day-off or shift requests.",
            "error",
        )
        return redirect(
            url_for(
                "main.staff_diary",
                month=entry.entry_date.strftime("%Y-%m"),
            )
        )

    selected_date = entry.entry_date
    month = selected_date.strftime("%Y-%m")

    # The diary entry itself is the manager-inbox request record. Deleting it
    # removes that date from the request inbox as well. If it was the only date
    # in a grouped request, the request disappears completely.
    db.session.delete(entry)
    db.session.commit()

    flash("Diary request removed.", "success")
    return redirect(
        url_for(
            "main.staff_diary",
            month=month,
            selected=selected_date.isoformat(),
        )
    )


@main.route("/staff-diary/no-one-off/<int:entry_id>/remove", methods=["POST"])
def remove_no_one_off(entry_id):
    entry = db.get_or_404(StaffDiaryEntry, entry_id)

    if (
        not current_user().is_manager
        or entry.entry_type != "no_one_off"
    ):
        flash("Manager access is required.", "error")
        return redirect(url_for("main.staff_diary"))

    selected_date = entry.entry_date
    month = selected_date.strftime("%Y-%m")
    db.session.delete(entry)
    db.session.commit()

    flash("NO ONE OFF removed.", "success")
    return redirect(
        url_for(
            "main.staff_diary",
            month=month,
            selected=selected_date.isoformat(),
        )
    )




@main.route("/staff-diary/event/add", methods=["POST"])
def calendar_event_add():
    date_text = request.form.get("event_date", "").strip()
    title = request.form.get("title", "").strip()
    event_type = request.form.get("event_type", "event").strip()

    try:
        event_date = datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError:
        flash("Choose a valid event date.", "error")
        return redirect(url_for("main.staff_diary"))

    if not title:
        flash("Enter an event name.", "error")
        return redirect(
            url_for("main.staff_diary", month=event_date.strftime("%Y-%m"))
        )

    if event_type not in {"football", "event"}:
        event_type = "event"

    event_time = None
    time_text = request.form.get("event_time", "").strip()
    if time_text:
        try:
            event_time = datetime.strptime(time_text, "%H:%M").time()
        except ValueError:
            flash("Enter a valid event time.", "error")
            return redirect(
                url_for("main.staff_diary", month=event_date.strftime("%Y-%m"))
            )

    db.session.add(
        PubCalendarEvent(
            event_date=event_date,
            title=title,
            event_type=event_type,
            event_time=event_time,
            created_by_user_id=current_user().id,
        )
    )
    db.session.commit()

    flash("Event added to the Staff Diary.", "success")
    return redirect(
        url_for("main.staff_diary", month=event_date.strftime("%Y-%m"))
    )


@main.route("/staff-diary/event/<int:event_id>/delete", methods=["POST"])
def calendar_event_delete(event_id):
    event = db.get_or_404(PubCalendarEvent, event_id)
    selected_date = event.event_date
    month = selected_date.strftime("%Y-%m")
    db.session.delete(event)
    db.session.commit()

    flash("Event removed.", "success")
    return redirect(
        url_for(
            "main.staff_diary",
            month=month,
            selected=selected_date.isoformat(),
        )
    )


@main.route("/staff-requests")
def staff_request_inbox():
    month_text = request.args.get("month", "").strip()

    try:
        month_date = (
            datetime.strptime(month_text, "%Y-%m").date().replace(day=1)
            if month_text
            else date.today().replace(day=1)
        )
    except ValueError:
        month_date = date.today().replace(day=1)

    previous_month = (
        month_date.replace(day=1) - timedelta(days=1)
    ).replace(day=1)

    next_month = (
        date(month_date.year + 1, 1, 1)
        if month_date.month == 12
        else date(month_date.year, month_date.month + 1, 1)
    )

    cal = calendar.Calendar(firstweekday=0)
    calendar_weeks = cal.monthdatescalendar(
        month_date.year,
        month_date.month,
    )
    visible_dates = [d for week in calendar_weeks for d in week]
    visible_start = min(visible_dates)
    visible_end = max(visible_dates)

    pending = db.session.scalars(
        db.select(StaffDiaryEntry)
        .where(
            StaffDiaryEntry.status == "requested",
            StaffDiaryEntry.entry_type.in_(
                ["day_off_request", "available_window"]
            ),
        )
        .order_by(StaffDiaryEntry.created_at, StaffDiaryEntry.entry_date)
    ).all()

    grouped = {}

    for entry in pending:
        key = entry.request_group_id or f"entry-{entry.id}"

        if key not in grouped:
            grouped[key] = {
                "key": key,
                "staff": entry.staff,
                "entry_type": entry.entry_type,
                "entries": [],
                "created_at": entry.created_at,
                "shift_text": (
                    entry.note
                    if entry.entry_type == "available_window"
                    else None
                ),
            }

        grouped[key]["entries"].append(entry)

    requests = list(grouped.values())

    for group in requests:
        group["entries"].sort(key=lambda e: e.entry_date)
        group["dates"] = [e.entry_date for e in group["entries"]]

    if requests:
        all_request_dates = [
            entry.entry_date
            for item in requests
            for entry in item["entries"]
        ]
        range_start = min(all_request_dates)
        range_end = max(all_request_dates)
        positions = day_off_request_positions(range_start, range_end)
        blocked_dates = no_one_off_dates(range_start, range_end)
    else:
        positions = {}
        blocked_dates = set()

    for item in requests:
        item["date_details"] = []

        for entry in item["entries"]:
            rank = positions.get(entry.id)
            item["date_details"].append(
                {
                    "date": entry.entry_date,
                    "position": rank,
                    "no_one_off": entry.entry_date in blocked_dates,
                }
            )

    calendar_entries = db.session.scalars(
        db.select(StaffDiaryEntry)
        .where(
            StaffDiaryEntry.entry_date >= visible_start,
            StaffDiaryEntry.entry_date <= visible_end,
        )
        .order_by(
            StaffDiaryEntry.entry_date,
            StaffDiaryEntry.created_at,
            StaffDiaryEntry.id,
        )
    ).all()

    calendar_entries_by_date = {d: [] for d in visible_dates}
    for entry in calendar_entries:
        calendar_entries_by_date.setdefault(entry.entry_date, []).append(entry)

    calendar_positions = day_off_request_positions(
        visible_start,
        visible_end,
    )
    calendar_no_off_dates = no_one_off_dates(
        visible_start,
        visible_end,
    )

    calendar_large_parties = db.session.scalars(
        db.select(LargePartyInquiry)
        .where(
            LargePartyInquiry.event_date >= visible_start,
            LargePartyInquiry.event_date <= visible_end,
            LargePartyInquiry.status != "Cancelled",
        )
        .order_by(
            LargePartyInquiry.event_date,
            LargePartyInquiry.event_time,
        )
    ).all()

    calendar_large_parties_by_date = {d: [] for d in visible_dates}
    for inquiry in calendar_large_parties:
        calendar_large_parties_by_date.setdefault(
            inquiry.event_date,
            [],
        ).append(inquiry)

    calendar_events = db.session.scalars(
        db.select(PubCalendarEvent)
        .where(
            PubCalendarEvent.event_date >= visible_start,
            PubCalendarEvent.event_date <= visible_end,
        )
        .order_by(
            PubCalendarEvent.event_date,
            PubCalendarEvent.event_time,
            PubCalendarEvent.id,
        )
    ).all()

    calendar_events_by_date = {d: [] for d in visible_dates}
    for event in calendar_events:
        calendar_events_by_date.setdefault(
            event.event_date,
            [],
        ).append(event)

    return render_template(
        "staff_requests.html",
        requests=requests,
        month_date=month_date,
        previous_month=previous_month,
        next_month=next_month,
        calendar_weeks=calendar_weeks,
        entries_by_date=calendar_entries_by_date,
        large_parties_by_date=calendar_large_parties_by_date,
        events_by_date=calendar_events_by_date,
        day_off_positions=calendar_positions,
        no_off_dates=calendar_no_off_dates,
    )


@main.route("/staff-requests/<string:group_key>/decision", methods=["POST"])
def diary_manager_update(group_key):
    action = request.form.get("action")

    if action not in {"approved", "rejected"}:
        flash("Choose Approve or Decline.", "error")
        return redirect(url_for("main.staff_request_inbox"))

    if group_key.startswith("entry-"):
        try:
            entry_id = int(group_key.split("-", 1)[1])
        except ValueError:
            entry_id = -1

        entry = db.session.get(StaffDiaryEntry, entry_id)
        entries = [entry] if entry else []
    else:
        entries = db.session.scalars(
            db.select(StaffDiaryEntry).where(
                StaffDiaryEntry.request_group_id == group_key,
                StaffDiaryEntry.status == "requested",
            )
        ).all()

    if not entries:
        flash("That request is no longer open.", "error")
        return redirect(url_for("main.staff_request_inbox"))

    for entry in entries:
        entry.status = action
        entry.reviewed_by_user_id = current_user().id
        entry.reviewed_at = datetime.now()

    db.session.commit()

    flash(
        "Request approved." if action == "approved" else "Request declined.",
        "success",
    )
    return redirect(url_for("main.staff_request_inbox"))




# -------------------------
# Shift swaps
# -------------------------

@main.route("/shift-requests")
def shift_request_inbox():
    my_profile = current_staff_profile()

    if not my_profile:
        return render_template(
            "shift_requests.html",
            my_profile=None,
            incoming=[],
            outgoing=[],
            shift_label=shift_label,
        )

    incoming = db.session.scalars(
        db.select(ShiftSwapRequest)
        .where(
            ShiftSwapRequest.target_staff_id == my_profile.id,
            ShiftSwapRequest.status == "pending_target",
        )
        .order_by(ShiftSwapRequest.created_at.desc())
    ).all()

    outgoing = db.session.scalars(
        db.select(ShiftSwapRequest)
        .where(
            ShiftSwapRequest.requester_staff_id == my_profile.id,
        )
        .order_by(ShiftSwapRequest.created_at.desc())
        .limit(30)
    ).all()

    return render_template(
        "shift_requests.html",
        my_profile=my_profile,
        incoming=incoming,
        outgoing=outgoing,
        shift_label=shift_label,
    )


@main.route("/rota/swap/<int:swap_id>/cancel", methods=["POST"])
def cancel_shift_request(swap_id):
    swap = db.get_or_404(ShiftSwapRequest, swap_id)
    my_profile = current_staff_profile()

    if (
        not my_profile
        or swap.requester_staff_id != my_profile.id
    ):
        flash("You can only cancel a shift request that you sent.", "error")
        return redirect(url_for("main.shift_request_inbox"))

    if swap.status != "pending_target":
        flash("That shift request can no longer be cancelled.", "error")
        return redirect(url_for("main.shift_request_inbox"))

    week_start = (
        swap.requester_shift.rota_week.week_start
        if swap.requester_shift and swap.requester_shift.rota_week
        else None
    )

    db.session.delete(swap)
    db.session.commit()

    flash("Shift request cancelled.", "success")

    if request.form.get("return_to") == "rota" and week_start:
        return redirect(
            url_for(
                "main.rota_home",
                week=week_start.isoformat(),
            )
        )

    return redirect(url_for("main.shift_request_inbox"))


@main.route("/rota/shift/<int:shift_id>/swap", methods=["GET", "POST"])
def request_shift_swap(shift_id):
    shift = db.get_or_404(RotaShift, shift_id)
    my_profile = current_staff_profile()

    if not my_profile or shift.staff_id != my_profile.id:
        flash("You can only request a swap for your own shift.", "error")
        return redirect(url_for("main.rota_home"))

    other_profiles = db.session.scalars(
        db.select(StaffProfile)
        .where(
            StaffProfile.active.is_(True),
            StaffProfile.id != my_profile.id,
        )
        .order_by(StaffProfile.sort_order, StaffProfile.display_name)
    ).all()

    week = shift.rota_week

    if request.method == "POST":
        target_id = int(request.form["target_staff_id"])
        target_shift_text = request.form.get("target_shift_id", "")
        target_shift_id = int(target_shift_text) if target_shift_text else None


        target_profile = db.session.get(StaffProfile, target_id)
        if not target_profile:
            flash("Choose a valid staff member.", "error")
            return redirect(request.url)

        if target_shift_id:
            target_shift = db.session.get(RotaShift, target_shift_id)

            if (
                not target_shift
                or target_shift.staff_id != target_id
                or target_shift.rota_week_id != shift.rota_week_id
                or target_shift.shift_date != shift.shift_date
            ):
                flash(
                    "Shift swaps can only be made with another shift on the same day.",
                    "error",
                )
                return redirect(
                    url_for("main.rota_home", week=week.week_start.isoformat())
                )

        duplicate = db.session.scalar(
            db.select(ShiftSwapRequest).where(
                ShiftSwapRequest.requester_shift_id == shift.id,
                ShiftSwapRequest.target_staff_id == target_id,
                ShiftSwapRequest.status == "pending_target",
            )
        )

        if duplicate:
            flash("That swap request is already waiting for a response.", "error")
            return redirect(
                url_for("main.shift_request_inbox")
            )

        request_row = ShiftSwapRequest(
            requester_shift_id=shift.id,
            requester_staff_id=my_profile.id,
            target_staff_id=target_id,
            target_shift_id=target_shift_id,
            status="pending_target",
            requester_note=request.form.get("note", "").strip() or None,
        )

        db.session.add(request_row)
        db.session.commit()

        flash("Shift change request sent.", "success")
        return redirect(
            url_for(
                "main.rota_home",
                week=week.week_start.isoformat(),
            )
        )

    target_shifts = {
        profile.id: sorted(
            [
                s for s in week.shifts
                if s.staff_id == profile.id
            ],
            key=lambda s: (s.shift_date, s.start_time),
        )
        for profile in other_profiles
    }

    return render_template(
        "shift_swap.html",
        shift=shift,
        other_profiles=other_profiles,
        target_shifts=target_shifts,
        shift_label=shift_label,
    )


@main.route("/rota/swap/<int:swap_id>/respond", methods=["POST"])
def swap_target_response(swap_id):
    swap = db.get_or_404(ShiftSwapRequest, swap_id)
    my_profile = current_staff_profile()

    if not my_profile or swap.target_staff_id != my_profile.id:
        flash("That swap request is not assigned to you.", "error")
        return redirect(url_for("main.rota_home"))

    action = request.form.get("action")

    if swap.status != "pending_target":
        flash("That swap request is no longer waiting for you.", "error")
        return redirect(url_for("main.shift_request_inbox"))

    if action == "accept":
        requester_shift = swap.requester_shift
        target_shift = swap.target_shift

        if target_shift:
            if target_shift.shift_date != requester_shift.shift_date:
                flash("That shift swap is no longer valid.", "error")
                return redirect(url_for("main.shift_request_inbox"))

            requester_staff_id = requester_shift.staff_id
            requester_shift.staff_id = target_shift.staff_id
            target_shift.staff_id = requester_staff_id
        else:
            # The selected person was not working that day (or the requester
            # chose "take my shift"), so approval transfers the shift to them.
            requester_shift.staff_id = swap.target_staff_id

        swap.status = "approved"
    else:
        swap.status = "rejected"

    swap.target_response_note = (
        request.form.get("note", "").strip() or None
    )
    swap.target_responded_at = datetime.now()
    db.session.commit()

    flash(
        "Shift switch approved and the rota has been updated."
        if action == "accept"
        else "Shift switch declined.",
        "success",
    )

    return redirect(url_for("main.shift_request_inbox"))


@main.route("/rota/swap/<int:swap_id>/manager", methods=["POST"])
def swap_manager_decision(swap_id):
    swap = db.get_or_404(ShiftSwapRequest, swap_id)
    action = request.form.get("action")

    if action == "approve":
        requester_shift = swap.requester_shift

        if swap.target_shift:
            # True two-way swap.
            target_shift = swap.target_shift
            requester_staff_id = requester_shift.staff_id
            requester_shift.staff_id = target_shift.staff_id
            target_shift.staff_id = requester_staff_id
        else:
            # Target simply covers/takes the shift.
            requester_shift.staff_id = swap.target_staff_id

        swap.status = "approved"
    else:
        swap.status = "rejected"

    swap.manager_note = request.form.get("note", "").strip() or None
    swap.manager_user_id = current_user().id
    swap.manager_responded_at = datetime.now()

    db.session.commit()

    flash(
        "Swap approved and the published rota has been updated."
        if action == "approve"
        else "Swap rejected.",
        "success",
    )

    return redirect(url_for("main.rota_home"))


# -------------------------
# Rota settings
# -------------------------

@main.route("/rota/settings", methods=["GET", "POST"])
def rota_settings():
    if request.method == "POST":
        for weekday in range(7):
            row = db.session.scalar(
                db.select(RotaFinishSetting).where(
                    RotaFinishSetting.weekday == weekday
                )
            )

            text_value = request.form.get(
                f"finish_{weekday}",
                "",
            )

            if row and text_value:
                row.estimated_finish = datetime.strptime(
                    text_value,
                    "%H:%M",
                ).time()

        db.session.commit()
        flash("Estimated Finish times saved.", "success")
        return redirect(url_for("main.rota_settings"))

    finish_settings = {
        row.weekday: row
        for row in db.session.scalars(
            db.select(RotaFinishSetting)
        ).all()
    }

    templates = db.session.scalars(
        db.select(RotaShiftTemplate)
        .order_by(
            RotaShiftTemplate.weekday,
            RotaShiftTemplate.start_time,
        )
    ).all()

    return render_template(
        "rota_settings.html",
        finish_settings=finish_settings,
        templates=templates,
        weekday_names=WEEKDAY_NAMES,
    )


@main.route("/rota/settings/template/add", methods=["POST"])
def rota_template_add():
    try:
        weekday = int(request.form["weekday"])
        start = datetime.strptime(
            request.form["start_time"],
            "%H:%M",
        ).time()
        is_finish = request.form.get("end_is_finish") == "1"
        end = (
            None
            if is_finish
            else datetime.strptime(
                request.form["end_time"],
                "%H:%M",
            ).time()
        )
        quantity = max(int(request.form.get("quantity", 1)), 1)
    except (ValueError, KeyError):
        flash("Check the template details.", "error")
        return redirect(url_for("main.rota_settings"))

    db.session.add(
        RotaShiftTemplate(
            weekday=weekday,
            start_time=start,
            end_time=end,
            end_is_finish=is_finish,
            role=request.form.get("role", "front_of_house"),
            quantity=quantity,
        )
    )
    db.session.commit()

    return redirect(url_for("main.rota_settings"))


@main.route("/rota/settings/template/<int:template_id>/delete", methods=["POST"])
def rota_template_delete(template_id):
    row = db.get_or_404(RotaShiftTemplate, template_id)
    db.session.delete(row)
    db.session.commit()
    return redirect(url_for("main.rota_settings"))



# -------------------------
# Public customer portal
# -------------------------

@main.route("/")
@main.route("/customer")
@main.route("/customer/")
def customer_home():
    menu_path = os.path.join(
        os.path.dirname(__file__),
        "static",
        "menus",
        "the-rocket-pub-food-menu.pdf",
    )

    return render_template(
        "customer_home.html",
        food_menu_available=os.path.exists(menu_path),
    )


@main.route("/customer/food-menu")
def customer_food_menu():
    menu_directory = os.path.join(
        os.path.dirname(__file__),
        "static",
        "menus",
    )
    filename = "the-rocket-pub-food-menu.pdf"
    menu_path = os.path.join(menu_directory, filename)

    if not os.path.exists(menu_path):
        return render_template(
            "customer_menu_unavailable.html",
        ), 404

    return send_from_directory(
        menu_directory,
        filename,
        mimetype="application/pdf",
        as_attachment=False,
    )


@main.route("/customer/allergens")
def customer_allergens():
    return render_template(
        "customer_allergens.html",
        **allergen_menu_context(),
    )


# -------------------------
# Allergen menu
# -------------------------

def ensure_allergen_schema_current():
    """
    Repair older development SQLite databases before allergen queries run.

    The live Windows server keeps its existing instance/pub_booking.db while
    code is updated from GitHub, so newer model columns may not exist yet.
    """
    inspector = inspect(db.engine)

    if "allergen_menu_item" not in inspector.get_table_names():
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("allergen_menu_item")
    }

    required = {
        "milk_status": "VARCHAR(20) DEFAULT 'free'",
        "nuts_status": "VARCHAR(20) DEFAULT 'free'",
        "egg_status": "VARCHAR(20) DEFAULT 'free'",
        "gluten_status": "VARCHAR(20) DEFAULT 'free'",
        "can_make_gluten_free": "BOOLEAN DEFAULT 0",
        "gluten_free_changes": "VARCHAR(300)",
    }

    changed = False

    for name, sql_type in required.items():
        if name not in columns:
            db.session.execute(
                text(
                    f"ALTER TABLE allergen_menu_item "
                    f"ADD COLUMN {name} {sql_type}"
                )
            )
            changed = True

    if changed:
        db.session.commit()



def allergen_menu_context():
    """Shared read-only allergen data for staff and customer views."""
    ensure_allergen_schema_current()
    search = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()

    milk_free = request.args.get("milk_free") == "1"
    nut_free = request.args.get("nut_free") == "1"
    egg_free = request.args.get("egg_free") == "1"
    gluten_free = request.args.get("gluten_free") == "1"
    vegetarian = request.args.get("vegetarian") == "1"
    can_make_vegetarian = request.args.get("can_make_vegetarian") == "1"

    stmt = db.select(AllergenMenuItem).where(
        AllergenMenuItem.active.is_(True)
    )

    if search:
        term = f"%{search.lower()}%"
        stmt = stmt.where(
            db.or_(
                db.func.lower(AllergenMenuItem.name).like(term),
                db.func.lower(AllergenMenuItem.description).like(term),
                db.func.lower(AllergenMenuItem.ingredients).like(term),
            )
        )

    if category:
        stmt = stmt.where(AllergenMenuItem.category == category)

    if milk_free:
        stmt = stmt.where(AllergenMenuItem.milk_status == "free")
    if nut_free:
        stmt = stmt.where(AllergenMenuItem.nuts_status == "free")
    if egg_free:
        stmt = stmt.where(AllergenMenuItem.egg_status == "free")
    if gluten_free:
        stmt = stmt.where(
            db.or_(
                AllergenMenuItem.gluten_status == "free",
                AllergenMenuItem.can_make_gluten_free.is_(True),
            )
        )
    if vegetarian:
        stmt = stmt.where(AllergenMenuItem.vegetarian.is_(True))
    if can_make_vegetarian:
        stmt = stmt.where(
            db.or_(
                AllergenMenuItem.vegetarian.is_(True),
                AllergenMenuItem.can_make_vegetarian.is_(True),
            )
        )

    items = db.session.scalars(
        stmt.order_by(
            AllergenMenuItem.category,
            AllergenMenuItem.name,
        )
    ).all()

    categories = [
        "Main Meals",
        "Starters",
        "Sides",
        "Kids Meals",
        "Desserts",
    ]

    selected_allergens = []
    if milk_free:
        selected_allergens.append("milk_status")
    if nut_free:
        selected_allergens.append("nuts_status")
    if egg_free:
        selected_allergens.append("egg_status")
    if gluten_free:
        selected_allergens.append("gluten_status")

    side_options = {}
    safe_side_options = {}

    for item in items:
        if item.category != "Main Meals":
            continue

        sides = []
        for link in item.allowed_side_links:
            side = db.session.get(AllergenMenuItem, link.side_id)
            if side and side.active:
                sides.append(side)

        sides.sort(key=lambda side: side.name.lower())
        side_options[item.id] = sides

        if selected_allergens:
            def side_matches(field):
                if field == "gluten_status":
                    return (
                        side.gluten_status == "free"
                        or side.can_make_gluten_free
                    )
                return getattr(side, field) == "free"

            safe_side_options[item.id] = [
                side
                for side in sides
                if all(
                    side_matches(field)
                    for field in selected_allergens
                )
            ]
        else:
            safe_side_options[item.id] = sides

    return {
        "items": items,
        "categories": categories,
        "side_options": side_options,
        "safe_side_options": safe_side_options,
        "selected_allergens": selected_allergens,
        "search": search,
        "selected_category": category,
        "filters": {
            "milk_free": milk_free,
            "nut_free": nut_free,
            "egg_free": egg_free,
            "gluten_free": gluten_free,
            "vegetarian": vegetarian,
            "can_make_vegetarian": can_make_vegetarian,
        },
    }



@main.route("/allergens")
def allergen_menu():
    return render_template(
        "allergen_menu.html",
        **allergen_menu_context(),
    )


def allergen_form_values(item=None):
    ensure_allergen_schema_current()

    side_items = db.session.scalars(
        db.select(AllergenMenuItem)
        .where(
            AllergenMenuItem.category == "Sides",
            AllergenMenuItem.active.is_(True),
        )
        .order_by(AllergenMenuItem.name)
    ).all()

    selected_side_ids = set()

    if item is not None:
        selected_side_ids = {
            link.side_id
            for link in item.allowed_side_links
        }

    return {
        "item": item,
        "categories": [
            "Main Meals",
            "Starters",
            "Sides",
            "Kids Meals",
            "Desserts",
        ],
        "side_items": side_items,
        "selected_side_ids": selected_side_ids,
    }


@main.route("/allergens/new", methods=["GET", "POST"])
def allergen_new():
    if request.method == "POST":
        return save_allergen_item()

    return render_template(
        "allergen_form.html",
        **allergen_form_values(),
    )


@main.route("/allergens/<int:item_id>/edit", methods=["GET", "POST"])
def allergen_edit(item_id):
    ensure_allergen_schema_current()
    item = db.get_or_404(AllergenMenuItem, item_id)

    if request.method == "POST":
        return save_allergen_item(item)

    return render_template(
        "allergen_form.html",
        **allergen_form_values(item),
    )


def save_allergen_item(item=None):
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip() or "Main Meals"

    valid_categories = {
        "Main Meals",
        "Starters",
        "Sides",
        "Kids Meals",
        "Desserts",
    }

    if category not in valid_categories:
        flash("Choose a valid menu category.", "error")
        return redirect(request.url)

    if not name:
        flash("Enter a menu item name.", "error")
        return redirect(request.url)

    duplicate_stmt = db.select(AllergenMenuItem).where(
        db.func.lower(AllergenMenuItem.name) == name.lower()
    )

    if item is not None:
        duplicate_stmt = duplicate_stmt.where(
            AllergenMenuItem.id != item.id
        )

    if db.session.scalar(duplicate_stmt):
        flash("A menu item with that name already exists.", "error")
        return redirect(request.url)

    is_new_item = item is None

    if is_new_item:
        item = AllergenMenuItem()
        db.session.add(item)

    # Required fields must be assigned before the first INSERT/flush.
    item.name = name
    item.category = category
    # Description is no longer used by the allergen menu.
    item.description = None

    raw_ingredients = request.form.get("ingredients", "")
    ingredient_lines = []

    for line in raw_ingredients.replace("\r", "").split("\n"):
        # Accept pasted bullet lists too, but store clean one-item-per-line text.
        cleaned = line.strip()
        cleaned = cleaned.lstrip("•*-").strip()

        if cleaned:
            ingredient_lines.append(cleaned)

    item.ingredients = "\n".join(ingredient_lines) or None

    valid_statuses = {"free", "contains", "may_contain"}

    for field in [
        "milk_status",
        "nuts_status",
        "egg_status",
        "gluten_status",
    ]:
        value = request.form.get(field, "free")
        if value not in valid_statuses:
            value = "free"
        setattr(item, field, value)

    # Keep legacy booleans coherent during the development migration.
    item.contains_milk = item.milk_status == "contains"
    item.contains_nuts = item.nuts_status == "contains"
    item.contains_egg = item.egg_status == "contains"
    item.contains_gluten = item.gluten_status == "contains"

    item.vegetarian = request.form.get("vegetarian") == "1"
    item.can_make_vegetarian = (
        request.form.get("can_make_vegetarian") == "1"
    )
    item.vegetarian_changes = None

    item.can_make_gluten_free = (
        request.form.get("can_make_gluten_free") == "1"
    )
    item.gluten_free_changes = None

    # New rows need an ID before their side links can be rebuilt. At this point
    # all required fields have been populated, so flushing is safe.
    if is_new_item:
        db.session.flush()

    # Only Main Meals hold side options. Rebuild the links whenever saved.
    AllergenMealSide.query.filter_by(meal_id=item.id).delete()

    if item.category == "Main Meals":
        selected_side_ids = request.form.getlist("side_ids")

        for side_id_text in selected_side_ids:
            try:
                side_id = int(side_id_text)
            except ValueError:
                continue

            side = db.session.get(AllergenMenuItem, side_id)

            if side and side.category == "Sides" and side.active:
                db.session.add(
                    AllergenMealSide(
                        meal_id=item.id,
                        side_id=side.id,
                    )
                )

    db.session.commit()

    flash("Allergen menu item saved.", "success")
    return redirect(url_for("main.allergen_menu"))




@main.route("/allergens/<int:item_id>/delete", methods=["POST"])
def allergen_delete(item_id):
    item = db.get_or_404(AllergenMenuItem, item_id)
    name = item.name
    db.session.delete(item)
    db.session.commit()

    flash(f"{name} deleted from the allergen menu.", "success")
    return redirect(url_for("main.allergen_menu"))


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




@main.route("/table-map")
def table_map():
    tables = db.session.scalars(
        db.select(PubTable)
        .where(PubTable.active.is_(True))
        .order_by(*table_order_clause())
    ).all()

    floor_objects = db.session.scalars(
        db.select(FloorPlanObject)
        .order_by(FloorPlanObject.z_index, FloorPlanObject.id)
    ).all()

    settings = db.session.scalar(
        db.select(FloorPlanSetting).where(
            FloorPlanSetting.name == "main"
        )
    )

    return render_template(
        "table_map.html",
        tables=tables,
        floor_objects=floor_objects,
        settings=settings,
    )


@main.route("/table-layout")
def table_layout():
    """
    Master visual pub floor-plan editor.

    Bookable tables use PubTable; everything structural/decorative is stored as
    FloorPlanObject so it never enters the booking allocator.
    """
    tables = db.session.scalars(
        db.select(PubTable).order_by(*table_order_clause())
    ).all()

    areas = db.session.scalars(
        db.select(Area).order_by(Area.name)
    ).all()

    pairings = db.session.scalars(
        db.select(TablePairing)
    ).all()

    settings = db.session.scalar(
        db.select(FloorPlanSetting).where(
            FloorPlanSetting.name == "main"
        )
    )

    floor_objects = db.session.scalars(
        db.select(FloorPlanObject)
        .order_by(FloorPlanObject.z_index, FloorPlanObject.id)
    ).all()

    return render_template(
        "table_layout.html",
        tables=tables,
        areas=areas,
        pairings=pairings,
        settings=settings,
        floor_objects=floor_objects,
    )


@main.route("/api/table-layout/save", methods=["POST"])
def save_table_layout():
    """
    Save drag/resize/shape changes from the floor-plan editor.

    Payload:
    {
      "tables": [
        {
          "id": 1,
          "x": 120,
          "y": 100,
          "width": 90,
          "height": 60,
          "shape": "rectangle",
          "rotation": 0
        }
      ],
      "canvas_width": 1200,
      "canvas_height": 760
    }
    """
    payload = request.get_json(silent=True) or {}
    table_rows = payload.get("tables", [])

    settings = db.session.scalar(
        db.select(FloorPlanSetting).where(
            FloorPlanSetting.name == "main"
        )
    )

    if settings is None:
        settings = FloorPlanSetting(name="main")
        db.session.add(settings)

    canvas_width = payload.get("canvas_width")
    canvas_height = payload.get("canvas_height")

    if isinstance(canvas_width, (int, float)) and canvas_width >= 600:
        settings.canvas_width = int(canvas_width)

    if isinstance(canvas_height, (int, float)) and canvas_height >= 400:
        settings.canvas_height = int(canvas_height)

    allowed_shapes = {"rectangle", "round", "square", "oval"}

    for row in table_rows:
        table_id = row.get("id")

        if not isinstance(table_id, int):
            continue

        table = db.session.get(PubTable, table_id)

        if table is None:
            continue

        try:
            x = float(row.get("x", table.x_position or 0))
            y = float(row.get("y", table.y_position or 0))
            width = float(row.get("width", table.layout_width or 90))
            height = float(row.get("height", table.layout_height or 60))
            rotation = float(row.get("rotation", table.layout_rotation or 0))
        except (TypeError, ValueError):
            continue

        shape = row.get("shape", table.layout_shape or "rectangle")
        if shape not in allowed_shapes:
            shape = "rectangle"

        # Keep rotation-aware signed coordinates for the same reason as
        # structural floor objects. The browser editor already constrains the
        # VISUAL table inside the map.
        table.x_position = max(-500, min(x, settings.canvas_width + 500))
        table.y_position = max(-500, min(y, settings.canvas_height + 500))
        table.layout_width = min(max(width, 46), 400)
        table.layout_height = min(max(height, 46), 300)
        table.layout_shape = shape
        table.layout_rotation = rotation % 360

    for row in payload.get("objects", []):
        object_id = row.get("id")

        if not isinstance(object_id, int):
            continue

        floor_object = db.session.get(FloorPlanObject, object_id)

        if floor_object is None:
            continue

        try:
            x = float(row.get("x", floor_object.x_position))
            y = float(row.get("y", floor_object.y_position))
            width = float(row.get("width", floor_object.layout_width))
            height = float(row.get("height", floor_object.layout_height))
            rotation = float(
                row.get("rotation", floor_object.layout_rotation)
            )
            z_index = int(row.get("z_index", floor_object.z_index))
        except (TypeError, ValueError):
            continue

        shape = row.get("shape", floor_object.layout_shape or "rectangle")
        if shape not in allowed_shapes:
            shape = "rectangle"

        # Rotated objects may legitimately need a negative unrotated
        # left/top value so their VISUAL edge sits flush with the map edge.
        # Example: a long wall rotated 90° can require x < 0 even though no
        # visible part of the wall is outside the floor plan.
        floor_object.x_position = max(-1000, min(x, settings.canvas_width + 1000))
        floor_object.y_position = max(-1000, min(y, settings.canvas_height + 1000))
        floor_object.layout_width = min(max(width, 16), 1000)
        floor_object.layout_height = min(max(height, 10), 800)
        floor_object.layout_rotation = rotation % 360
        floor_object.layout_shape = shape
        floor_object.z_index = max(-50, min(z_index, 100))

    db.session.commit()

    return {"ok": True}


@main.route("/api/table-layout/table/<int:table_id>", methods=["POST"])
def update_layout_table(table_id):
    """
    Update table metadata directly from the floor-plan side panel.
    """
    table = db.get_or_404(PubTable, table_id)
    payload = request.get_json(silent=True) or {}

    number = str(payload.get("number", table.number)).strip()
    capacity = payload.get("capacity", table.capacity)
    area_id = payload.get("area_id", table.area_id)

    try:
        capacity = int(capacity)
        area_id = int(area_id)
    except (TypeError, ValueError):
        return {"ok": False, "error": "Invalid table details."}, 400

    if not number or capacity < 1:
        return {"ok": False, "error": "Table number and capacity are required."}, 400

    duplicate = db.session.scalar(
        db.select(PubTable).where(
            PubTable.number == number,
            PubTable.id != table.id,
        )
    )

    if duplicate:
        return {"ok": False, "error": "Another table already uses that number."}, 400

    table.number = number
    table.capacity = capacity
    table.area_id = area_id
    table.near_tv = bool(payload.get("near_tv", False))
    table.has_bench = bool(payload.get("has_bench", False))
    table.accessible = bool(payload.get("accessible", False))
    table.unsuitable_for_food = bool(
        payload.get("unsuitable_for_food", False)
    )
    table.active = bool(payload.get("active", True))

    db.session.commit()

    return {"ok": True}



@main.route("/api/floor-objects", methods=["POST"])
def create_floor_object():
    """Create a new non-bookable object in the floor-plan editor."""
    payload = request.get_json(silent=True) or {}

    allowed_types = {
        "wall",
        "door",
        "bar",
        "pillar",
        "tv",
        "fixed_table",
        "label",
        "area",
    }

    object_type = str(payload.get("object_type", "")).strip()

    if object_type not in allowed_types:
        return {"ok": False, "error": "Unsupported floor-plan object."}, 400

    defaults = {
        "wall": {
            "width": 220,
            "height": 16,
            "shape": "rectangle",
            "label": "Wall",
            "z": 1,
        },
        "door": {
            "width": 80,
            "height": 16,
            "shape": "rectangle",
            "label": "Door",
            "z": 2,
        },
        "bar": {
            "width": 240,
            "height": 70,
            "shape": "rectangle",
            "label": "Bar",
            "z": 2,
        },
        "pillar": {
            "width": 50,
            "height": 50,
            "shape": "square",
            "label": "Pillar",
            "z": 2,
        },
        "tv": {
            "width": 70,
            "height": 26,
            "shape": "rectangle",
            "label": "TV",
            "z": 3,
        },
        "fixed_table": {
            "width": 85,
            "height": 55,
            "shape": "rectangle",
            "label": "Non-bookable table",
            "z": 3,
        },
        "label": {
            "width": 150,
            "height": 40,
            "shape": "rectangle",
            "label": "Label",
            "z": 5,
        },
        "area": {
            "width": 300,
            "height": 220,
            "shape": "rectangle",
            "label": "Area",
            "z": -5,
        },
    }

    default = defaults[object_type]

    floor_object = FloorPlanObject(
        object_type=object_type,
        label=str(payload.get("label") or default["label"]),
        x_position=float(payload.get("x", 80)),
        y_position=float(payload.get("y", 80)),
        layout_width=float(payload.get("width", default["width"])),
        layout_height=float(payload.get("height", default["height"])),
        layout_shape=str(payload.get("shape", default["shape"])),
        layout_rotation=float(payload.get("rotation", 0)),
        z_index=int(payload.get("z_index", default["z"])),
        area_id=payload.get("area_id"),
    )

    db.session.add(floor_object)
    db.session.commit()

    return {
        "ok": True,
        "object": {
            "id": floor_object.id,
            "object_type": floor_object.object_type,
            "label": floor_object.label,
            "x": floor_object.x_position,
            "y": floor_object.y_position,
            "width": floor_object.layout_width,
            "height": floor_object.layout_height,
            "shape": floor_object.layout_shape,
            "rotation": floor_object.layout_rotation,
            "z_index": floor_object.z_index,
            "area_id": floor_object.area_id,
        },
    }


@main.route("/api/floor-objects/<int:object_id>", methods=["POST"])
def update_floor_object(object_id):
    """Update floor-plan object metadata from the inspector."""
    floor_object = db.get_or_404(FloorPlanObject, object_id)
    payload = request.get_json(silent=True) or {}

    label = str(payload.get("label", floor_object.label or "")).strip()
    area_id = payload.get("area_id")

    if area_id in ("", None):
        area_id = None
    else:
        try:
            area_id = int(area_id)
        except (TypeError, ValueError):
            return {"ok": False, "error": "Invalid area."}, 400

    floor_object.label = label or floor_object.object_type.replace("_", " ").title()
    floor_object.area_id = area_id

    db.session.commit()

    return {"ok": True}


@main.route("/api/floor-objects/<int:object_id>", methods=["DELETE"])
def delete_floor_object(object_id):
    floor_object = db.get_or_404(FloorPlanObject, object_id)
    db.session.delete(floor_object)
    db.session.commit()
    return {"ok": True}


@main.route("/api/floor-objects/<int:object_id>/duplicate", methods=["POST"])
def duplicate_floor_object(object_id):
    source = db.get_or_404(FloorPlanObject, object_id)

    duplicate = FloorPlanObject(
        object_type=source.object_type,
        label=source.label,
        x_position=source.x_position + 24,
        y_position=source.y_position + 24,
        layout_width=source.layout_width,
        layout_height=source.layout_height,
        layout_rotation=source.layout_rotation,
        layout_shape=source.layout_shape,
        z_index=source.z_index,
        area_id=source.area_id,
    )

    db.session.add(duplicate)
    db.session.commit()

    return {"ok": True, "id": duplicate.id}


@main.route("/api/table-layout/pair", methods=["POST"])
def create_layout_pairing():
    """Create a physical pairing relationship from the visual editor."""
    payload = request.get_json(silent=True) or {}

    table_a_id = payload.get("table_a_id")
    table_b_id = payload.get("table_b_id")

    try:
        first, second = sorted([int(table_a_id), int(table_b_id)])
    except (TypeError, ValueError):
        return {"ok": False, "error": "Choose two tables."}, 400

    if first == second:
        return {"ok": False, "error": "Choose two different tables."}, 400

    existing = db.session.scalar(
        db.select(TablePairing).where(
            TablePairing.table_a_id == first,
            TablePairing.table_b_id == second,
        )
    )

    if existing is None:
        db.session.add(
            TablePairing(
                table_a_id=first,
                table_b_id=second,
            )
        )
        db.session.commit()

    return {"ok": True}


@main.route("/api/table-layout/pair/<int:pairing_id>", methods=["DELETE"])
def delete_layout_pairing(pairing_id):
    pairing = db.get_or_404(TablePairing, pairing_id)
    db.session.delete(pairing)
    db.session.commit()
    return {"ok": True}


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



@main.route("/api/table-availability")
def table_availability_api():
    """
    Live availability used by the normal booking form.

    Under 10: normal automatic suitability / configured pairing suggestions.
    10+: manual Pool Room / Snug selection with larger-booking priority.
    """
    date_text = request.args.get("date", "")
    time_text = request.args.get("time", "")
    party_size = request.args.get("party_size", type=int) or 0
    preferred_area_id = request.args.get("preferred_area_id", type=int)
    wants_near_tv = request.args.get("wants_near_tv") == "1"
    avoids_bench = request.args.get("avoids_bench") == "1"
    is_eating_food = request.args.get("is_eating_food", "1") == "1"
    exclude_booking_id = request.args.get("exclude_booking_id", type=int)

    try:
        booking_date = datetime.strptime(date_text, "%Y-%m-%d").date()
        booking_time = datetime.strptime(time_text, "%H:%M").time()
    except ValueError:
        return {
            "tables": [],
            "groups": [],
            "large_booking_mode": False,
            "large_groups": [],
        }

    large_booking_mode = party_size >= 10
    blocked_by_large_party_ids = large_party_blocked_table_ids(
        booking_date,
        booking_time,
        STANDARD_BOOKING_DURATION,
    )

    table_rows = []

    for table in db.session.scalars(
        db.select(PubTable)
        .join(Area)
        .where(
            PubTable.active.is_(True),
            db.func.lower(Area.name) != "bar",
        )
        .order_by(*table_order_clause())
    ).all():
        available = table_is_available(
            table.id,
            booking_date,
            booking_time,
            STANDARD_BOOKING_DURATION,
            exclude_booking_id,
        )

        if large_booking_mode:
            if table.id in blocked_by_large_party_ids:
                status = "large_party"
                selectable = False
            else:
                conflicts = overlapping_normal_bookings(
                    [table.id],
                    booking_date,
                    booking_time,
                    STANDARD_BOOKING_DURATION,
                    exclude_booking_id,
                )

                if any(existing.party_size >= party_size for existing in conflicts):
                    status = "unavailable"
                    selectable = False
                elif conflicts:
                    status = "priority_move"
                    selectable = True
                elif is_large_booking_area(table):
                    status = "large_booking_available"
                    selectable = True
                else:
                    # Still selectable manually, but Pool Room / Snug remain the
                    # preferred suggestion areas for larger bookings.
                    status = "available"
                    selectable = True

            available = selectable
        else:
            selectable = available

            if not available:
                status = (
                    "large_party"
                    if table.id in blocked_by_large_party_ids
                    else "unavailable"
                )
            elif party_size > 0 and table.capacity == party_size:
                status = "ideal"
            elif party_size > 0 and table.capacity > party_size:
                status = "suitable"
            elif party_size > 0 and table.capacity < party_size:
                status = "too_small"
            else:
                status = "available"

        table_rows.append(
            {
                "id": table.id,
                "number": table.number,
                "capacity": table.capacity,
                "area_id": table.area_id,
                "area_name": table.area.name,
                "available": selectable,
                "status": status,
                "unsuitable_for_food": bool(table.unsuitable_for_food),
                "near_tv": bool(table.near_tv),
                "has_bench": bool(table.has_bench),
            }
        )

    groups = (
        available_pairing_groups(
            party_size,
            booking_date,
            booking_time,
            STANDARD_BOOKING_DURATION,
            preferred_area_id,
            wants_near_tv,
            avoids_bench,
            is_eating_food,
            exclude_booking_id,
        )
        if party_size > 0 and party_size < 10
        else []
    )

    large_groups = (
        large_booking_recommended_groups(
            party_size,
            booking_date,
            booking_time,
            STANDARD_BOOKING_DURATION,
            exclude_booking_id,
        )
        if large_booking_mode
        else []
    )

    return {
        "tables": table_rows,
        "groups": groups,
        "large_booking_mode": large_booking_mode,
        "large_groups": large_groups,
    }


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
        .where(
            Booking.booking_date == selected_date,
            Booking.status != "Cancelled",
        )
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
    areas = db.session.scalars(
        db.select(Area)
        .where(db.func.lower(Area.name) != "bar")
        .order_by(Area.name)
    ).all()

    tables = db.session.scalars(
        db.select(PubTable)
        .join(Area)
        .where(
            PubTable.active.is_(True),
            db.func.lower(Area.name) != "bar",
        )
        .order_by(*table_order_clause())
    ).all()

    if request.method == "POST":
        customer_name = request.form.get("customer_name", "").strip()
        customer_phone = normalise_phone(request.form.get("customer_phone", ""))
        party_size = request.form.get("party_size", type=int)
        number_of_children = request.form.get("number_of_children", type=int) or 0
        high_chairs_required = request.form.get("high_chairs_required", type=int) or 0

        if not customer_name or not customer_phone or not party_size:
            flash(
                "Customer name, phone number and party size are required.",
                "error",
            )
            return redirect(request.url)

        if high_chairs_required < 0 or high_chairs_required > party_size:
            flash(
                "High chairs required cannot be greater than the total party size.",
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
            if party_size >= 10:
                flash(
                    "Bookings of 10 or more require manual table selection "
                    "from the Pool Room / Snug.",
                    "error",
                )
                return redirect(request.url)

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

        moved_smaller_bookings = []
        if party_size >= 10:
            try:
                moved_smaller_bookings = (
                    relocate_smaller_bookings_for_priority_large_booking(
                        selected_tables,
                        party_size,
                        booking_date,
                        booking_time,
                        exclude_booking_id=exclude_id,
                    )
                )
            except ValueError as exc:
                db.session.rollback()
                flash(str(exc), "error")
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
        booking.high_chairs_required = high_chairs_required
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
                    high_chairs_required=high_chairs_required,
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
                repeat_rule.high_chairs_required = high_chairs_required
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

        message = "Booking updated." if exclude_id else "Booking created."

        if moved_smaller_bookings:
            message += (
                " Smaller booking"
                + ("s" if len(moved_smaller_bookings) != 1 else "")
                + " moved: "
                + ", ".join(moved_smaller_bookings)
                + "."
            )

        flash(message, "success")
        return redirect(
            url_for("main.bookings", date=booking_date.isoformat())
        )

    floor_objects = db.session.scalars(
        db.select(FloorPlanObject)
        .order_by(FloorPlanObject.z_index, FloorPlanObject.id)
    ).all()

    floor_settings = db.session.scalar(
        db.select(FloorPlanSetting).where(
            FloorPlanSetting.name == "main"
        )
    )

    return render_template(
        "booking_form.html",
        areas=areas,
        tables=tables,
        floor_objects=floor_objects,
        floor_settings=floor_settings,
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


@main.route("/bookings/<int:booking_id>/delete", methods=["POST"])
def delete_cancelled_booking(booking_id):
    """
    Permanently remove a cancelled booking. Intended for cleanup/test data.

    Any repeat-booking occurrence that referenced the booking is retained but
    detached from the deleted booking record.
    """
    booking = db.get_or_404(Booking, booking_id)

    if booking.status != "Cancelled":
        flash(
            "Only cancelled bookings can be permanently deleted.",
            "error",
        )
        return redirect(url_for("main.archive"))

    occurrences = db.session.scalars(
        db.select(RepeatBookingOccurrence).where(
            RepeatBookingOccurrence.booking_id == booking.id
        )
    ).all()

    for occurrence in occurrences:
        occurrence.booking_id = None
        occurrence.status = "Cancelled"

    customer_name = booking.customer.name
    db.session.delete(booking)
    db.session.commit()

    flash(
        f"Cancelled booking for {customer_name} permanently removed.",
        "success",
    )
    return redirect(url_for("main.archive"))


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
        high_chairs_required=rule.high_chairs_required,
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
        high_chairs = request.form.get("high_chairs_required", type=int) or 0

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

        if high_chairs < 0 or high_chairs > party_size:
            flash("High chairs cannot exceed total party size.", "error")
            return redirect(request.url)

        rule.weekday = weekday
        rule.booking_time = booking_time
        rule.party_size = party_size
        rule.number_of_children = children
        rule.high_chairs_required = high_chairs
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
        .where(LargePartyInquiry.status != "Cancelled")
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


@main.route("/large-parties/<int:inquiry_id>/cancel", methods=["POST"])
def cancel_large_party(inquiry_id):
    inquiry = db.get_or_404(LargePartyInquiry, inquiry_id)
    inquiry.status = "Cancelled"
    db.session.commit()

    flash(
        f"{inquiry.customer_name}'s large party was cancelled and moved to Archive.",
        "success",
    )
    return redirect(url_for("main.large_parties"))


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

    areas = db.session.scalars(
        db.select(Area).order_by(Area.name)
    ).all()

    tables = db.session.scalars(
        db.select(PubTable)
        .where(PubTable.active.is_(True))
        .order_by(*table_order_clause())
    ).all()

    if request.method == "POST":
        customer_name = request.form.get("customer_name", "").strip()
        customer_phone = normalise_phone(request.form.get("customer_phone", ""))
        party_size = request.form.get("party_size", type=int)
        children = request.form.get("number_of_children", type=int) or 0
        high_chairs = request.form.get("high_chairs_required", type=int) or 0

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

        if high_chairs < 0 or high_chairs > party_size:
            flash(
                "High chairs required cannot exceed the total party size.",
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

        reserve_for_rest_of_day = (
            request.form.get("reserve_for_rest_of_day") == "on"
        )

        expected_end_time = None

        if not reserve_for_rest_of_day and request.form.get("expected_end_time"):
            try:
                expected_end_time = datetime.strptime(
                    request.form["expected_end_time"], "%H:%M"
                ).time()
            except ValueError:
                flash("Please enter a valid expected end time.", "error")
                return redirect(request.url)

        if event_time and not reserve_for_rest_of_day:
            if expected_end_time is None:
                flash(
                    "Enter an expected end time or choose 'Reserve for rest of day'.",
                    "error",
                )
                return redirect(request.url)

            if expected_end_time <= event_time:
                flash(
                    "Expected end time must be later than the event start time.",
                    "error",
                )
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

        deposit_method = request.form.get("deposit_payment_method", "").strip() or None
        deposit_taken_by = request.form.get("deposit_taken_by", "").strip() or None

        deposit_due_date = None
        deposit_paid_date = None

        if request.form.get("deposit_due_date"):
            try:
                deposit_due_date = datetime.strptime(
                    request.form["deposit_due_date"], "%Y-%m-%d"
                ).date()
            except ValueError:
                flash("Enter a valid deposit due date.", "error")
                return redirect(request.url)

        if request.form.get("deposit_paid_date"):
            try:
                deposit_paid_date = datetime.strptime(
                    request.form["deposit_paid_date"], "%Y-%m-%d"
                ).date()
            except ValueError:
                flash("Enter a valid deposit paid date.", "error")
                return redirect(request.url)

        if deposit_paid > 0 and deposit_paid_date is None:
            flash(
                "The date the deposit was paid is required once a payment is recorded.",
                "error",
            )
            return redirect(request.url)

        if deposit_paid > 0 and deposit_method not in {"Cash", "Card"}:
            flash(
                "Choose Cash or Card when a deposit payment has been recorded.",
                "error",
            )
            return redirect(request.url)

        if deposit_paid > 0 and not deposit_taken_by:
            flash(
                "Enter who took the deposit payment.",
                "error",
            )
            return redirect(request.url)

        if inquiry is None:
            inquiry = LargePartyInquiry()
            db.session.add(inquiry)

        inquiry.customer_name = customer_name
        inquiry.customer_phone = customer_phone
        inquiry.event_date = event_date
        inquiry.event_time = event_time
        inquiry.expected_end_time = expected_end_time
        inquiry.reserve_for_rest_of_day = reserve_for_rest_of_day
        inquiry.party_size = party_size
        inquiry.number_of_children = children
        inquiry.high_chairs_required = high_chairs
        inquiry.food_type = food_type
        inquiry.menu_option_id = menu_option_id
        inquiry.catered_people = catered_people
        inquiry.quoted_price_per_head = price_per_head
        inquiry.quoted_food_total = food_total
        inquiry.deposit_required_amount = deposit_due
        inquiry.deposit_paid_amount = deposit_paid
        inquiry.deposit_due_date = deposit_due_date
        inquiry.deposit_paid_date = deposit_paid_date if deposit_paid > 0 else None
        inquiry.deposit_payment_method = deposit_method if deposit_paid > 0 else None
        inquiry.deposit_taken_by = deposit_taken_by if deposit_paid > 0 else None
        inquiry.occasion = request.form.get("occasion", "").strip() or None
        inquiry.notes = request.form.get("notes", "").strip() or None
        inquiry.status = request.form.get("status", "Enquiry").strip() or "Enquiry"

        db.session.flush()

        # Rebuild area/table reservations for this enquiry.
        LargePartyReservedArea.query.filter_by(inquiry_id=inquiry.id).delete()
        LargePartyReservedTable.query.filter_by(inquiry_id=inquiry.id).delete()

        reserved_area_ids = request.form.getlist("reserved_area_ids", type=int)
        reserved_table_ids = request.form.getlist("reserved_table_ids", type=int)

        for area_id in sorted(set(reserved_area_ids)):
            db.session.add(
                LargePartyReservedArea(
                    inquiry_id=inquiry.id,
                    area_id=area_id,
                )
            )

        for table_id in sorted(set(reserved_table_ids)):
            db.session.add(
                LargePartyReservedTable(
                    inquiry_id=inquiry.id,
                    table_id=table_id,
                )
            )

        db.session.flush()

        # If the newly reserved area/tables contain existing bookings, move
        # those bookings automatically to the next best available table.
        try:
            moved_bookings = relocate_bookings_conflicting_with_large_party(
                inquiry
            )
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
            return redirect(request.url)

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

        # Rebuild callback/follow-up reminders.
        InquiryReminder.query.filter_by(
            inquiry_id=inquiry.id,
            reminder_kind="manual",
        ).delete()

        reminder_dates = request.form.getlist("reminder_date")
        reminder_notes = request.form.getlist("reminder_note")
        reminder_completed = request.form.getlist("reminder_completed")

        for index, date_text in enumerate(reminder_dates):
            note = reminder_notes[index].strip() if index < len(reminder_notes) else ""

            if not date_text and not note:
                continue

            if not date_text or not note:
                db.session.rollback()
                flash("Each reminder needs both a date and a note.", "error")
                return redirect(request.url)

            try:
                reminder_date = datetime.strptime(date_text, "%Y-%m-%d").date()
            except ValueError:
                db.session.rollback()
                flash("Enter a valid reminder date.", "error")
                return redirect(request.url)

            db.session.add(
                InquiryReminder(
                    inquiry_id=inquiry.id,
                    reminder_date=reminder_date,
                    note=note,
                    reminder_kind="manual",
                    completed=(
                        index < len(reminder_completed)
                        and reminder_completed[index] == "1"
                    ),
                )
            )

        # Keep one automatic reminder in sync with the promised deposit date.
        # If the deposit is already fully paid, or the expected date is cleared,
        # no automatic deposit reminder is needed.
        auto_deposit_reminder = db.session.scalar(
            db.select(InquiryReminder).where(
                InquiryReminder.inquiry_id == inquiry.id,
                InquiryReminder.reminder_kind == "deposit_due",
            )
        )

        deposit_still_due = (
            float(inquiry.deposit_required_amount or 0)
            - float(inquiry.deposit_paid_amount or 0)
        ) > 0.009

        if inquiry.deposit_due_date and deposit_still_due:
            reminder_note = (
                f"Deposit expected today — £{inquiry.deposit_balance:.2f} "
                f"still due for {inquiry.customer_name}'s large party."
            )

            if auto_deposit_reminder is None:
                auto_deposit_reminder = InquiryReminder(
                    inquiry_id=inquiry.id,
                    reminder_kind="deposit_due",
                    completed=False,
                )
                db.session.add(auto_deposit_reminder)

            auto_deposit_reminder.reminder_date = inquiry.deposit_due_date
            auto_deposit_reminder.note = reminder_note
            auto_deposit_reminder.completed = False
        elif auto_deposit_reminder is not None:
            db.session.delete(auto_deposit_reminder)

        db.session.commit()

        message = (
            "Large party enquiry updated."
            if request.endpoint == "main.edit_large_party"
            else "Large party enquiry created."
        )

        if moved_bookings:
            message += " Moved: " + "; ".join(moved_bookings)

        flash(message, "success")
        return redirect(url_for("main.large_parties"))

    return render_template(
        "large_party_form.html",
        inquiry=inquiry,
        options=options,
        extra_options=extra_options,
        areas=areas,
        tables=tables,
        selected_reserved_area_ids=(
            [link.area_id for link in inquiry.reserved_areas]
            if inquiry else []
        ),
        selected_reserved_table_ids=(
            [link.table_id for link in inquiry.reserved_tables]
            if inquiry else []
        ),
        today=date.today(),
    )
