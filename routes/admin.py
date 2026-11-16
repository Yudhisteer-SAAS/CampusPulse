from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from database import get_db_connection
from routes.auth import admin_required, login_required
from services.feedback import get_feedback_summary
from services.waitlist import get_waitlist_for_event

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def _event_form_errors(title, description, category, event_date, time_value, venue, seat_limit):
    if len(title.strip()) < 3:
        raise ValueError('Event title must be at least 3 characters long.')
    if len(description.strip()) < 20:
        raise ValueError('Description must be at least 20 characters long.')
    if category not in {'Technical', 'Cultural', 'Sports', 'Workshop', 'Seminar', 'Other'}:
        raise ValueError('Please choose a valid event category.')
    if not event_date:
        raise ValueError('Event date is required.')
    try:
        if event_date < date.today().isoformat():
            pass
    except ValueError:
        raise ValueError('Event date must use a valid YYYY-MM-DD format.')
    if not time_value:
        raise ValueError('Event time is required.')
    if len(venue.strip()) < 3:
        raise ValueError('Venue must be at least 3 characters long.')
    try:
        seat_limit_value = int(seat_limit)
    except (TypeError, ValueError):
        raise ValueError('Seat capacity must be a whole number.')
    if seat_limit_value < 1:
        raise ValueError('Seat capacity must be at least 1.')
    return {
        'title': title.strip(),
        'description': description.strip(),
        'category': category,
        'date': event_date,
        'time': time_value,
        'venue': venue.strip(),
        'seat_limit': seat_limit_value,
    }


@admin_bp.route('/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('user_id') and session.get('role') == 'admin':
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''

        with get_db_connection() as connection:
            user = connection.execute(
                'SELECT * FROM users WHERE email = ? AND role = ?',
                (email, 'admin'),
            ).fetchone()

        if not user:
            flash('Invalid admin account details.', 'error')
            return render_template('admin/login.html')

        from werkzeug.security import check_password_hash
        if not check_password_hash(user['password_hash'], password):
            flash('Invalid admin account details.', 'error')
            return render_template('admin/login.html')

        session.clear()
        session['user_id'] = user['id']
        session['role'] = 'admin'
        flash('Admin login successful.', 'success')
        return redirect(url_for('admin.dashboard'))

    return render_template('admin/login.html')


@admin_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('auth.login'))


@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    with get_db_connection() as connection:
        events = connection.execute(
            '''
            SELECT e.*, COUNT(r.id) AS registered_count, COUNT(w.id) AS waitlist_count
            FROM events e
            LEFT JOIN registrations r ON r.event_id = e.id AND r.status = 'confirmed'
            LEFT JOIN waitlist w ON w.event_id = e.id
            GROUP BY e.id
            ORDER BY e.date ASC
            '''
        ).fetchall()

        stats = {
            'total_events': connection.execute('SELECT COUNT(*) AS total FROM events').fetchone()['total'],
            'student_registrations': connection.execute('SELECT COUNT(*) AS total FROM registrations').fetchone()['total'],
            'waitlist': connection.execute('SELECT COUNT(*) AS total FROM waitlist').fetchone()['total'],
        }

    return render_template('admin/dashboard.html', events=events, stats=stats)


@admin_bp.route('/events/new', methods=['GET', 'POST'])
@login_required
@admin_required
def create_event():
    if request.method == 'POST':
        try:
            payload = _event_form_errors(
                request.form.get('title', ''),
                request.form.get('description', ''),
                request.form.get('category', ''),
                request.form.get('date', ''),
                request.form.get('time', ''),
                request.form.get('venue', ''),
                request.form.get('seat_limit', ''),
            )
        except ValueError as exc:
            flash(str(exc), 'error')
            return render_template('admin/event_form.html', event=None, action='Create')

        with get_db_connection() as connection:
            connection.execute(
                '''
                INSERT INTO events (title, description, category, date, time, venue, seat_limit, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    payload['title'],
                    payload['description'],
                    payload['category'],
                    payload['date'],
                    payload['time'],
                    payload['venue'],
                    payload['seat_limit'],
                    session['user_id'],
                ),
            )
        flash('Event created successfully.', 'success')
        return redirect(url_for('admin.dashboard'))

    return render_template('admin/event_form.html', event=None, action='Create')


@admin_bp.route('/events/<int:event_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_event(event_id):
    with get_db_connection() as connection:
        event = connection.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
        if not event:
            abort(404)

    if request.method == 'POST':
        try:
            payload = _event_form_errors(
                request.form.get('title', ''),
                request.form.get('description', ''),
                request.form.get('category', ''),
                request.form.get('date', ''),
                request.form.get('time', ''),
                request.form.get('venue', ''),
                request.form.get('seat_limit', ''),
            )
        except ValueError as exc:
            flash(str(exc), 'error')
            return render_template('admin/event_form.html', event=event, action='Edit')

        with get_db_connection() as connection:
            connection.execute(
                '''
                UPDATE events
                SET title = ?, description = ?, category = ?, date = ?, time = ?, venue = ?, seat_limit = ?
                WHERE id = ?
                ''',
                (
                    payload['title'],
                    payload['description'],
                    payload['category'],
                    payload['date'],
                    payload['time'],
                    payload['venue'],
                    payload['seat_limit'],
                    event_id,
                ),
            )
        flash('Event updated successfully.', 'success')
        return redirect(url_for('admin.event_detail', event_id=event_id))

    return render_template('admin/event_form.html', event=event, action='Edit')


@admin_bp.route('/events/<int:event_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_event(event_id):
    with get_db_connection() as connection:
        event = connection.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
        if not event:
            abort(404)

        connection.execute('DELETE FROM feedback WHERE event_id = ?', (event_id,))
        connection.execute('DELETE FROM registrations WHERE event_id = ?', (event_id,))
        connection.execute('DELETE FROM waitlist WHERE event_id = ?', (event_id,))
        connection.execute('DELETE FROM events WHERE id = ?', (event_id,))

    flash('Event deleted successfully.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/events/<int:event_id>')
@login_required
@admin_required
def event_detail(event_id):
    with get_db_connection() as connection:
        event = connection.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
        if not event:
            abort(404)

        registered_students = connection.execute(
            '''
            SELECT r.user_id, u.name, u.email, r.registered_at
            FROM registrations r
            JOIN users u ON u.id = r.user_id
            WHERE r.event_id = ?
            ORDER BY r.registered_at ASC
            ''',
            (event_id,),
        ).fetchall()

        waitlist = get_waitlist_for_event(event_id)
        feedback_summary = get_feedback_summary(event_id)

    return render_template(
        'admin/event_detail.html',
        event=event,
        registered_students=registered_students,
        waitlist=waitlist,
        feedback_summary=feedback_summary,
    )
