# Pub Booking System - v3

## New in this version

### Normal bookings
- Manual time entry instead of an interval dropdown
- Earliest booking: 12:15pm
- Latest Monday-Saturday: 7:30pm
- Latest Sunday: 7:00pm
- Invalid times are cleared immediately in the browser with a popup message
- Server-side time validation remains in place too
- Number of children field (under 13)
- Automatic deposit calculation for parties over 10:
  - £5 per head
  - capped at £100
- Customer-facing deposit callback warning shown before saving
- Deposit paid can be tracked and edited
- Existing bookings can now be edited
- Existing table clash detection works correctly while editing

### Large party enquiries
- Separate Large Party Enquiry workflow
- Designed as an open/editable enquiry rather than a confirmed booking
- Name + phone
- Estimated party size
- Number of children (under 13)
- Optional date/time
- Occasion
- Status
- Menu / Buffet selection
- Options 1-4
- Configurable price per head for each option
- Number being catered for can be lower than total attendance
- Automatic food estimate when a price has been configured
- Deposit estimate/tracking
- Notes / call history
- Enquiries can be repeatedly edited as details are confirmed

## Run

```bash
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Open:

http://127.0.0.1:8000

The app keeps using the existing SQLite database in:

instance/pub_booking.db
