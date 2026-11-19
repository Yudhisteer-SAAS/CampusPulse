from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from database import get_db_connection
from routes.auth import admin_required, login_required
from services.feedback import get_feedback_summary
from services.attendance import check_in_attendance, get_attendance_summary, get_event_attendance
from services.image_upload import delete_image_file, has_upload, save_uploaded_image
from services.notifications import (
    notify_administrators,
    notify_event_audience,
)
from services.waitlist import get_waitlist_for_event

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
EVENT_CATEGORIES = {'Technical', 'Cultural', 'Sports', 'Workshop', 'Seminar', 'Other'}


def _event_form_context(event, action, error=None):
    gallery = []
    if event:
        with get_db_connection() as connection:
            gallery = connection.execute(
                'SELECT id, image_path, display_order FROM event_images WHERE event_id = ? ORDER BY display_order, id',
                (event['id'],),
            ).fetchall()
    return render_template(
        'admin/event_form.html',
        event=event,
        gallery_images=gallery,
        action=action,
        error=error,
    )


def _image_files():
    poster = request.files.get('poster')
    gallery = [file for file in request.files.getlist('gallery_images') if has_upload(file)]
    if len(gallery) > 10:
        raise ValueError('You can upload up to 10 gallery images per event.')
    return poster if has_upload(poster) else None, gallery


def _save_form_images():
    poster, gallery = _image_files()
    saved = []
    try:
        poster_path = save_uploaded_image(poster) if poster else None
        if poster_path:
            saved.append(poster_path)
        gallery_paths = []
        for image in gallery:
            image_path = save_uploaded_image(image)
            saved.append(image_path)
            gallery_paths.append(image_path)
        return poster_path, gallery_paths, saved
    except (OSError, ValueError):
        for image_path in saved:
            delete_image_file(image_path)
        raise


def _event_form_errors(title, description, category, event_date, time_value, venue, seat_limit):
    if len(title.strip()) < 3:
        raise ValueError('Event title must be at least 3 characters long.')
    if len(description.strip()) < 20:
        raise ValueError('Description must be at least 20 characters long.')
    if category not in EVENT_CATEGORIES:
        raise ValueError('Please choose a valid event category.')
    if not event_date:
        raise ValueError('Event date is required.')
    try:
        date.fromisoformat(event_date)
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


@admin_bp.route('/attendance-scanner', methods=['GET', 'POST'])
@login_required
@admin_required
def attendance_scanner():
    if request.method == 'POST':
        try:
            check_in = check_in_attendance(
                request.form.get('pass_code', ''),
                session['user_id'],
            )
            flash(
                f"Attendance recorded for {check_in['student_name']} — {check_in['title']}.",
                'success',
            )
        except ValueError as exc:
            flash(str(exc), 'error')
    return render_template('admin/attendance_scanner.html')


@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    with get_db_connection() as connection:
        event_rows = connection.execute(
            '''
            SELECT e.*,
                (
                    SELECT COUNT(*) FROM registrations r
                    WHERE r.event_id = e.id AND r.status = 'confirmed'
                ) AS registered_count,
                (
                    SELECT COUNT(*) FROM waitlist w
                    WHERE w.event_id = e.id
                ) AS waitlist_count
            FROM events e
            ORDER BY e.date ASC
            '''
        ).fetchall()

        stats = {
            'total_events': connection.execute('SELECT COUNT(*) AS total FROM events').fetchone()['total'],
            'student_registrations': connection.execute('SELECT COUNT(*) AS total FROM registrations').fetchone()['total'],
            'waitlist': connection.execute('SELECT COUNT(*) AS total FROM waitlist').fetchone()['total'],
        }

    events = []
    for row in event_rows:
        event = dict(row)
        event['poster_url'] = (
            url_for('student.poster_image', event_id=event['id'])
            if event['poster_path']
            else None
        )
        events.append(event)
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
            poster_path, gallery_paths, saved_paths = _save_form_images()
        except ValueError as exc:
            flash(str(exc), 'error')
            return _event_form_context(None, 'Create')

        try:
            with get_db_connection() as connection:
                cursor = connection.execute(
                    '''
                    INSERT INTO events (title, description, category, date, time, venue, seat_limit, created_by, poster_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        poster_path,
                    ),
                )
                event_id = cursor.lastrowid
                connection.executemany(
                    'INSERT INTO event_images (event_id, image_path, display_order) VALUES (?, ?, ?)',
                    [(event_id, path, index) for index, path in enumerate(gallery_paths)],
                )
        except Exception:
            for image_path in saved_paths:
                delete_image_file(image_path)
            raise
        flash('Event created successfully.', 'success')
        return redirect(url_for('admin.dashboard'))

    return _event_form_context(None, 'Create')


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
            poster_upload, gallery_uploads = _image_files()
            removed_gallery_ids = []
            for image_id in request.form.getlist('remove_gallery_image'):
                try:
                    removed_gallery_ids.append(int(image_id))
                except ValueError as exc:
                    raise ValueError('Invalid gallery image selection.') from exc
            with get_db_connection() as connection:
                current_count = connection.execute(
                    'SELECT COUNT(*) AS total FROM event_images WHERE event_id = ?',
                    (event_id,),
                ).fetchone()['total']
                removable_count = 0
                if removed_gallery_ids:
                    placeholders = ','.join('?' for _ in removed_gallery_ids)
                    removable_count = connection.execute(
                        f'SELECT COUNT(*) AS total FROM event_images WHERE event_id = ? AND id IN ({placeholders})',
                        (event_id, *removed_gallery_ids),
                    ).fetchone()['total']
                if current_count - removable_count + len(gallery_uploads) > 10:
                    raise ValueError('An event can have up to 10 gallery images.')
            poster_path, gallery_paths, saved_paths = _save_form_images()
        except ValueError as exc:
            flash(str(exc), 'error')
            return _event_form_context(event, 'Edit')

        old_image_paths = []
        try:
            with get_db_connection() as connection:
                changes = [
                    (field, event[field], payload[field])
                    for field in ('title', 'category', 'date', 'time', 'venue', 'description', 'seat_limit')
                    if event[field] != payload[field]
                ]
                removed_poster = request.form.get('remove_poster') == '1'
                new_poster_path = poster_path or (
                    None if removed_poster else event['poster_path']
                )
                if new_poster_path != event['poster_path'] and event['poster_path']:
                    old_image_paths.append(event['poster_path'])

                connection.execute(
                    '''
                    UPDATE events
                    SET title = ?, description = ?, category = ?, date = ?, time = ?,
                        venue = ?, seat_limit = ?, poster_path = ?
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
                        new_poster_path,
                        event_id,
                    ),
                )

                if changes:
                    change_summary = '; '.join(
                        f"{field.replace('_', ' ').title()}: {old_value} → {new_value}"
                        for field, old_value, new_value in changes
                    )
                    notify_event_audience(
                        connection,
                        event_id,
                        'event_updated',
                        'Event details updated',
                        f"{event['title']} has important updates: {change_summary}.",
                    )
                    notify_administrators(
                        connection,
                        event_id,
                        'event_updated',
                        'Event details updated',
                        f"{event['title']} was updated by an administrator. {change_summary}.",
                    )

                removed_images = []
                if removed_gallery_ids:
                    placeholders = ','.join('?' for _ in removed_gallery_ids)
                    removed_images = connection.execute(
                        f'SELECT id, image_path FROM event_images WHERE event_id = ? AND id IN ({placeholders})',
                        (event_id, *removed_gallery_ids),
                    ).fetchall()
                    connection.execute(
                        f'DELETE FROM event_images WHERE event_id = ? AND id IN ({placeholders})',
                        (event_id, *removed_gallery_ids),
                    )
                    old_image_paths.extend(image['image_path'] for image in removed_images)

                max_order = connection.execute(
                    'SELECT COALESCE(MAX(display_order), -1) AS max_order FROM event_images WHERE event_id = ?',
                    (event_id,),
                ).fetchone()['max_order']
                connection.executemany(
                    'INSERT INTO event_images (event_id, image_path, display_order) VALUES (?, ?, ?)',
                    [
                        (event_id, path, max_order + index + 1)
                        for index, path in enumerate(gallery_paths)
                    ],
                )
        except Exception:
            for image_path in saved_paths:
                delete_image_file(image_path)
            raise
        for image_path in old_image_paths:
            delete_image_file(image_path)
        flash('Event updated successfully.', 'success')
        return redirect(url_for('admin.event_detail', event_id=event_id))

    return _event_form_context(event, 'Edit')


