from datetime import date

from pathlib import Path

from flask import Blueprint, abort, flash, redirect, render_template, request, send_from_directory, session, url_for

from config import EVENT_UPLOAD_DIR
from database import get_db_connection
from routes.auth import login_required, student_required
from services.feedback import get_feedback_summary, submit_feedback
from services.registration import cancel_registration, get_event_registration_summary, register_student_for_event
from services.recommendations import EVENT_CATEGORIES, get_recommendations, get_student_interests, save_student_interests
from services.attendance import create_attendance_pass, create_qr_data_uri
from services.waitlist import get_waitlist_position

student_bp = Blueprint('student', __name__)


def _event_categories():
    with get_db_connection() as connection:
        categories = connection.execute(
            'SELECT DISTINCT category FROM events ORDER BY category ASC'
        ).fetchall()
        return [row['category'] for row in categories]


def _event_cards(category=None, limit=None):
    query = 'SELECT * FROM events WHERE date >= ?'
    params = [date.today().isoformat()]
    if category and category != 'all':
        query += ' AND category = ?'
        params.append(category)
    query += ' ORDER BY date ASC'
    if limit:
        query += ' LIMIT ?'
        params.append(limit)

    with get_db_connection() as connection:
        rows = connection.execute(query, params).fetchall()

    results = []
    for row in rows:
        summary = get_event_registration_summary(row['id'])
        event = {**dict(row), **summary}
        event['poster_url'] = (
            url_for('student.poster_image', event_id=event['id'])
            if event.get('poster_path')
            else None
        )
        results.append(event)
    return results


@student_bp.route('/')
def home():
    events = _event_cards(limit=6)
    featured = events[:3]
    categories = _event_categories()
    return render_template('student/index.html', events=events, featured=featured, categories=categories)


@student_bp.route('/dashboard')
@login_required
@student_required
def dashboard():
    user_id = session.get('user_id')
    with get_db_connection() as connection:
        user = connection.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        upcoming = _event_cards(limit=5)
        categories = _event_categories()
        registrations = connection.execute(
            '''
            SELECT e.*, r.status, r.registered_at
            FROM registrations r
            JOIN events e ON e.id = r.event_id
            WHERE r.user_id = ?
            ORDER BY e.date ASC
            ''',
            (user_id,),
        ).fetchall()
        recommendations = get_recommendations(user_id)
        recommendations = [
            {
                **event,
                'poster_url': (
                    url_for('student.poster_image', event_id=event['id'])
                    if event.get('poster_path')
                    else None
                ),
            }
            for event in map(dict, recommendations)
        ]
        waitlisted = connection.execute(
            '''
            SELECT e.*, w.joined_at
            FROM waitlist w
            JOIN events e ON e.id = w.event_id
            WHERE w.user_id = ?
            ORDER BY e.date ASC
            ''',
            (user_id,),
        ).fetchall()

    return render_template(
        'student/dashboard.html',
        user=user,
        upcoming=upcoming,
        categories=categories,
        registrations=registrations,
        waitlisted=waitlisted,
        recommendations=recommendations,
    )


@student_bp.route('/events')
@login_required
@student_required
def events():
    category = request.args.get('category', 'all')
    event_rows = _event_cards(category=category)
    categories = _event_categories()
    return render_template('student/events.html', events=event_rows, categories=categories, selected_category=category)


@student_bp.route('/events/<int:event_id>')
@login_required
@student_required
def event_detail(event_id):
    with get_db_connection() as connection:
        event = connection.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
        if not event:
            abort(404)

        registration = connection.execute(
            'SELECT * FROM registrations WHERE user_id = ? AND event_id = ?',
            (session['user_id'], event_id),
        ).fetchone()
        waitlist_entry = connection.execute(
            'SELECT * FROM waitlist WHERE user_id = ? AND event_id = ?',
            (session['user_id'], event_id),
        ).fetchone()
        gallery_images = connection.execute(
            'SELECT id FROM event_images WHERE event_id = ? ORDER BY display_order, id',
            (event_id,),
        ).fetchall()

    summary = get_event_registration_summary(event_id)
    feedback_summary = get_feedback_summary(event_id)
    waitlist_position = get_waitlist_position(event_id, session['user_id']) if waitlist_entry else None
    new_attendance_pass = None
    if (
        registration
        and session.get('issue_attendance_pass_for_event') == event_id
    ):
        session.pop('issue_attendance_pass_for_event')
        new_attendance_pass = create_attendance_pass(session['user_id'], registration['id'])
        if new_attendance_pass:
            new_attendance_pass['qr_image'] = create_qr_data_uri(new_attendance_pass['token'])
    event = dict(event)
    event['poster_url'] = (
        url_for('student.poster_image', event_id=event_id)
        if event['poster_path']
        else None
    )

    return render_template(
        'student/event_detail.html',
        event=event,
        summary=summary,
        feedback_summary=feedback_summary,
        registration=registration,
        waitlist_entry=waitlist_entry,
        waitlist_position=waitlist_position,
        new_attendance_pass=new_attendance_pass,
        gallery_images=gallery_images,
        today=date.today().isoformat(),
    )


