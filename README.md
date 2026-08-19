# Rocket Pub Server - v6.1 Email Verification

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


## v5.1 floor-plan usability overhaul

- Removed Pool Table and Stairs from the add-object toolbar.
- Reworked dragging/resizing to use window-level pointer tracking for much
  smoother interaction.
- Drag/resizing calculations are zoom-aware, preventing jumping while zoomed.
- Objects can no longer be resized beyond the right/bottom edge of the map.
- Walls can now stretch all the way to the map boundary.
- The floor-plan map can be resized from 600x400 up to 3000x2200.
- The editor viewport height can be changed with a slider or the browser's
  vertical resize handle.
- Zoom range is deliberately limited to 35%–125%.
- Fit Whole Map automatically chooses a zoom that shows the complete floor plan.
- Zooming keeps the centre of the current view stable where possible.
- Pairing lines are calculated from unscaled map coordinates so they remain
  stable at every zoom level.


## v5.1.1 rotated wall boundary fix

Fixed rotated walls/objects being stopped away from the map edge. CSS rotation
changes the object's visual bounding box while `offsetLeft` still describes its
unrotated box. Dragging, resizing and map-resizing now use rotation-aware visual
bounds, allowing a long wall rotated 90 degrees to sit flush against the left,
right, top or bottom edge of the floor plan.


## v5.2 booking-screen floor-plan integration

- Normal booking table boxes now use a horizontal slider.
- Cards sort automatically from ideal through unavailable.
- Hovering a table card highlights its physical table on the full floor plan.
- Hovering a physical table highlights/scrolls its card into view.
- Clicking either the card or map selects/deselects that table.
- Large-party-reserved tables use a separate purple status.
- Suggested connected table combinations remain available.
- The complete saved pub layout is displayed under the slider as a spatial reference.


## v5.2.1 rotated-position persistence fix

- Fixed walls/objects placed flush against the left/top edge moving inward after
  Save Layout, page reload, adding another object, or opening the booking form.
- Rotated objects can require a negative unrotated x/y coordinate even when the
  visible object is completely inside the map. The server previously forced
  those coordinates back to zero.
- Signed rotation-aware coordinates are now preserved in SQLite.
- Rotated bookable tables use the same persistence fix.
- Adding a new floor-plan object now saves the current layout before reloading
  the editor, preventing unsaved position changes from being lost.


## v5.3 dashboard floor map

- The dashboard keeps the existing chronological booking list.
- The complete saved pub floor plan is now shown underneath the list.
- Every active bookable table displays its booking count for the selected day.
- Tables with bookings are visually distinguished from tables with none.
- Hovering a table fades the other bookable tables and opens a tooltip showing:
  - customer name
  - booking start/end time
  - party size
  - eating/drinks-only status
- Multi-table bookings appear on every physical table assigned to that booking.
- Dashboard date navigation automatically updates the floor-plan booking counts.
- The map uses the same walls, bar, TVs, pillars, labels and other saved
  non-bookable floor-plan objects as the editor.


## v5.3.1 dashboard map placement fix

The dashboard floor-plan markup had accidentally been inserted inside the
Jinja title block, which meant it was rendered into the page title rather than
the visible dashboard content. The map is now placed after the booking list
inside the dashboard content block.


## v5.3.2 dashboard map width fix

- Dashboard floor plan now fits to the full available card width.
- Removed the fixed-height scaling constraint that caused a large blank area
  on the right of wide floor plans.
- Dashboard map container now follows the fitted floor-plan height.


## v5.3.3 dashboard map edge clipping fix

- Dashboard floor plan now clips all objects exactly to the saved map boundary.
- Fixed rotated walls/doors visually spilling past the right and bottom border
  when the dashboard map was scaled to fill the card width.
- The editable floor-plan screen is unchanged; only the read-only dashboard
  view uses clipping.


## v5.4 large-party dashboard integration

- Setting an expected/promised deposit date automatically creates a dashboard
  reminder on that date while money remains outstanding.
- The automatic reminder moves when the expected date changes and is removed
  when the date is cleared or the deposit is fully paid.
