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


## v9.1 rota corrections

- Removed Front of House / Glass Collector / Regular / Casual labels from the
  rota display. Those internal compatibility fields no longer clutter the UI.
- Matt is archived because he no longer works at the pub.
- Erin, Hannah, Leoni and Charl are placed at the bottom of the rota by default.
- Managers enter shifts using the same shorthand as the paper rota:
  `5-9`, `3-8`, `12-6`, `4-F`, `6-F`.
- Shift editing is now one text field instead of separate start/end/Finish
  controls.
- Auto-fill was rewritten to be deliberately conservative. It uses a realistic
  weekly coverage skeleton taken from the supplied rotas, assigns only one
  shift per person per day, heavily penalises occasional staff, respects
  availability, and balances projected weekly hours.
- Common shift patterns can be edited per staff profile and are used as an
  Auto-fill ranking hint.


## v9.2 rota autofill crash and staff archive fixes

- Fixed the `NameError: parse_rota_shift_text is not defined` crash in Auto-fill.
- Active rota order now follows the established paper rota ordering:
  Gemma, Brooke, Niamh, Lois, Jenna, Maggie, Alara, Scott, Kieran.
- Hannah, Charl, Leoni, Erin and Matt are archived by default.
- Archived staff stay in historical rota records but disappear from future rota
  views and Auto-fill.
- Managers can add a staff profile from the Rota Builder or Staff Profiles.
- Each rota name has a small `•••` options menu for Edit Staff / Archive Staff.
- Staff Profiles has Restore for archived staff.
- Because future rota views are built from active staff profiles, archive/restore
  changes automatically apply to future rota weeks without rewriting old rota
  history.


## v9.2.1 archive route hotfix

- Fixed the 500 error opening Rota Builder caused by the template referencing
  `main.rota_profile_archive` before that Flask route existed.
- Added working Manager-only Archive and Restore routes.
- Remove/archive now always preserves historical rota records.
- Archived staff disappear from future rota views and Auto-fill but can be
  restored from Staff Profiles.


## v9.2.2 Auto-fill time import hotfix

- Fixed the Auto-fill 500 error caused by `parse_rota_shift_text()` calling
  `time(...)` without importing `time` from Python's `datetime` module.


## v9.3 manual rota builder

- Auto-fill has been removed completely.
- Estimated/projected hours have been removed from the rota and rota image.
- Empty rota cells are genuinely blank. A manager clicks a blank cell and
  types paper-rota notation such as `5-9`, `12-6` or `4-F`.
- Existing shifts are clicked directly to edit them.
- A day-off/unavailable diary request greys out that staff/date cell and blocks
  shift entry.
- Date-specific availability appears as a compact `A` badge on that cell, for
  example `A 5-9`, while the manager can still click the cell and assign the
  shift.
- Pending availability requests use a yellow availability badge; approved
  availability uses green.


## v9.3.1 clear rota draft

- Managers now have a `Clear rota` button while editing a draft.
- Clearing removes every shift from that rota week in one action.
- A confirmation prompt warns that all entered shifts for the week will be removed.
- Staff Diary / availability entries are not deleted.
- Published rotas cannot be cleared unless they are first returned to draft.


## v9.3.2 simple add staff

- The detailed Add Staff Profile form is no longer used for adding staff.
- Pressing `Add staff` now shows only the four archived occasional staff:
  Hannah, Charl, Leoni and Erin.
- Selecting one restores that profile to future rotas.
- The detailed staff form remains available only from Edit Staff.


## v9.3.2 archived-only Add Staff

- `Add staff` no longer creates a new staff profile.
- It now shows only archived Hannah, Charl, Leoni and Erin.
- Pressing `Add to rota` restores that person to the active future rota list.
- Matt remains archived and is not offered in Add Staff.
- Login-account linking is left for a later stage.


## v9.3.3 inline Add Staff

- Removed the Add Staff button from the top of the rota editor.
- Archived Hannah, Charl, Leoni and Erin now appear in an Add Staff row at the bottom of the rota table.
- Managers can restore a person directly from that row without leaving the rota editor.
- Once restored, that person's name disappears from the Add Staff row and returns to the active rota list.


## v9.3.3 inline Add Staff and diary changes

