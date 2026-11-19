from database import get_db_connection


def create_notification(connection, recipient_id, event_id, notification_type, title, message):
    connection.execute(
        '''
        INSERT INTO notifications (recipient_id, event_id, type, title, message)
        VALUES (?, ?, ?, ?, ?)
        ''',
        (recipient_id, event_id, notification_type, title, message),
    )


def notify_administrators(connection, event_id, notification_type, title, message):
    admins = connection.execute(
        "SELECT id FROM users WHERE role = 'admin'"
    ).fetchall()
    for admin in admins:
        create_notification(
            connection,
            admin['id'],
            event_id,
            notification_type,
            title,
            message,
        )


def notify_event_audience(connection, event_id, notification_type, title, message):
    recipients = connection.execute(
        '''
        SELECT user_id FROM registrations WHERE event_id = ?
        UNION
        SELECT user_id FROM waitlist WHERE event_id = ?
        ''',
        (event_id, event_id),
    ).fetchall()
    for recipient in recipients:
        create_notification(
            connection,
            recipient['user_id'],
            event_id,
            notification_type,
            title,
            message,
        )


def get_recent_notifications(user_id, limit=5):
    with get_db_connection() as connection:
        return connection.execute(
            '''
            SELECT n.id, n.event_id, n.type, n.title, n.message, n.created_at,
                   n.read_at, e.title AS event_title, e.id AS related_event_id
            FROM notifications n
            LEFT JOIN events e ON e.id = n.event_id
            WHERE n.recipient_id = ?
            ORDER BY n.created_at DESC, n.id DESC
            LIMIT ?
            ''',
            (user_id, limit),
        ).fetchall()


def get_unread_notification_count(user_id):
    with get_db_connection() as connection:
        return connection.execute(
            'SELECT COUNT(*) AS total FROM notifications WHERE recipient_id = ? AND read_at IS NULL',
            (user_id,),
        ).fetchone()['total']


def get_notifications(user_id):
    with get_db_connection() as connection:
        return connection.execute(
            '''
            SELECT n.id, n.event_id, n.type, n.title, n.message, n.created_at,
                   n.read_at, e.title AS event_title, e.id AS related_event_id
            FROM notifications n
            LEFT JOIN events e ON e.id = n.event_id
            WHERE n.recipient_id = ?
            ORDER BY n.created_at DESC, n.id DESC
            ''',
            (user_id,),
        ).fetchall()


def mark_notification_read(user_id, notification_id):
    with get_db_connection() as connection:
        cursor = connection.execute(
            '''
            UPDATE notifications SET read_at = CURRENT_TIMESTAMP
            WHERE id = ? AND recipient_id = ? AND read_at IS NULL
            ''',
            (notification_id, user_id),
        )
        return cursor.rowcount > 0


def mark_all_notifications_read(user_id):
    with get_db_connection() as connection:
        cursor = connection.execute(
            '''
            UPDATE notifications SET read_at = CURRENT_TIMESTAMP
            WHERE recipient_id = ? AND read_at IS NULL
            ''',
            (user_id,),
        )
        return cursor.rowcount


def get_notification_summary(user_id):
    return {
        'unread_count': get_unread_notification_count(user_id),
        'recent': get_recent_notifications(user_id),
    }
