# Pub Booking System - Starter

A lightweight Flask/SQLite starter application for a local pub booking system.

## Included in this first version

- Dashboard showing today's bookings
- Customer records
- Customer search by name or phone number
- Stored customer preferences
- Configurable pub areas
- Configurable tables and capacities
- Table characteristics such as near-TV/accessibility/window
- Table pairing definitions
- Booking creation
- Manual table assignment
- Simple automatic single-table allocation
- Booking overlap prevention
- Multi-table bookings
- Booking cancellation
- Date-based booking view
- Local-network hosting support

## Run on macOS

From the project folder:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Then open:

http://127.0.0.1:5000

For another device on the same Wi-Fi, use the Mac's local IP:

http://YOUR-MAC-IP:5000

## Database

The SQLite database is created automatically at:

instance/pub_booking.db

Do not commit the database file to Git.