@student_bp.route('/events/<int:event_id>/poster-image')
def poster_image(event_id):
    with get_db_connection() as connection:
        event = connection.execute(
            'SELECT poster_path FROM events WHERE id = ?',
            (event_id,),
        ).fetchone()
    if not event or not event['poster_path'] or Path(event['poster_path']).name != event['poster_path']:
        abort(404)
    return send_from_directory(EVENT_UPLOAD_DIR, event['poster_path'], max_age=3600)


@student_bp.route('/event-images/<int:image_id>')
def gallery_image(image_id):
    with get_db_connection() as connection:
        image = connection.execute(
            'SELECT image_path FROM event_images WHERE id = ?',
            (image_id,),
        ).fetchone()
    if not image or Path(image['image_path']).name != image['image_path']:
        abort(404)
    return send_from_directory(EVENT_UPLOAD_DIR, image['image_path'], max_age=3600)


@student_bp.route('/events/<int:event_id>/register', methods=['POST'])
@login_required
@student_required
def register_event(event_id):
    try:
        result = register_student_for_event(session['user_id'], event_id)
        if result.get('registration_id'):
            session['issue_attendance_pass_for_event'] = event_id
        flash(result['message'], 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('student.event_detail', event_id=event_id))


@student_bp.route('/events/<int:event_id>/cancel', methods=['POST'])
@login_required
@student_required
def cancel_event(event_id):
    if session.get('issue_attendance_pass_for_event') == event_id:
        session.pop('issue_attendance_pass_for_event')
    try:
        result = cancel_registration(session['user_id'], event_id)
        flash(result['message'], 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('student.my_registrations'))


@student_bp.route('/my-registrations')
@login_required
@student_required
def my_registrations():
    user_id = session['user_id']
    with get_db_connection() as connection:
        registrations = connection.execute(
            '''
            SELECT e.*, r.status, r.registered_at
            FROM registrations r
            JOIN events e ON e.id = r.event_id
            WHERE r.user_id = ?
            ORDER BY e.date ASC
            ''',
            (user_id,),
        ).fetchall()

        waitlisted = connection.execute(
            '''
            SELECT e.*, w.joined_at, w.id AS waitlist_id
            FROM waitlist w
            JOIN events e ON e.id = w.event_id
            WHERE w.user_id = ?
            ORDER BY e.date ASC
            ''',
            (user_id,),
        ).fetchall()

    for item in waitlisted:
        item['position'] = get_waitlist_position(item['id'], user_id)

    return render_template(
        'student/my_registrations.html',
        registrations=registrations,
        waitlisted=waitlisted,
        today=date.today().isoformat(),
    )


@student_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@student_required
def profile():
    user_id = session['user_id']
    if request.method == 'POST':
        try:
            save_student_interests(user_id, request.form.getlist('categories'))
            flash('Your interests have been updated.', 'success')
            return redirect(url_for('student.profile'))
        except ValueError as exc:
            flash(str(exc), 'error')

    return render_template(
        'student/profile.html',
        categories=EVENT_CATEGORIES,
        interests=get_student_interests(user_id),
    )


@student_bp.route('/my-qr-passes')
@login_required
@student_required
def my_qr_passes():
    user_id = session['user_id']
    with get_db_connection() as connection:
        registration_ids = connection.execute(
            '''
            SELECT id FROM registrations
            WHERE user_id = ? AND status = 'confirmed'
            ORDER BY registered_at DESC
            ''',
            (user_id,),
        ).fetchall()

    passes = []
    for row in registration_ids:
        attendance_pass = create_attendance_pass(user_id, row['id'])
        if attendance_pass:
            attendance_pass['qr_image'] = create_qr_data_uri(attendance_pass['token'])
            passes.append(attendance_pass)
    return render_template('student/qr_passes.html', passes=passes)


@student_bp.route('/feedback/<int:event_id>', methods=['GET', 'POST'])
@login_required
@student_required
def feedback(event_id):
    with get_db_connection() as connection:
        event = connection.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
        if not event:
            abort(404)

        registration = connection.execute(
            'SELECT * FROM registrations WHERE user_id = ? AND event_id = ?',
            (session['user_id'], event_id),
        ).fetchone()

    if not registration:
        flash('You must have a registration for the event before leaving feedback.', 'error')
        return redirect(url_for('student.my_registrations'))

    if request.method == 'POST':
        rating = request.form.get('rating')
        comment = request.form.get('comment')
        try:
            result = submit_feedback(session['user_id'], event_id, rating, comment)
            flash(result['message'], 'success')
            return redirect(url_for('student.my_registrations'))
        except ValueError as exc:
            flash(str(exc), 'error')

    return render_template('student/feedback_form.html', event=event)
