from datetime import date

from database import get_db_connection


def get_feedback_summary(event_id):
    with get_db_connection() as connection:
        total_count = connection.execute(
            'SELECT COUNT(*) AS total FROM feedback WHERE event_id = ?',
            (event_id,),
        ).fetchone()['total']
        average_rating = connection.execute(
            'SELECT AVG(rating) AS avg FROM feedback WHERE event_id = ?',
            (event_id,),
        ).fetchone()['avg']
        return {
            'total_count': total_count,
            'average_rating': round(average_rating, 2) if average_rating is not None else 0,
            'feedback': connection.execute(
                '''
                SELECT f.*, u.name
                FROM feedback f
                JOIN users u ON u.id = f.user_id
                WHERE f.event_id = ?
                ORDER BY f.created_at DESC
                ''',
                (event_id,),
            ).fetchall(),
        }


def submit_feedback(user_id, event_id, rating, comment):
    cleaned_rating = int(rating)
    cleaned_comment = (comment or '').strip()

    if not 1 <= cleaned_rating <= 5:
        raise ValueError('Rating must be between 1 and 5.')
    if len(cleaned_comment) < 10:
        raise ValueError('Feedback comment must be at least 10 characters long.')
    if len(cleaned_comment) > 500:
        raise ValueError('Feedback comment is too long.')

    with get_db_connection() as connection:
        event = connection.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
        if not event:
            raise ValueError('The event was not found.')
        if event['date'] >= date.today().isoformat():
            raise ValueError('Feedback can only be submitted after the event date has passed.')

        existing_registration = connection.execute(
            'SELECT 1 FROM registrations WHERE user_id = ? AND event_id = ?',
            (user_id, event_id),
        ).fetchone()
        if not existing_registration:
            raise ValueError('You must have registered for this event before leaving feedback.')

        existing_feedback = connection.execute(
            'SELECT 1 FROM feedback WHERE user_id = ? AND event_id = ?',
            (user_id, event_id),
        ).fetchone()
        if existing_feedback:
            raise ValueError('You have already submitted feedback for this event.')

        connection.execute(
            'INSERT INTO feedback (user_id, event_id, rating, comment, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)',
            (user_id, event_id, cleaned_rating, cleaned_comment),
        )

        return {'success': True, 'message': 'Feedback submitted successfully.'}
