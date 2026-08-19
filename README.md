# Pub Booking System - v5 Complete Floor Plan Editor

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


## v5 — Table layout editor

- New Table Layout screen.
- Drag-and-drop table positioning.
- Resize tables using the bottom-right handle.
- Table shapes:
  - rectangle
  - square
  - round
  - oval
- Rotate selected tables in 15-degree steps.
- Table positions, sizes, shapes and rotations persist in SQLite.
- Edit table number, capacity, area and booking characteristics directly from
  the floor-plan side panel.
- Create/remove physical table-pairing relationships from the visual editor.
- Pairings are drawn as dashed links on the layout.
- Layout supports large canvases with scrolling for an accurate recreation of
  the pub.
- Existing tables automatically appear in the editor; no re-entry is required.

The visual floor plan is currently an editor/configuration screen. The next
stage is to reuse this exact layout on the live booking screen so tables can be
clicked and colour-coded by availability.


## Complete v5 additions

The floor-plan editor now supports the actual building layout as well as
bookable tables.

Non-bookable floor-plan objects:
- walls
- doors/openings
- bar/counter
- pillars
- TVs
- non-bookable/fixed tables
- pool table
- stairs
- area blocks
- text labels

Floor-plan objects:
- are completely separate from PubTable
- are never offered by the booking allocator
- can be dragged, resized and rotated
- can change shape
- can be moved forward/backward in the visual layer order
- can be duplicated
- can be deleted
- can have editable labels
- can optionally be associated with one of the configured pub areas

Bookable tables remain the normal numbered PubTable records and can still be:
- positioned
- resized
- reshaped
- rotated
- paired
- edited from the inspector

This master floor plan is now ready to be reused in the live booking screen.


## v5.0.1 hotfix

Fixed the Table Layout page failing to render because Jinja does not support
Python-style list comprehensions inside `{{ ... }}` expressions. Pairing data is
now emitted with a normal Jinja `{% for %}` loop.
