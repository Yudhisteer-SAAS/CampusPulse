from datetime import date

from database import get_db_connection
from services.notifications import create_notification, notify_administrators


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
            cursor = connection.execute(
                'INSERT INTO registrations (user_id, event_id, status, registered_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)',
                (user_id, event_id, 'confirmed'),
            )
            student = connection.execute(
                'SELECT name FROM users WHERE id = ?',
                (user_id,),
            ).fetchone()
            message = f"{student['name']} registered for {event['title']} on {event['date']} at {event['time']}."
            create_notification(
                connection,
                user_id,
                event_id,
                'registration_confirmed',
                'Registration confirmed',
                f"Your registration for {event['title']} is confirmed for {event['date']} at {event['time']}.",
            )
            notify_administrators(
                connection,
                event_id,
                'student_registered',
                'New event registration',
                message,
            )
            return {
                'success': True,
                'message': 'Registration confirmed successfully.',
                'registration_id': cursor.lastrowid,
            }

        connection.execute(
            'INSERT INTO waitlist (user_id, event_id, joined_at, status) VALUES (?, ?, CURRENT_TIMESTAMP, ?)',
            (user_id, event_id, 'waiting'),
        )
        student = connection.execute(
            'SELECT name FROM users WHERE id = ?',
            (user_id,),
        ).fetchone()
        create_notification(
            connection,
            user_id,
            event_id,
            'waitlist_joined',
            'Added to waitlist',
            f"You have joined the waitlist for {event['title']} on {event['date']} at {event['time']}.",
        )
        notify_administrators(
            connection,
            event_id,
            'student_waitlisted',
            'Student joined the waitlist',
            f"{student['name']} joined the waitlist for {event['title']} on {event['date']} at {event['time']}.",
        )
        return {'success': True, 'message': 'The event is full. You were added to the waitlist.'}


def cancel_registration(user_id, event_id):
    with get_db_connection() as connection:
        existing = connection.execute(
            '''
            SELECT r.*, u.name, e.title, e.date, e.time
            FROM registrations r
            JOIN users u ON u.id = r.user_id
            JOIN events e ON e.id = r.event_id
            WHERE r.user_id = ? AND r.event_id = ?
            ''',
            (user_id, event_id),
        ).fetchone()
        if not existing:
            waitlist_entry = connection.execute(
                '''
                SELECT w.id, w.user_id, u.name, e.title, e.date, e.time
                FROM waitlist w
                JOIN users u ON u.id = w.user_id
                JOIN events e ON e.id = w.event_id
                WHERE w.user_id = ? AND w.event_id = ?
                ''',
                (user_id, event_id),
            ).fetchone()
            if not waitlist_entry:
                raise ValueError('No active registration was found to cancel.')
            connection.execute('DELETE FROM waitlist WHERE id = ?', (waitlist_entry['id'],))
            create_notification(
                connection,
                user_id,
                event_id,
                'waitlist_left',
                'Waitlist spot released',
                f"You left the waitlist for {waitlist_entry['title']}.",
            )
            notify_administrators(
                connection,
                event_id,
                'waitlist_cancelled',
                'Student left the waitlist',
                f"{waitlist_entry['name']} left the waitlist for {waitlist_entry['title']} on {waitlist_entry['date']} at {waitlist_entry['time']}.",
            )
            return {'success': True, 'message': 'You have left the waitlist.'}

        connection.execute(
            'DELETE FROM registrations WHERE user_id = ? AND event_id = ?',
            (user_id, event_id),
        )
        create_notification(
            connection,
            user_id,
            event_id,
            'registration_cancelled',
            'Registration canceled',
            f"Your registration for {existing['title']} has been canceled.",
        )
        notify_administrators(
            connection,
            event_id,
            'student_cancelled',
            'Registration canceled',
            f"{existing['name']} canceled their registration for {existing['title']} on {existing['date']} at {existing['time']}.",
        )

        waiting_user = connection.execute(
            'SELECT * FROM waitlist WHERE event_id = ? ORDER BY joined_at ASC LIMIT 1',
            (event_id,),
        ).fetchone()

        if waiting_user:
            promoted = connection.execute(
                'SELECT name FROM users WHERE id = ?',
                (waiting_user['user_id'],),
            ).fetchone()
            connection.execute(
                'INSERT INTO registrations (user_id, event_id, status, registered_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)',
                (waiting_user['user_id'], event_id, 'confirmed'),
            )
            connection.execute(
                'DELETE FROM waitlist WHERE id = ?',
                (waiting_user['id'],),
            )
            create_notification(
                connection,
                waiting_user['user_id'],
                event_id,
                'waitlist_promoted',
                'You have a confirmed seat',
                f"A seat opened for {existing['title']}. Your waitlist position was promoted and your registration is confirmed for {existing['date']} at {existing['time']}.",
            )
            notify_administrators(
                connection,
                event_id,
                'waitlist_promoted',
                'Waitlisted student promoted',
                f"{promoted['name']} was promoted from the waitlist for {existing['title']}.",
            )
            return {'success': True, 'message': 'Registration canceled successfully. The next waitlisted student was promoted.'}

        return {'success': True, 'message': 'Registration canceled successfully.'}