- Manual callback reminders remain separate and editable.
- Large-party deposit fields now use separate Expected Deposit and Payment
  Received cards for clearer day-to-day use.
- Large parties taking place on the selected dashboard date now have their own
  dashboard section with times, status, party size, reserved areas/tables and
  deposit summary.
- Tables/areas reserved for large parties are purple on the dashboard map.
- Hovering a purple table shows the large-party customer, time, party size,
  occasion and status.
- Whole-area reservations automatically colour every active table in that area;
  linked area-block floor-plan objects are also shaded purple.


## v5.4 large-party dashboard and deposit reminders

- Expected/promised deposit dates automatically create a dashboard reminder.
- Changing the expected date automatically moves that reminder.
- Clearing the expected date, or fully paying the required deposit, removes the
  automatic deposit reminder.
- Automatic deposit reminders remain separate from manually added callback
  reminders.
- Large parties taking place on the selected dashboard date now have their own
  dashboard list showing:
  - start/end time or rest-of-day status
  - customer
  - party size
  - occasion/status
  - reserved areas
  - specifically reserved tables
  - deposit paid/required and expected date
- Large-party-reserved tables are purple on the dashboard map.
- Reserving an entire area makes every bookable table in that area purple.
- If a floor-plan Area Block is linked to the same pub area, that whole visual
  area is also shaded purple.
- Hovering a purple table shows the large-party customer, reservation time,
  party size, occasion and status alongside any ordinary bookings.
- The large-party deposit section has separate Expected Deposit and Payment
  Received cards, with clear automatic-reminder guidance.


## v5.5 dashboard and booking-duration refinements

- Standard normal booking duration changed from 3 hours to 2 hours 30 minutes.
- Existing saved bookings keep their stored duration; newly created/confirmed
  normal bookings use 150 minutes.
- Large-party deposit/payment section now uses the full available form width
  instead of inheriting the narrow normal-booking deposit-panel limit.
- Expected Deposit and Payment Received cards are equal-width and less cramped.
- Large-party dashboard rows now show:
  - total food/extras amount
  - deposit paid
  - outstanding balance = total amount minus deposit paid
  - expected deposit date when money is still due
- A table reserved for a large party now keeps its numeric normal-booking count
  on the dashboard map and shows a separate purple LP badge. This means a table
  with normal bookings earlier in the day still visibly shows that count before
  the later large-party reservation.


## v5.6 live dashboard booking states

Dashboard normal-booking rows now change automatically through three visual
states:

- White / Upcoming:
  - before the booking's start time
  - full booking details remain visible
- Yellow / Here now:
  - from booking start until scheduled end
  - shows a "They've left" button
- Green / Finished:
  - automatically after the scheduled end time
  - or immediately when staff press "They've left"
  - row collapses into a smaller/minimised history rectangle

The dashboard checks today's rows every 30 seconds so a booking can move from
white to yellow and yellow to green without refreshing the page.

Pressing "They've left" persists the booking as Completed and records the
completion time. A manually completed booking stops blocking its table(s)
immediately, allowing those tables to be allocated to a later booking.
Past-day bookings display as completed/minimised automatically while future-day
bookings remain white/upcoming.


## v5.7 archive and test-data cleanup

- Cancelled normal bookings no longer appear on the active Bookings screen.
- Cancelled large-party enquiries no longer appear in the active Enquiries box.
- New Archive screen contains:
  - cancelled bookings
  - cancelled large-party enquiries
  - past normal bookings
  - past large-party events
- Cancelled bookings and cancelled large-party enquiries can be permanently
  deleted from Archive, making it easy to clear test data.
- Permanent deletion is deliberately limited to Cancelled records.
- Deleting a cancelled normal booking safely detaches any repeat occurrence that
  pointed to it before removing the booking.
- Archive is available from the top navigation and from Bookings/Large Parties.


## v5.8 Rocket Pub Server brand refresh

- Renamed the user-facing application to Rocket Pub Server.
- Added The Rocket Pub Liverpool green logo to the application header.
- Reworked the site around the new deep-green and light-sage colour scheme.
- Updated header/navigation, buttons, cards, badges, inputs and floor-plan
  surrounds while keeping red/yellow/purple operational status colours distinct.
