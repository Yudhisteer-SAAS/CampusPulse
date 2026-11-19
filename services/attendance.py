import base64
import hashlib
import secrets

import qrcode
from qrcode.image.svg import SvgPathImage

from database import get_db_connection


def _token_digest(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def create_attendance_pass(user_id, registration_id):
    token = secrets.token_urlsafe(32)
    token_hash = _token_digest(token)
    with get_db_connection() as connection:
        connection.execute('BEGIN IMMEDIATE')
        registration = connection.execute(
            '''
            SELECT r.id, r.status, e.title, e.date, e.time, e.venue
            FROM registrations r
            JOIN events e ON e.id = r.event_id
            WHERE r.id = ? AND r.user_id = ? AND r.status = 'confirmed'
            ''',
            (registration_id, user_id),
        ).fetchone()
        if not registration:
            return None

        connection.execute(
            'INSERT INTO attendance_passes (registration_id, token_hash) VALUES (?, ?)',
            (registration_id, token_hash),
        )
        attendance = connection.execute(
            'SELECT checked_in_at FROM attendance WHERE registration_id = ?',
            (registration_id,),
        ).fetchone()
    return {**dict(registration), 'token': token, 'attendance': attendance}


def create_qr_data_uri(token):
    qr_code = qrcode.QRCode(box_size=8, border=2)
    qr_code.add_data(token)
    qr_code.make(fit=True)
    svg = qr_code.make_image(image_factory=SvgPathImage).to_string()
    if isinstance(svg, str):
        svg = svg.encode('utf-8')
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg).decode('ascii')


def check_in_attendance(token, admin_user_id):
    token = (token or '').strip()
    if not token or len(token) > 128:
        raise ValueError('Enter a valid attendance pass code.')

    with get_db_connection() as connection:
        connection.execute('BEGIN IMMEDIATE')
        registration = connection.execute(
            '''
            SELECT r.id AS registration_id, r.status, e.id AS event_id, e.title,
                   e.date, e.time, e.venue, u.name AS student_name
            FROM registrations r
            JOIN events e ON e.id = r.event_id
            JOIN users u ON u.id = r.user_id
            JOIN attendance_passes p ON p.registration_id = r.id
            WHERE p.token_hash = ? AND r.status = 'confirmed'
            ''',
            (_token_digest(token),),
        ).fetchone()
        if not registration:
            raise ValueError('This attendance pass is invalid or no longer active.')

        already_checked_in = connection.execute(
            'SELECT 1 FROM attendance WHERE registration_id = ?',
            (registration['registration_id'],),
        ).fetchone()
        if already_checked_in:
            raise ValueError('Attendance has already been recorded for this pass.')

        connection.execute(
            '''
            INSERT INTO attendance (registration_id, checked_in_by)
            VALUES (?, ?)
            ''',
            (registration['registration_id'], admin_user_id),
        )
    return dict(registration)


def get_event_attendance(event_id):
    with get_db_connection() as connection:
        return connection.execute(
            '''
            SELECT r.id AS registration_id, u.name, u.email, r.registered_at,
                   a.checked_in_at
            FROM registrations r
            JOIN users u ON u.id = r.user_id
            LEFT JOIN attendance a ON a.registration_id = r.id
            WHERE r.event_id = ? AND r.status = 'confirmed'
            ORDER BY r.registered_at ASC
            ''',
            (event_id,),
        ).fetchall()


def get_attendance_summary(event_id):
    with get_db_connection() as connection:
        totals = connection.execute(
            '''
            SELECT COUNT(r.id) AS registered,
                   COUNT(a.id) AS present
            FROM registrations r
            LEFT JOIN attendance a ON a.registration_id = r.id
            WHERE r.event_id = ? AND r.status = 'confirmed'
            ''',
            (event_id,),
        ).fetchone()
    return {
        'registered': totals['registered'],
        'present': totals['present'],
        'absent': totals['registered'] - totals['present'],
    }