@admin_bp.route('/images/<int:image_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_event_image(image_id):
    with get_db_connection() as connection:
        image = connection.execute(
            'SELECT id, event_id, image_path FROM event_images WHERE id = ?',
            (image_id,),
        ).fetchone()
        if not image:
            abort(404)
        connection.execute('DELETE FROM event_images WHERE id = ?', (image_id,))
    delete_image_file(image['image_path'])
    flash('Gallery image deleted.', 'success')
    return redirect(url_for('admin.edit_event', event_id=image['event_id']))


@admin_bp.route('/events/<int:event_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_event(event_id):
    image_paths = []
    with get_db_connection() as connection:
        event = connection.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
        if not event:
            abort(404)

        image_paths = [
            row['image_path']
            for row in connection.execute(
                'SELECT image_path FROM event_images WHERE event_id = ?',
                (event_id,),
            ).fetchall()
        ]
        if event['poster_path']:
            image_paths.append(event['poster_path'])
        notify_event_audience(
            connection,
            event_id,
            'event_cancelled',
            'Event canceled',
            f"{event['title']} has been canceled by an administrator.",
        )
        notify_administrators(
            connection,
            event_id,
            'event_cancelled',
            'Event canceled',
            f"{event['title']} was canceled and removed by an administrator.",
        )
        connection.execute('DELETE FROM feedback WHERE event_id = ?', (event_id,))
        connection.execute('DELETE FROM registrations WHERE event_id = ?', (event_id,))
        connection.execute('DELETE FROM waitlist WHERE event_id = ?', (event_id,))
        connection.execute('DELETE FROM event_images WHERE event_id = ?', (event_id,))
        connection.execute('DELETE FROM events WHERE id = ?', (event_id,))

    for image_path in image_paths:
        delete_image_file(image_path)
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
            SELECT r.user_id, u.name, u.email, r.registered_at, a.checked_in_at
            FROM registrations r
            JOIN users u ON u.id = r.user_id
            LEFT JOIN attendance a ON a.registration_id = r.id
            WHERE r.event_id = ?
            ORDER BY r.registered_at ASC
            ''',
            (event_id,),
        ).fetchall()

        waitlist = get_waitlist_for_event(event_id)
        feedback_summary = get_feedback_summary(event_id)
        attendance = get_event_attendance(event_id)
        attendance_summary = get_attendance_summary(event_id)
        gallery_images = connection.execute(
            'SELECT id FROM event_images WHERE event_id = ? ORDER BY display_order, id',
            (event_id,),
        ).fetchall()
        event = dict(event)
        event['poster_url'] = (
            url_for('student.poster_image', event_id=event_id)
            if event['poster_path']
            else None
        )

    return render_template(
        'admin/event_detail.html',
        event=event,
        registered_students=registered_students,
        waitlist=waitlist,
        feedback_summary=feedback_summary,
        attendance=attendance,
        attendance_summary=attendance_summary,
        gallery_images=gallery_images,
    )