- Increased the main desktop width slightly for better use of laptop screens.


## v5.8.1 centred brand panel

- Restored the Rocket Pub artwork as the full browser background.
- Main application content now sits inside one bordered translucent central
  panel instead of washing the wallpaper out across the entire page.
- The outer left/right margins intentionally expose the full background image.
- Added a subtle glass effect, green-tinted border and shadow to separate the
  operational interface from the branded wallpaper.
- Responsive sizing keeps the same treatment on laptops, tablets and phones.


## v5.8.3 active navigation

- The current section is now highlighted in the top navigation bar.
- Related screens inherit the same section highlight, so:
  - New/Edit Booking highlights Bookings
  - New/Edit Large Party highlights Large Parties
  - Customer edit highlights Customers
  - Table create/edit highlights Tables
- The active state uses the light sage Rocket Pub branding rather than a generic colour.


## v6 user accounts and permissions

Roles:
- Staff
  - dashboard/bookings/large parties/customers/archive
  - read-only Table Map with table properties
  - cannot edit table records or floor plan
  - cannot permanently delete archived bookings/enquiries
  - cannot manage users
- Manager
  - all Staff access
  - Tables and Table Layout editing
  - permanent deletion of cancelled archived records
  - can create, disable and reset Staff accounts
- Admin
  - full access
  - can additionally create/manage Manager accounts and change Staff/Manager roles

Initial administrator on a new database:
- username: admin
- temporary password: Password

All newly created users receive the temporary password `Password`. The system
forces them to choose a new password on first login before any operational page
is accessible. Passwords are stored using Werkzeug password hashing rather than
plain text.

Forgotten-password self-service is intentionally deferred. Managers/Admin can
currently reset accounts back to the temporary password `Password`, after which
the user is again forced to change it.


## v6.1 email verification

- After a user's mandatory first password change, Rocket Pub Server prompts them
  to add an email address.
- Email setup is optional and can be skipped with "Do this later".
- Users can later add/change their own email from the Email link in the header.
- Verification uses a six-digit one-time code valid for 15 minutes.
- Codes are stored hashed rather than in plain text.
- Managers can add/change email addresses for Staff accounts.
- Admin can do the same for Staff and Manager accounts.
- New-user creation includes an optional email field.
- Email states in Users:
  - Verified
  - Pending verification
  - No email

### Sending verification mail

The application defaults to `ROCKET_EMAIL_MODE=console` so email verification
can be tested immediately without putting mail credentials into source code.
The six-digit code is printed in the Flask terminal.

The sender address defaults to:

`rocketpubserver@outlook.com`

A generic STARTTLS SMTP backend is present for providers that support password
SMTP authentication. Outlook.com itself now requires Microsoft Modern
Authentication/OAuth2, so the live `rocketpubserver@outlook.com` sender still
needs a Microsoft OAuth connection before production email delivery is enabled.
No Outlook password is stored in this repository.


## v6.2 Microsoft Outlook / Graph email

The Admin Users screen now includes a Rocket Email connection card.

1. Keep the Microsoft Client ID, Client Secret and Tenant ID in local `.env`.
2. Sign in to Rocket Pub Server as Admin.
3. Open Users.
4. Press **Connect Microsoft Email**.
5. Sign in as `rocketpubserver@outlook.com` and approve access.
6. Microsoft tokens are stored locally in
   `instance/microsoft_token_cache.bin`.
7. Verification codes are then sent through Microsoft Graph `/me/sendMail`.

Both `.env` and `instance/microsoft_token_cache.bin` are ignored by Git.

The returned project ZIP intentionally does not contain the real `.env` file
or Microsoft token cache.


## v6.2.1 admin-only email management

- Managers can no longer set, replace, clear or verify another user's email.
- Managers still see email status for accounts they can view.
- Only Admin can attach an email to Staff/Manager accounts from Users.
- If an account already has a verified email, the Set Email field disappears;
  Admin must deliberately Reset Email before assigning another address.
- Pending emails show an Admin verification-code field directly on Users.
- Admin can enter the six-digit code, resend the code, or clear the pending
  address.
