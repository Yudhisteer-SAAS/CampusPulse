import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from config import DATABASE_PATH


@contextmanager
def get_db_connection():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_db():
    with get_db_connection() as connection:
        connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('student', 'admin')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )

        connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                venue TEXT NOT NULL,
                seat_limit INTEGER NOT NULL CHECK(seat_limit > 0),
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(created_by) REFERENCES users(id)
            )
            '''
        )

        event_columns = {
            row['name'] for row in connection.execute('PRAGMA table_info(events)')
        }
        if 'poster_path' not in event_columns:
            connection.execute('ALTER TABLE events ADD COLUMN poster_path TEXT')

        connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'confirmed' CHECK(status IN ('confirmed')),
                registered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, event_id),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(event_id) REFERENCES events(id)
            )
            '''
        )

        connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS user_interests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                UNIQUE(user_id, category),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            '''
        )
        connection.execute(
            'CREATE INDEX IF NOT EXISTS idx_user_interests_user_id '
            'ON user_interests(user_id)'
        )

        connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS attendance_passes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                registration_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                issued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(registration_id) REFERENCES registrations(id) ON DELETE CASCADE
            )
            '''
        )
        connection.execute(
            'CREATE INDEX IF NOT EXISTS idx_attendance_passes_registration_id '
            'ON attendance_passes(registration_id)'
        )

        connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                registration_id INTEGER NOT NULL UNIQUE,
                checked_in_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                checked_in_by INTEGER NOT NULL,
                FOREIGN KEY(registration_id) REFERENCES registrations(id) ON DELETE CASCADE,
                FOREIGN KEY(checked_in_by) REFERENCES users(id)
            )
            '''
        )
        connection.execute(
            'CREATE INDEX IF NOT EXISTS idx_attendance_checked_in_by '
            'ON attendance(checked_in_by)'
        )

        connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS event_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                image_path TEXT NOT NULL UNIQUE,
                image_type TEXT NOT NULL DEFAULT 'gallery' CHECK(image_type = 'gallery'),
                display_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
            )
            '''
        )
        connection.execute(
            'CREATE INDEX IF NOT EXISTS idx_event_images_event_order '
            'ON event_images(event_id, display_order, id)'
        )

        connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_id INTEGER NOT NULL,
                event_id INTEGER,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                read_at TEXT,
                FOREIGN KEY(recipient_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE SET NULL
            )
            '''
        )
        connection.execute(
            'CREATE INDEX IF NOT EXISTS idx_notifications_recipient_read_created '
            'ON notifications(recipient_id, read_at, created_at)'
        )

        connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS waitlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_id INTEGER NOT NULL,
                joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'waiting' CHECK(status IN ('waiting')),
                UNIQUE(user_id, event_id),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(event_id) REFERENCES events(id)
            )
            '''
        )

        connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_id INTEGER NOT NULL,
                rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
                comment TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, event_id),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(event_id) REFERENCES events(id)
            )
            '''
        )


def _seed_events(connection):
    today = date.today()
    events = [
        {
            'title': 'Campus Innovation Expo',
            'description': 'A showcase of student-built prototypes, hackathon winners, and entrepreneurial startups from across the campus.',
            'category': 'Technical',
            'date': (today + timedelta(days=4)).isoformat(),
            'time': '10:00',
            'venue': 'Innovation Hall',
            'seat_limit': 2,
            'created_by': 1,
        },
        {
            'title': 'Cultural Night 2026',
            'description': 'An evening of music, dance, and poetry that celebrates the creativity of the student community.',
            'category': 'Cultural',
            'date': (today + timedelta(days=9)).isoformat(),
            'time': '18:30',
            'venue': 'Auditorium A',
            'seat_limit': 10,
            'created_by': 1,
        },
        {
            'title': 'Intercollege Football League',
            'description': 'A competitive football event with live commentary, team spirit, and community cheering.',
            'category': 'Sports',
            'date': (today + timedelta(days=12)).isoformat(),
            'time': '16:00',
            'venue': 'Main Sports Field',
            'seat_limit': 12,
            'created_by': 1,
        },
        {
            'title': 'AI for Everyday Problems',
            'description': 'A practical workshop exploring how machine learning can enhance education, healthcare, and community planning.',
            'category': 'Workshop',
            'date': (today + timedelta(days=15)).isoformat(),
            'time': '11:00',
            'venue': 'Smart Labs Studio',
            'seat_limit': 8,
            'created_by': 1,
        },
        {
            'title': 'Startup Storytelling Seminar',
            'description': 'Hear from founders, investors, and mentors about how student ideas can become real ventures.',
            'category': 'Seminar',
            'date': (today + timedelta(days=22)).isoformat(),
            'time': '14:00',
            'venue': 'Executive Hall',
            'seat_limit': 10,
            'created_by': 1,
        },
        {
            'title': 'Campus Wellness Week Kickoff',
            'description': 'A community event featuring wellness talks, mindfulness workshops, and mental health resources.',
            'category': 'Other',
            'date': (today - timedelta(days=10)).isoformat(),
            'time': '13:00',
            'venue': 'Student Center',
            'seat_limit': 12,
            'created_by': 1,
        },
    ]

    inserted_event_ids = {}
    for event in events:
        cursor = connection.execute(
            '''
            INSERT INTO events (title, description, category, date, time, venue, seat_limit, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                event['title'],
                event['description'],
                event['category'],
                event['date'],
                event['time'],
                event['venue'],
                event['seat_limit'],
                event['created_by'],
            ),
        )
        inserted_event_ids[event['title']] = cursor.lastrowid

    return inserted_event_ids


