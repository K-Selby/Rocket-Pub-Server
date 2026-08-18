# Pub Booking System - Starter

Local Flask/SQLite pub booking application.

## Current features

- Dashboard showing today's bookings
- Customer records created automatically when a booking is made
- Returning customer recognition by phone number
- Name/phone customer search
- Saved seating preferences
- Configurable pub areas
- Configurable tables
- Edit tables after creation
- Table characteristics:
  - capacity
  - area
  - near TV
  - bench seating
  - accessible
  - active/inactive
- Numerically ordered table numbers
- Physically valid table pairings
- Booking creation
- 3-hour standard booking duration
- Booking times from 12:15 to 19:30 in 15-minute intervals
- Late food-order warning after 18:45
- Sunday-specific 19:30 kitchen closing warning
- Manual table assignment
- Automatic single-table or paired-table allocation
- Allocation preferences:
  - area
  - specific table
  - near TV
  - no bench seating
- Booking overlap prevention
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

Open:

http://127.0.0.1:8000

Another device on the same Wi-Fi can use the Mac's local address, e.g.:

http://192.168.1.173:8000

## Database

The database is stored at:

instance/pub_booking.db

The revised starter includes a small compatibility step that adds the new
bench-related columns to a database created by the earlier starter version.