- New-user email entry is shown only when Admin creates the account.
- Individual users still retain their own first-login/self-service email setup.


## v6.3 forgotten password

- Login screen now has **Forgot password?**
- User enters their username.
- Reset is available only when the account has a verified email.
- Rocket Pub Server emails a six-digit reset code through the connected Outlook
  / Microsoft Graph sender.
- Reset codes expire after 15 minutes and are stored hashed.
- After the code is verified, the user chooses and confirms a new password.
- Successful reset clears the reset token and returns the user to sign-in.
- Accounts without a verified email must use the existing manager/admin password
  reset process.


## v6.4 allergen menu and navigation cleanup

### Staff allergen lookup
All logged-in users can open **Allergen Menu** and:
- search by meal, ingredient or description
- filter by category
- show only meals that are milk free
- nut free
- egg free
- gluten free
- vegetarian
- vegetarian or able to be made vegetarian
- inspect listed ingredients and vegetarian modifications

### Management
Managers/Admin can:
- add allergen menu items
- edit ingredients/allergen flags
- mark meals vegetarian
- mark meals as able to be made vegetarian and record the required change
- permanently delete menu items

Staff have read-only allergen access; the write routes are protected server-side.

### Test data
A small demonstration menu is seeded only when the allergen table is empty.
It is clearly labelled test data in the interface and is intended to be
replaced with verified Rocket Pub menu and ingredient information.

### Navigation
The header is less crowded:
- Dashboard
- Bookings
- Large Parties
- Allergen Menu
- More: Customers, Table Map, Archive
- Management (Manager/Admin): Tables, Table Layout, Users


## v6.4.1 tri-state allergens and side choices

Categories are now fixed to:
- Main Meals
- Starters
- Sides
- Kids Meals
- Desserts

Each of the four test allergens now has three states:
- Green: Free
- Yellow: May contain
- Red: Contains

Free-from searches are strict: both Red and Yellow are excluded.

Main Meals can be linked to any number of items in the Sides category. When
staff select allergen-free filters, Rocket Pub Server separately checks every
linked side and suggests only sides confirmed Green for all selected allergens.
The full side list can still be expanded so staff can see why another side was
excluded.


## v9 rota and staff diary

### Rota
- Sunday-Saturday weekly rota.
- Managers create Draft rotas.
- Staff cannot see a Draft.
- Managers can manually add/edit/remove shifts.
- `F` is stored as a variable Finish rather than a fake clock time.
- Projected hours use manager-editable estimated Finish times:
  Monday 22:00, Tuesday 23:00, Wednesday 22:00, Thursday 23:00,
  Friday 00:00, Saturday 00:00 and Sunday 22:30.
- Managers issue/publish the rota when ready.
- Issued rotas can be downloaded as a high-resolution PNG.

### Smart Auto-fill
Auto-fill uses:
- recurring staff availability
- approved date-specific Staff Diary overrides
- work role (Front of House, Kitchen, Both, Glass Collector)
- maximum/target weekly hours
- regular vs casual status
- historical rota pattern bonuses inferred from the supplied June-August rota
  photographs
- manager-editable shift-slot templates

Auto-fill only creates suggestions. It never publishes the rota.

### Initial staff assumptions
- Hannah, Charl/Charlotte and Erin are marked Casual / odd shifts.
- Alara is marked Casual + Glass Collector and is normally available
  Friday-Sunday only.
- Historical scoring recognises recurring patterns for Brooke, Niamh, Lois,
  Jenna, Maggie, Kieran and Scott.
- All of these rules can be changed by a manager.

### Staff Diary
Staff can submit:
- day-off/unavailable requests
- a specific time window they can work on a date
- notes

Managers can:
- add entries for anyone
- approve/reject requests
- mark a date NO ONE OFF
- view diary entries alongside the rota builder

### Shift swaps
- Staff can request another person to take a shift.
- They can alternatively choose one of the other person's shifts for a true
  two-way swap.
- The other staff member accepts/declines.
- Accepted swaps go to a manager.
- When approved, the live rota is changed automatically.

### Navigation
Rota is a primary navigation item.
Staff Diary sits under More.
Manager rota tools are accessible from the Rota screen.