def seed_database():
    with get_db_connection() as connection:
        if connection.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            return

        admin_password = generate_password_hash('Admin@123')
        student_password = generate_password_hash('Student@123')

        user_rows = [
            (1, 'Arjun Rao', 'admin@campuspulse.edu', admin_password, 'admin'),
            (2, 'Aarav Mehta', 'aarav@campuspulse.edu', student_password, 'student'),
            (3, 'Ananya Iyer', 'ananya@campuspulse.edu', student_password, 'student'),
            (4, 'Priya Nair', 'priya@campuspulse.edu', student_password, 'student'),
            (5, 'Rohan Patel', 'rohan@campuspulse.edu', student_password, 'student'),
            (6, 'Kavya Desai', 'kavya@campuspulse.edu', student_password, 'student'),
        ]
        connection.executemany(
            'INSERT INTO users (id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)',
            user_rows,
        )

        event_ids = _seed_events(connection)

        registrations = [
            (2, event_ids['Campus Innovation Expo'], 'confirmed', '2026-11-15 09:00:00'),
            (3, event_ids['Campus Innovation Expo'], 'confirmed', '2026-11-15 09:14:00'),
            (4, event_ids['Cultural Night 2026'], 'confirmed', '2026-11-15 10:00:00'),
            (5, event_ids['AI for Everyday Problems'], 'confirmed', '2026-11-15 11:30:00'),
            (6, event_ids['Campus Wellness Week Kickoff'], 'confirmed', '2026-11-15 12:30:00'),
            (2, event_ids['Campus Wellness Week Kickoff'], 'confirmed', '2026-11-15 13:00:00'),
            (3, event_ids['Campus Wellness Week Kickoff'], 'confirmed', '2026-11-15 13:20:00'),
        ]
        connection.executemany(
            'INSERT INTO registrations (user_id, event_id, status, registered_at) VALUES (?, ?, ?, ?)',
            registrations,
        )

        waitlist_entries = [
            (4, event_ids['Campus Innovation Expo'], '2026-11-15 15:00:00', 'waiting'),
            (5, event_ids['Campus Innovation Expo'], '2026-11-15 15:40:00', 'waiting'),
        ]
        connection.executemany(
            'INSERT INTO waitlist (user_id, event_id, joined_at, status) VALUES (?, ?, ?, ?)',
            waitlist_entries,
        )

        feedback_rows = [
            (2, event_ids['Campus Wellness Week Kickoff'], 5, 'The wellness activities were thoughtful and the volunteers made everyone feel welcome.', '2026-11-15 18:00:00'),
            (3, event_ids['Campus Wellness Week Kickoff'], 4, 'A useful session with practical resources and a comfortable pace.', '2026-11-15 18:45:00'),
            (4, event_ids['Campus Wellness Week Kickoff'], 5, 'Enjoyed the mindfulness workshop and the friendly campus atmosphere.', '2026-11-15 19:15:00'),
        ]
        connection.executemany(
            'INSERT INTO feedback (user_id, event_id, rating, comment, created_at) VALUES (?, ?, ?, ?, ?)',
            feedback_rows,
        )


if __name__ == '__main__':
    init_db()
    seed_database()
    print(f'Initialized CampusPulse database at {DATABASE_PATH}')
