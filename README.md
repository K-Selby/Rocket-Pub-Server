# Pub Booking System - v4.1

## Added in v4

- Real Rocket Pub buffet packages from the supplied menu:
  - Option 1 — The Basics — £8.95/head
  - Option 2 — The Classic — £9.95/head
  - Option 3 — The Upgraded — £10.95/head
  - Option 4 — The Full Works — £12.95/head
- Package contents shown in the Large Party section
- Standard extra hot dishes at £6.50/head, minimum 25 people
- Multiple extra dishes per enquiry
- Each extra dish can have its own headcount
- Custom extra dishes with custom price/head and quantity
- "Unsuitable for food" table characteristic
- Normal bookings default to "Eating food"
- Drinks-only bookings can untick Eating food
- Automatic allocation heavily penalises food-unsuitable tables but keeps them
  available as a last resort
- Dashboard previous/next day navigation and date picker
- New bookings cannot be in the past, including earlier on the current day
- Customer edit and delete controls
- Weekly repeat booking rules
- Repeat bookings appear on the dashboard one week before the next occurrence
- Confirm, Skip this time, and Edit repeat controls
- Confirm creates the actual booking and runs normal automatic table allocation

## Important delete behaviour

Deleting a saved customer also deletes their linked normal booking history and
repeat schedules. The UI displays a confirmation warning before doing this.

## Run

```bash
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Open:

http://127.0.0.1:8000


## v4.1 hotfix

Fixed an IntegrityError when enabling a weekly repeat booking from an existing
booking. RepeatBooking rows now receive weekday, time, party size and all other
required fields before SQLAlchemy first flushes them to SQLite.
