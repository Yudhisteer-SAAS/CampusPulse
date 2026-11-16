from database import get_db_connection


def get_waitlist_for_event(event_id):
    with get_db_connection() as connection:
        return connection.execute(
            '''
            SELECT w.id, w.user_id, u.name, u.email, w.joined_at
            FROM waitlist w
            JOIN users u ON u.id = w.user_id
            WHERE w.event_id = ?
            ORDER BY w.joined_at ASC
            ''',
            (event_id,),
        ).fetchall()


def get_waitlist_position(event_id, user_id):
    with get_db_connection() as connection:
        waitlist = connection.execute(
            '''
            SELECT user_id, joined_at
            FROM waitlist
            WHERE event_id = ?
            ORDER BY joined_at ASC
            ''',
            (event_id,),
        ).fetchall()

        for position, row in enumerate(waitlist, start=1):
            if row['user_id'] == user_id:
                return position
        return None


def promote_next_waitlist_member(event_id):
    with get_db_connection() as connection:
        next_user = connection.execute(
            '''
            SELECT * FROM waitlist
            WHERE event_id = ?
            ORDER BY joined_at ASC LIMIT 1
            ''',
            (event_id,),
        ).fetchone()

        if not next_user:
            return None

        connection.execute(
            'INSERT INTO registrations (user_id, event_id, status, registered_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)',
            (next_user['user_id'], event_id, 'confirmed'),
        )
        connection.execute('DELETE FROM waitlist WHERE id = ?', (next_user['id'],))
        return next_user['user_id']