- Add Staff is now a row at the bottom of the Rota Builder table.
- The row lists only archived Hannah, Charl, Leoni and Erin.
- Clicking a name immediately restores them and returns to the same rota.
- No separate Add Staff page is needed from the Rota Builder.
- Staff Diary uses rota shorthand for specific availability: `4-9`, `5-F`,
  `12-6`, etc.
- The rota shows those requests as compact `A 4-9` / `A 5-F` markers.
- Staff Diary now shows all seven dates in the selected week as checkboxes.
  Multiple dates can be selected and submitted together, including several
  days off in one request.


## v9.3.4 compact shift editor fix

- Fixed the narrow rota-cell editor so Add/Cancel no longer spill outside the cell.
- Add and Cancel are now compact ✓ / × controls beside the shift field.
- The shorthand parser explicitly supports `4-8`, `5-9`, `12-6`, `4-F`, etc.
- Invalid shift text now shows the actual validation error instead of the generic
  "Check the shift details" message.


## v9.3.4 rota request and diary range fixes

- Fixed the cramped rota cell editor so shift input, Add/Save and Cancel fit.
- Specific-shift availability is now a full-width visible marker such as `4-8`.
- Managers can press `+` beside a requested specific shift to put that shift
  directly onto the rota; a pending request is approved at the same time.
- Staff Diary no longer contains format-help comments or example placeholders.
- Staff Diary controls are aligned to the same compact height.
- Day-off requests now use From / To dates rather than seven checkboxes tied to
  the visible week.
- Date ranges can cross rota weeks, e.g. Friday through Wednesday. One diary
  entry is created for every date in the inclusive range.


## v9.3.5 confirmed availability display fix

- When a manager presses `+` on a requested shift such as `4-8`, the
  availability suggestion no longer remains visible as a second rota slot.
- The rota cell now shows only the actual confirmed shift.
- The original Staff Diary request remains in the diary/history.


## v9.3.6 simplified staff and K rota code

- Removed target weekly hours and maximum weekly hours from the staff UI.
- Removed recurring weekday availability and its edit form.
- Removed Common Shifts / Auto-fill-related staff settings.
- Rota availability is now based only on date-specific Staff Diary entries.
- The staff options menu now contains Archive Staff only.
- Fixed the staff `•••` menu stacking behind the row underneath.
- Managers can type `K` directly into a rota cell. It is stored and displayed
  as `K`, matching the paper rota.


## v9.3.6 rota and staff cleanup

- Removed the rota-builder instruction banner.
- Removed the old target-hours, max-hours and recurring weekday-availability
  editing UI. Staff rota editing now contains only the staff name.
- `K` can be entered directly into a rota cell and displays as `K`.
- Staff `•••` menus are layered above the following table rows.
- Shift editors stay inside their own table cell, including Saturday.
- Staff Diary automatically sets `To` to the selected `From` date. `To` cannot
  be earlier than `From`, but the user can extend it to any later date.
- Managers can rename staff accounts from the Users screen; administrators can
  rename manager accounts as well.


## v9.3.7 roster, diary and users cleanup

- Archived rota staff are handled only from the bottom row of the Rota Builder.
- Any archived current staff member appears there; Matt remains excluded because
  he no longer works at the pub.
- Archiving no longer opens a separate Rota Staff page. It keeps the manager on
  the same draft and moves the name to the archived row.
- Restoring a staff member makes them active immediately and they remain on
  current/future rota drafts until explicitly archived again.
- Rota profiles automatically link to matching user accounts by name where an
  older profile was not already linked.
- Staff Diary entries for another person can now only be created by Admin.
  Staff and Managers can submit only for their own linked rota profile.
- Managers do not get email-setting controls for user accounts.
- User Name, Role and Reset Password actions are now behind a single Edit
  control. Role and email remain Admin-only.
- Removed the `F = Finish (actual finishing time varies)` footer from saved rota
  images.


## v9.3.8 manager user deletion

- Managers now get `Delete user` instead of Disable/Enable for staff accounts.
- Managers can delete staff login accounts only; they cannot delete manager or
  administrator accounts or their own account.
- Deleting a login unlinks it from the rota profile first, so the person's rota
  profile, shifts and Staff Diary history are retained.
- Admin keeps the existing Disable/Enable control.


## v9.3.8 user delete and rota image fix

- Managers use `Delete user` for staff accounts instead of Disable.
- Deleting a login does not delete that person's rota profile or historical
  rota/diary records; it only removes the login link.
