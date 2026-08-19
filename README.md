# Pub Booking System - v4.4

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


## v4.2

- Large-party enquiries can reserve whole pub areas.
- Large-party enquiries can reserve multiple individual tables.
- Those reservations block normal booking allocation during the overlapping
  three-hour event window.
- Existing normal bookings on newly reserved tables are automatically moved to
  the next suitable available table.
- If no alternative table exists, the large-party reservation save is rejected
  rather than leaving a booking conflict.
- Fixed custom extra-dish name controls showing when "Custom dish" was not
  selected.
- Added total food amount for large-party enquiries.
- Added remainder after deposit.
- Large-party deposits now record Cash/Card and the staff member who took them.


## v4.3

- Large-party enquiries now include an expected end time.
- Reserved areas/tables are blocked from event start until expected end.
- "Reserve for rest of day" can be selected instead of an end time.
- Rest-of-day reservations remain blocked through 23:59:59.
- The form clearly notes that the selected area/table is closed to further
  bookings for the rest of that day.
- Existing older enquiries without an end time safely fall back to a three-hour
  blocking window.


## v4.4

- High-chair count added to normal bookings, weekly repeats and large-party enquiries.
- Large-party deposits now support:
  - optional promised/due date
  - mandatory paid date when money has been recorded
  - Cash/Card
  - staff member who took payment
  - remaining balance
- Selecting large-party areas filters the specific-table selector to those areas.
- Multiple callback/follow-up reminders can be attached to a large-party enquiry.
- Due reminders appear on the dashboard on the selected date.
- Normal booking table availability updates live:
  - green = exact-capacity available table
  - yellow = available but larger than necessary
  - red = unavailable / already occupied
  - grey = too small alone but potentially useful in a valid combination
- Valid configured table combinations are suggested live.
- Normal bookings can use more than two tables, provided the selected tables form
  one connected group through configured table-pairing relationships.
