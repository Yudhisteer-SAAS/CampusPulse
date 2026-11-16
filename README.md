# CampusPulse

CampusPulse is a Flask-based campus event platform for students and administrators. It supports secure authentication, role-based access control, event registration with waitlist handling, feedback submission, and a polished responsive interface for browsing campus events.

## Features

- Student signup and login
- Admin login and protected admin workflows
- Event catalog with category filtering
- Event details, registration, and cancellation
- Waitlist logic with automatic promotion when a confirmed spot opens
- Post-event feedback collection with ratings and averages
- SQLite-backed data model with seeded sample data
- CSRF protection and response security headers

## Technology Stack

- Python 3
- Flask
- SQLite
- Jinja2 templates
- Werkzeug password hashing

## Project Structure

- `app.py` — Flask app factory and global security configuration
- `config.py` — app configuration settings
- `database.py` — SQLite schema creation and seed data
- `seed_database.py` — database initialization helper
- `routes/` — auth, student, and admin route blueprints
- `services/` — registration, waitlist, and feedback business logic
- `templates/` — Jinja templates for UI pages
- `static/` — CSS and JavaScript assets
- `tests/` — unit tests for app workflows and security checks

## Quick Start

1. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Initialize the database and seed sample users/events:

```bash
python seed_database.py
```

4. Run the app:

```bash
python app.py
```

Then open:

- http://127.0.0.1:5000/

## Default Accounts

- Admin: `admin@campuspulse.edu` / `Admin@123`
- Student: `maya@campuspulse.edu` / `Student@123`

## Testing

Run the test suite with:

```bash
python -m unittest discover -s tests -v
```

## Notes

- The app uses SQLite and stores data in a file managed by `config.py`.
- The production-style workflow includes server-side validation, access control, and waitlist enforcement rather than relying solely on client-side behavior.
- Security headers and CSRF validation are enabled in the app factory for POST/PUT/PATCH/DELETE requests.