- Fixed saved rota images being clipped at the bottom. The PNG canvas now
  includes the column-heading row as well as every staff row.


## v9.3.9 persistent restored staff and delete users

- Fixed Hannah/Charl/Leoni/Erin being re-archived after being restored.
- The initial seed now sets archived status only when a rota profile is first
  created. After that, archive/restore is manager-controlled and persists
  through page changes and server restarts.
- Managers now use `Delete user` rather than Disable for staff accounts.
- Admin can delete non-admin user accounts too.
- Deleting a login preserves the rota profile, shifts, diary history and rota
  history by clearing the login references before deleting the account.


## v9.3.9 roster persistence and navigation cleanup

- Restored staff remain active across navigation and server restarts until explicitly archived.
- Managers use Delete user for staff; Admin can delete staff or manager accounts.
- Removed the Email shortcut beside the logged-in username.
- Removed email status from the main Users list; Admin email management remains inside Edit.
- More and Management menus are mutually exclusive: opening one closes the other.


## v9.4.1 single username source

- Removed `Charl` as a separate seeded/display rota name; the account is `Charlotte`.
- Linked rota profiles display the linked `AppUser.username` everywhere.
- The old `staff_profile.display_name` database column remains only for schema
  compatibility and unlinked legacy records; linked records are automatically
  kept identical to username.
- Removed independent `Edit name` from the rota. Names are changed only through
  Management → Users and immediately flow through to the rota.


## v9.4.2 archive persistence and published edit cleanup

- Archived staff now stay archived until explicitly restored from the Archived
  staff row.
- Adding/editing a shift no longer silently reactivates an archived person.
- Archive/restore commits force a fresh database reload before the rota renders.
- Removed `Return to draft` from an issued rota. Rota edits already save
  immediately, so issued rota editing now has a simple `Save changes` button.
- The supplied v9.4.2 database has Alara archived.


## v9.5 staff calendar, requests inbox and permissions

- Table Layout and all floor-plan write APIs are Admin-only.
- Staff Diary is now a monthly multi-select calendar.
- Every user submits day-off/shift requests only for themselves.
- Managers/Admin can place NO ONE OFF on selected dates.
- Requests go to Management -> Requests for approval/decline.
- Multi-day submissions are grouped and count as one open request.
- The Management menu shows a live open-request badge.
- Large parties have a direct Cancel action that moves them to Archive.


## v9.5.1 diary staffing guidance and events

- Managers see the same monthly Staff Diary calendar, including who is off,
  pending requests, large parties and pub events.
- Large parties are shown automatically on their event date with party size
  and time.
- Managers can add football matches or other pub events directly to the diary.
- `NO ONE OFF` no longer blocks a request. Staff can still submit it, but the
  calendar gives a clear low-chance warning and the manager inbox highlights
  the restriction.
- Day-off requests are ordered first come, first served on every date.
- Monday-Thursday: positions 1-3 are marked `Good chance`; later requests are
  `Lower chance`.
- Friday-Sunday: positions 1-2 are marked `Good chance`; later requests are
  `Lower chance`.
- A `NO ONE OFF` date is always shown as low chance regardless of queue
  position.
- The request inbox shows the position/chance separately for every selected
  date, so a multi-day request can have different positions on different days.


## v9.5.2 calendar display and navigation cleanup

- Removed Good chance / Lower chance wording from Staff Diary.
- Day-off request order is shown as a numbered circle by the name.
- Pending circles are amber, approved circles green, rejected circles grey.
- Shift requests are blue.
- Football events, other events and large parties are purple.
- NO ONE OFF dates are red.
- Rejected requests remain visible in grey.
- Management Requests now includes the same monthly calendar above the inbox.
- Admin/Managers can view Staff Diary even without a rota profile.
- Managers can see other managers in Users, but cannot edit them.
- Removed standalone Table Map; old URL redirects to Dashboard.
- Removed Dashboard Fit whole map button and fixed the far-right wall clipping.
- Navigation spacing/dropdowns cleaned up.


## v9.5.3 navigation and diary controls

- Staff can remove their own pending day-off or requested-shift submissions.
  A multi-date request is removed as one grouped request.
