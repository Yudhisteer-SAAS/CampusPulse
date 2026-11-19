from datetime import date

from database import get_db_connection


EVENT_CATEGORIES = ('Technical', 'Cultural', 'Sports', 'Workshop', 'Seminar', 'Other')


def get_student_interests(user_id):
    with get_db_connection() as connection:
        rows = connection.execute(
            'SELECT category FROM user_interests WHERE user_id = ? ORDER BY category',
            (user_id,),
        ).fetchall()
    return [row['category'] for row in rows]


def save_student_interests(user_id, categories):
    selected = set(categories)
    if not selected.issubset(EVENT_CATEGORIES):
        raise ValueError('Please choose only valid event categories.')

    with get_db_connection() as connection:
        connection.execute('DELETE FROM user_interests WHERE user_id = ?', (user_id,))
        connection.executemany(
            'INSERT INTO user_interests (user_id, category) VALUES (?, ?)',
            [(user_id, category) for category in EVENT_CATEGORIES if category in selected],
        )


def get_recommendations(user_id, limit=6):
    today = date.today().isoformat()
    with get_db_connection() as connection:
        interest_rows = connection.execute(
            'SELECT category FROM user_interests WHERE user_id = ?',
            (user_id,),
        ).fetchall()
        history_rows = connection.execute(
            '''
            SELECT DISTINCT e.category
            FROM registrations r
            JOIN events e ON e.id = r.event_id
            WHERE r.user_id = ? AND r.status = 'confirmed'
            ''',
            (user_id,),
        ).fetchall()
        candidates = connection.execute(
            '''
            SELECT e.*,
                e.seat_limit - (
                    SELECT COUNT(*) FROM registrations r
                    WHERE r.event_id = e.id AND r.status = 'confirmed'
                ) AS available_seats
            FROM events e
            WHERE e.date >= ?
              AND e.seat_limit > (
                    SELECT COUNT(*) FROM registrations r
                    WHERE r.event_id = e.id AND r.status = 'confirmed'
              )
              AND NOT EXISTS (
                    SELECT 1 FROM registrations r
                    WHERE r.event_id = e.id AND r.user_id = ? AND r.status = 'confirmed'
              )
            ORDER BY e.date ASC, e.time ASC, e.id ASC
            ''',
            (today, user_id),
        ).fetchall()

    interests = {row['category'] for row in interest_rows}
    history = {row['category'] for row in history_rows}
    scored = []
    for row in candidates:
        event = dict(row)
        score = (3 if event['category'] in interests else 0) + (
            2 if event['category'] in history else 0
        )
        if score:
            event['recommendation_score'] = score
            scored.append(event)

    if not scored:
        scored = [
            {**dict(row), 'recommendation_score': 0}
            for row in candidates
        ]

    scored.sort(
        key=lambda event: (
            -event['recommendation_score'],
            event['date'],
            event['time'],
            event['id'],
        )
    )
    return scored[:limit]
