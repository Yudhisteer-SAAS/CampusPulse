# CampusPulse

CampusPulse is a responsive Flask application for managing campus events. Students can discover and register for events, join waitlists, share feedback, personalize recommendations, and carry QR attendance passes. Administrators can manage events and verify attendance.

## Features

- Student and administrator authentication with role-based access
- Event creation, editing, browsing, category filtering, registration, and cancellation
- Waitlists with automatic promotion when a confirmed registration is canceled
- Post-event ratings and feedback
- Student-selected event interests and rule-based recommendations
- Unique QR passes for confirmed registrations
- Camera-based and manual attendance check-in for administrators
- Per-event attendance lists with present and absent counts
- Event posters and galleries with validated image uploads
- In-app notifications for registrations, waitlists, and event changes
- SQLite persistence, CSRF validation, password hashing, and security headers
- Responsive student and admin interfaces
- CampusPulse branding based on the supplied `Logo.png`

## Technology

- Python 3.10+
- Flask 3.0
- SQLite
- Jinja templates, CSS, and vanilla JavaScript
- `qrcode` for SVG pass generation
- `qr-scanner` 1.4.2 (MIT) for in-browser camera scanning; bundled locally in `static/vendor/`

## Setup

### Linux and macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python seed_database.py
python app.py
```

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python seed_database.py
python app.py
```

Open <http://localhost:5000/> (or <http://127.0.0.1:5000/> for normal browsing).

The app stores its SQLite database in `instance/campuspulse.db` by default. To use a different path, set `CAMPUSPULSE_DB_PATH`. Configure `CAMPUSPULSE_SECRET_KEY` to a long, random value before deployment; the built-in development key is not suitable for production.

## Database migration

On startup, CampusPulse runs additive, idempotent schema initialization. Existing Phase 1 users, events, registrations, waitlists, and feedback are preserved. Phase 2 adds student interests, hashed QR pass tokens, attendance, event-image metadata, and notifications; it does not drop or recreate the database.

For production, back up `instance/campuspulse.db` before upgrading:

```bash
python -c "import shutil; shutil.copy2('instance/campuspulse.db', 'instance/campuspulse.db.backup')"
python app.py
```

On Windows, the same Python backup command works from PowerShell.

## Demo accounts

- Admin: `admin@campuspulse.edu` / `Admin@123`
- Student: `aarav@campuspulse.edu` / `Student@123`
- Other seeded students: `ananya@campuspulse.edu`, `priya@campuspulse.edu`, `rohan@campuspulse.edu`, and `kavya@campuspulse.edu` (all use `Student@123`)

Change these credentials and the development secret before making a deployment accessible to others.

## Recommendations

After signing in, use **My Interests** in the navigation to select event categories. The dashboard ranks upcoming, available events based on selected interests and categories from prior registrations. Events already registered for, past events, and full events are excluded. When no relevant match exists, it falls back to upcoming events with available seats.

## QR passes and attendance

1. Sign in as a student and register for an event.
2. Open **My QR Passes** to view and download an SVG pass for each confirmed registration.
3. Sign in as an administrator and open **Attendance Scanner**.
4. Allow camera access and scan the pass, or copy its manual code from **My QR Passes** and paste it into the scanner form.
5. View each event's attendance list and present/absent totals from its admin management page.

Camera scanning requires a secure browser context: open the app on `localhost` during development or serve it over HTTPS. Grant camera permission when prompted. If camera access is unavailable or denied, the manual pass-code option remains available. A pass token is random and its hash is stored in SQLite; check-in is restricted to administrators and each registration can only be checked in once.

## Event images and notifications

Administrators can add a poster and up to 10 gallery images when creating or editing an event. JPEG, PNG, and WebP uploads are validated and re-encoded as WebP; individual images are limited to 5 MB and 6000 pixels per dimension. Image files are stored under `instance/uploads/events`, while only generated filenames and gallery metadata are stored in SQLite. Replacing or removing an image, or deleting its event, removes the associated image file.

Students receive in-app notifications for registration, waitlist, promotion, cancellation, and event updates. Administrators receive notifications for registration activity and event changes. The notification menu refreshes periodically while signed in; users can mark individual notifications or all notifications as read. The supplied root-level `Logo.png` is used to produce the smaller logo and icon assets in `static/images/`.

## Responsive layout

The interface adapts across phone, tablet, and desktop widths, including collapsible mobile navigation, responsive event cards, and usable admin data sections. Layouts have been checked at 320, 375, 390, 768, and 1280 CSS pixels. The admin scanner uses the device camera when supported and provides a manual fallback. Motion effects respect `prefers-reduced-motion`.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Project layout

- `app.py` — Flask application and security controls
- `database.py` — database access, schema initialization, and seed data
- `routes/` — student, admin, and authentication routes
- `services/` — registration, waitlist, feedback, recommendation, and attendance logic
- `templates/` — student, admin, authentication, and error pages
- `static/` — styles, JavaScript, and the locally bundled QR scanner
- `tests/` — regression and Phase 2 workflow tests