- Managers can remove football/pub events from the Staff Diary.
- My Email moved out of the main navigation and into the account/username menu.
- Navigation is now grouped into `Staff` and `Bookings` dropdowns:
  - Staff: Rota, Staff Diary
  - Bookings: Table Bookings, Large Parties, Customers
- Archive moved into Management.
- The standalone Table Map is restored but is Admin-only, alongside Edit Table
  Layout.
- Management contains Requests, Users, Tables and Archive, with Admin-only map
  tools separated below.
- Managers continue to see other manager accounts on Users without permission
  to edit them.


## v9.5.4 selected-day removal and booking map centring

- Diary removal now works from the calendar itself: select the date, press
  `Remove`, then choose the item on that selected date.
- Staff can only remove their own pending day-off or shift requests.
- Admin can remove any staff diary request.
- Managers/Admin can remove calendar events and NO ONE OFF markers.
- Removed the separate My Pending Requests / Events This Month removal lists.
- Removed `Fit whole map` from the booking table-selection map.
- The booking floor-plan map is now centred within the booking screen while
  retaining automatic fitting.


## v9.5.4.1 Staff Diary startup fix

- Fixed the `month_events is not defined` error on `/staff-diary`.
- The old sidebar event list was removed in v9.5.4, so its obsolete template
  context has now been removed as well.
- Events are still removed by selecting their date and pressing `Remove`.


## v9.5.4.2 Staff Diary selected-day delete fix

- Fixed malformed removal URLs such as `/staff-diary/request/1$1remove`.
- Selecting a diary day now immediately shows removable items for that date in
  the sidebar; there is no separate Remove-button step.
- Every removable item shows an `×` marker and its own red `Delete` button.
- Staff/managers can delete only day-off or shift requests belonging to their
  own rota profile.
- Admin can delete any person's day-off or shift request.
- Managers/Admin can delete pub events and NO ONE OFF entries.
- Deletion uses the exact server-generated URL rather than constructing route
  strings in JavaScript.


## v9.5.4.3 diary delete flow

- Staff Diary delete buttons no longer ask for confirmation.
- After deleting an item, the same calendar date remains selected and its
  sidebar stays open.
- Deleting a day-off/shift diary entry deletes the underlying request record as
  well, so it is removed from the manager Requests inbox immediately.
- For a multi-date grouped request, deleting one date removes that date from
  the request; deleting the last remaining date removes the request entirely.


## v9.6 public customer portal

- Added a public, no-login customer area at `/customer`.
- Customer home has two options only:
  - View Food Menu PDF
  - View Allergen Menu
- The public allergen menu uses the same live allergen data and filters as the
  staff system, but contains no add/edit/delete controls.
- The staff allergen editor remains unchanged behind login.
- The food-menu route expects the PDF at:
  `app/static/menus/the-rocket-pub-food-menu.pdf`
- Until that PDF exists, `/customer/food-menu` shows a clean "coming soon"
  screen rather than an error page.


## v9.7 allergen preparation, mobile customer portal, rota drafts and shift switches

- Allergen items can now be marked `Can be made gluten free`, with optional
  preparation/substitution instructions.
- Such items show `Gluten free*` and the note `*Can be made gluten free when
  ordered as such`, rather than pretending the standard dish is gluten free.
- The gluten-free filter includes verified dishes that can be made gluten free.
- Added a favicon/tab icon using the Rocket logo on staff and customer pages.
- Customer pages have a tighter mobile header, single-column cards/menu results,
  two-column allergen toggles and touch-friendly controls.
- Rota Builder cell edits no longer POST/reload on every tick. Managers edit the
  week in the browser and press one `Save draft` button.
- `Issue rota` saves the current browser draft first and issues that exact state.
- Published rota editing uses the same single `Save changes` workflow.
- Added `Shift Requests` to Staff with an incoming-request badge.
- Staff and managers linked to a rota profile can request a cover or two-way
  shift switch.
- The requested person approves/declines it in their own Shift Requests inbox.
- Approval immediately updates the rota; a second manager-approval step is no
  longer required for new requests.


## v9.7.1 rota shift-change interaction

- Removed the separate `My shifts` section from the rota screen.
- On an issued rota, the logged-in staff member's own shift chips are now
  directly actionable in the main rota table.
- Desktop: hovering over your own shift reveals `Request shift change`; clicking
  the shift opens the existing cover/two-way switch request screen.
- Mobile: because touch screens do not have hover, `Request shift change` is
  shown directly beneath the time on your own shift.
