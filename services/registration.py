from datetime import date

from database import get_db_connection


def get_event_registration_summary(event_id):
    with get_db_connection() as connection:
        event = connection.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
        if not event:
            return None

        confirmed_count = connection.execute(
            'SELECT COUNT(*) AS total FROM registrations WHERE event_id = ? AND status = ?',
            (event_id, 'confirmed'),
        ).fetchone()['total']
        waitlist_count = connection.execute(
            'SELECT COUNT(*) AS total FROM waitlist WHERE event_id = ?',
            (event_id,),
        ).fetchone()['total']

        return {
            'event': dict(event),
            'confirmed_count': confirmed_count,
            'available_seats': max(event['seat_limit'] - confirmed_count, 0),
            'waitlist_count': waitlist_count,
        }


def register_student_for_event(user_id, event_id):
    today = date.today().isoformat()

    with get_db_connection() as connection:
        event = connection.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
        if not event:
            raise ValueError('The selected event was not found.')
        if event['date'] < today:
            raise ValueError('Registration is closed for past events.')

        already_registered = connection.execute(
            'SELECT 1 FROM registrations WHERE user_id = ? AND event_id = ?',
            (user_id, event_id),
        ).fetchone()
        already_waitlisted = connection.execute(
            'SELECT 1 FROM waitlist WHERE user_id = ? AND event_id = ?',
            (user_id, event_id),
        ).fetchone()
        if already_registered or already_waitlisted:
            raise ValueError('You are already registered or waitlisted for this event.')

        confirmed_count = connection.execute(
            'SELECT COUNT(*) AS total FROM registrations WHERE event_id = ? AND status = ?',
            (event_id, 'confirmed'),
        ).fetchone()['total']

        if confirmed_count < event['seat_limit']:
            connection.execute(
                'INSERT INTO registrations (user_id, event_id, status, registered_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)',
                (user_id, event_id, 'confirmed'),
            )
            return {'success': True, 'message': 'Registration confirmed successfully.'}

        connection.execute(
            'INSERT INTO waitlist (user_id, event_id, joined_at, status) VALUES (?, ?, CURRENT_TIMESTAMP, ?)',
            (user_id, event_id, 'waiting'),
        )
        return {'success': True, 'message': 'The event is full. You were added to the waitlist.'}


def cancel_registration(user_id, event_id):
    with get_db_connection() as connection:
        existing = connection.execute(
            'SELECT * FROM registrations WHERE user_id = ? AND event_id = ?',
            (user_id, event_id),
        ).fetchone()
        if not existing:
            raise ValueError('No active registration was found to cancel.')

        connection.execute(
            'DELETE FROM registrations WHERE user_id = ? AND event_id = ?',
            (user_id, event_id),
        )

        waiting_user = connection.execute(
            'SELECT * FROM waitlist WHERE event_id = ? ORDER BY joined_at ASC LIMIT 1',
            (event_id,),
        ).fetchone()

        if waiting_user:
            connection.execute(
                'INSERT INTO registrations (user_id, event_id, status, registered_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)',
                (waiting_user['user_id'], event_id, 'confirmed'),
            )
            connection.execute(
                'DELETE FROM waitlist WHERE id = ?',
                (waiting_user['id'],),
            )
            return {'success': True, 'message': 'Registration canceled successfully. The next waitlisted student was promoted.'}

        return {'success': True, 'message': 'Registration canceled successfully.'}