- Other people's shifts remain normal non-clickable rota entries.


## v9.7.2 inline shift requests and large-booking table fallback

- Clicking your own issued shift now expands the shift-change workflow on the
  same Rota page rather than navigating away.
- The selected shift's day is highlighted in the existing rota while choosing a
  colleague.
- Select a name, optionally choose one of their shifts for a true exchange, then
  press `Confirm swap request`.
- Shifts involved in an open pending request are highlighted yellow on the live
  rota. The saved rota image remains unchanged because no assignments are
  changed until the recipient approves.
- Normal booking allocation no longer includes the `Bar` area.
- If no single table or configured connected pairing fits a large normal
  booking, the allocator builds a fallback group from physically nearby
  available tables using floor-plan positions.
- Pool Room is preferred first, then Snug / Cubby, before other areas.
- Fallback groups may be one or two seats short; those options carry an explicit
  warning to the person taking the booking.


## v9.7.2.1 rota template fix

- Fixed `/rota` crashing with `No filter named 'isoformat'`.
- The day-highlighting JavaScript now receives ISO dates using normal Jinja
  method calls instead of trying to use a non-existent `isoformat` filter.


## v9.7.3 same-day shift-swap overlay

- Clicking your own issued shift now opens a modal overlay on top of the rota.
- Only colleagues who also have a shift on that exact date are selectable.
- Selecting a colleague selects their same-day shift for a true two-way swap.
- Same-day swapping is enforced on the server as well as in the interface.
- Open-request shifts remain yellow and cannot be entered into another swap.
- The rota itself and saved rota image are unchanged until the recipient approves.


## v9.7.3.1 rota title/script placement fix

- Fixed the shift-swap JavaScript being injected inside the Jinja `title`
  block, which caused the browser tab title to contain JavaScript/code.
- The swap overlay script now sits at the bottom of the Rota content block,
  after the rota/modal markup has rendered.


## v9.7.4 any-staff shift targets and Staff badge

- Shift-change overlay now lists every staff profile, including archived staff.
- Selecting a person always offers `Take my shift`.
- If that person also has a shift on the exact same day, the overlay additionally
  offers a true same-day `Swap shifts` option.
- Cross-day two-way swaps remain blocked by the backend.
- Archived/inactive profiles are labelled `Archived` in the picker.
- The top-level `Staff` navigation now shows the same incoming shift-request count
  badge as `Shift Requests`, so a waiting request is visible without opening the menu.


## v9.7.4.1 rota archived-staff picker fix

- Fixed `/rota` crashing because `StaffProfile.rota_name` is a Python property,
  not a SQL column, and therefore cannot be used directly in `ORDER BY`.
- The swap picker now loads profiles using real database columns and then sorts
  by the displayed rota name in Python.
- Active staff remain listed first, followed by archived staff.


## v9.7.5 shift request cancellation and rota update fix

- The person who sent a pending shift request can now cancel it from
  `Staff -> Shift Requests`.
- Pending requests can also be cancelled from the `My shift swaps` section on
  the rota.
- Cancelling removes the pending request immediately, so yellow open-request
  highlighting disappears.
- Fixed approved cover/swap assignments not being visible when the recipient was
  archived. Active staff always appear on the rota; archived staff now appear
  when they actually hold a shift in that displayed week.
- Approval continues to change the underlying `RotaShift.staff_id` assignments,
  so refreshing/opening the rota shows the approved swap immediately.


## v9.8 customer root, persistent staff login and rota autosave

- `rocketpubserver.co.uk/` is now the public customer portal.
- The staff dashboard lives at `/dashboard`.
- The customer navigation includes `Staff Login`; it links to `/dashboard`.
  Logged-out users are redirected to the login screen, while signed-in users go
  straight to the dashboard.
- Staff sessions are now permanent for 30 days, so closing the browser/computer
  does not normally require another login. Explicit Log out still ends the
  session immediately.
- Rota Builder now auto-saves local changes after roughly 0.9 seconds of
  inactivity and shows `Unsaved changes`, `Saving…`, or `Saved HH:MM:SS`.
- Manual `Save draft` / `Save changes` remains available.
- Archive/unarchive staff actions wait for any pending rota autosave before
  reloading the page, preventing the draft from reverting when a staff member
  is restored or archived.
