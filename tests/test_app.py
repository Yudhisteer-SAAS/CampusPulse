import sqlite3
import os
import tempfile
import unittest
from io import BytesIO
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import werkzeug
from PIL import Image

os.environ.setdefault('CAMPUSPULSE_DB_PATH', str(Path(tempfile.mkdtemp()) / 'campuspulse.db'))
os.environ.setdefault('CAMPUSPULSE_SECRET_KEY', 'test-secret-key')

from app import app
import database
from config import EVENT_UPLOAD_DIR
from database import get_db_connection, init_db, seed_database
from services.attendance import check_in_attendance, create_attendance_pass
from services.feedback import get_feedback_summary, submit_feedback
from services.recommendations import get_recommendations, get_student_interests


class CampusPulseAppTests(unittest.TestCase):
    def setUp(self):
        init_db()
        seed_database()
        self.client = app.test_client()
        self.uploads_before = set(EVENT_UPLOAD_DIR.glob('*.webp')) if EVENT_UPLOAD_DIR.exists() else set()

    def tearDown(self):
        if EVENT_UPLOAD_DIR.exists():
            for path in set(EVENT_UPLOAD_DIR.glob('*.webp')) - self.uploads_before:
                path.unlink(missing_ok=True)

    @staticmethod
    def _png_upload(color):
        image_bytes = BytesIO()
        Image.new('RGB', (16, 12), color).save(image_bytes, format='PNG')
        image_bytes.seek(0)
        return image_bytes

    def get_csrf(self):
        with self.client.session_transaction() as session:
            return session.get('csrf_token')

    def login(self, email, password, route='/login'):
        self.client.get(route)
        token = self.get_csrf()
        return self.client.post(
            route,
            data={'email': email, 'password': password, 'csrf_token': token},
            follow_redirects=True,
        )

    def test_student_registration_and_duplicate_prevention(self):
        response = self.login('aarav@campuspulse.edu', 'Student@123')
        self.assertIn('Welcome back', response.get_data(as_text=True))

        event_id = self._get_event_id('Cultural Night 2026')
        token = self.get_csrf()
        response = self.client.post(
            f'/events/{event_id}/register',
            data={'csrf_token': token},
            follow_redirects=True,
        )
        self.assertIn('Registration confirmed successfully', response.get_data(as_text=True))
        self.assertIn('data:image/svg+xml;base64', response.get_data(as_text=True))
        with get_db_connection() as connection:
            self.assertEqual(
                connection.execute(
                    '''
                    SELECT COUNT(*) FROM attendance_passes p
                    JOIN registrations r ON r.id = p.registration_id
                    WHERE r.user_id = ? AND r.event_id = ?
                    ''',
                    (2, event_id),
                ).fetchone()[0],
                1,
            )

        duplicate = self.client.post(
            f'/events/{event_id}/register',
            data={'csrf_token': self.get_csrf()},
            follow_redirects=True,
        )
        self.assertIn('already registered or waitlisted', duplicate.get_data(as_text=True))

    def test_waitlist_promotion_after_cancel(self):
        with get_db_connection() as connection:
            connection.execute(
                'INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)',
                ('Test User One', 'one@example.com', werkzeug.security.generate_password_hash('Student@123'), 'student'),
            )
            connection.execute(
                'INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)',
                ('Test User Two', 'two@example.com', werkzeug.security.generate_password_hash('Student@123'), 'student'),
            )
            connection.execute(
                '''
                INSERT INTO events (title, description, category, date, time, venue, seat_limit, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                ('Capacity Test Event', 'A short event for waitlist testing.', 'Workshop', '2099-12-15', '10:00', 'Hall B', 1, 1),
            )

        event_id = self._get_event_id('Capacity Test Event')

        self.login('one@example.com', 'Student@123')
        token = self.get_csrf()
        response = self.client.post(
            f'/events/{event_id}/register',
            data={'csrf_token': token},
            follow_redirects=True,
        )
        self.assertIn('Registration confirmed successfully', response.get_data(as_text=True))

        self.client.get('/logout')
        self.login('two@example.com', 'Student@123')
        token = self.get_csrf()
        response = self.client.post(
            f'/events/{event_id}/register',
            data={'csrf_token': token},
            follow_redirects=True,
        )
        self.assertIn('The event is full. You were added to the waitlist', response.get_data(as_text=True))

        self.client.get('/logout')
        self.login('one@example.com', 'Student@123')
        token = self.get_csrf()
        response = self.client.post(
            f'/events/{event_id}/cancel',
            data={'csrf_token': token},
            follow_redirects=True,
        )
        self.assertIn('The next waitlisted student was promoted', response.get_data(as_text=True))

        self.client.get('/logout')
        self.login('two@example.com', 'Student@123')
        response = self.client.get(f'/events/{event_id}', follow_redirects=True)
        self.assertIn('Confirmed registration', response.get_data(as_text=True))

    def test_admin_login_and_event_management(self):
        response = self.login('admin@campuspulse.edu', 'Admin@123', route='/admin/login')
        self.assertIn('Admin login successful', response.get_data(as_text=True))

        response = self.client.get('/admin/dashboard')
        self.assertIn('Administration dashboard', response.get_data(as_text=True))
        self.assertIn('2 registered', response.get_data(as_text=True))
        self.assertIn('2 waitlisted', response.get_data(as_text=True))

        token = self.get_csrf()
        response = self.client.post(
            '/admin/events/new',
            data={
                'csrf_token': token,
                'title': 'New Test Event',
                'description': 'This event is created through the admin management flow.',
                'category': 'Workshop',
                'date': '2099-12-01',
                'time': '12:30',
                'venue': 'Innovation Lab',
                'seat_limit': '50',
            },
            follow_redirects=True,
        )
        self.assertIn('Event created successfully', response.get_data(as_text=True))

        event_id = self._get_event_id('New Test Event')
        token = self.get_csrf()
        response = self.client.post(
            f'/admin/events/{event_id}/edit',
            data={
                'csrf_token': token,
                'title': 'Updated Test Event',
                'description': 'This event was edited through the admin dashboard.',
                'category': 'Technical',
                'date': '2099-12-05',
                'time': '14:00',
                'venue': 'Updated Lab',
                'seat_limit': '60',
            },
            follow_redirects=True,
        )
        self.assertIn('Event updated successfully', response.get_data(as_text=True))

    def test_event_image_upload_replace_remove_and_validation(self):
        self.login('admin@campuspulse.edu', 'Admin@123', route='/admin/login')
        response = self.client.post(
            '/admin/events/new',
            data={
                'csrf_token': self.get_csrf(),
                'title': 'Image Upload Test Event',
                'description': 'An event used to test secure poster and gallery uploads.',
                'category': 'Workshop',
                'date': '2099-12-20',
                'time': '12:30',
                'venue': 'Innovation Lab',
                'seat_limit': '50',
                'poster': (self._png_upload((30, 70, 90)), 'poster.png'),
                'gallery_images': [
                    (self._png_upload((80, 120, 40)), 'gallery-one.png'),
                    (self._png_upload((120, 40, 80)), 'gallery-two.png'),
                ],
            },
            follow_redirects=True,
        )
        self.assertIn('Event created successfully', response.get_data(as_text=True))

        with get_db_connection() as connection:
            event = connection.execute(
                'SELECT id, poster_path FROM events WHERE title = ?',
                ('Image Upload Test Event',),
            ).fetchone()
            gallery = connection.execute(
                'SELECT id, image_path FROM event_images WHERE event_id = ? ORDER BY id',
                (event['id'],),
            ).fetchall()
        self.assertTrue(event['poster_path'].endswith('.webp'))
        self.assertEqual(len(gallery), 2)
        poster_response = self.client.get(f"/events/{event['id']}/poster-image")
        gallery_response = self.client.get(f"/event-images/{gallery[0]['id']}")
        self.assertEqual(poster_response.mimetype, 'image/webp')
        self.assertEqual(gallery_response.mimetype, 'image/webp')
        poster_response.close()
        gallery_response.close()
        original_paths = [EVENT_UPLOAD_DIR / event['poster_path']] + [
            EVENT_UPLOAD_DIR / image['image_path'] for image in gallery
        ]

        response = self.client.post(
            f"/admin/events/{event['id']}/edit",
            data={
                'csrf_token': self.get_csrf(),
                'title': 'Image Upload Test Event',
                'description': 'An event used to test secure poster and gallery uploads.',
                'category': 'Workshop',
                'date': '2099-12-20',
                'time': '12:30',
                'venue': 'Innovation Lab',
                'seat_limit': '50',
                'remove_poster': '1',
                'remove_gallery_image': str(gallery[0]['id']),
            },
            follow_redirects=True,
        )
        self.assertIn('Event updated successfully', response.get_data(as_text=True))
        with get_db_connection() as connection:
            updated_event = connection.execute(
                'SELECT poster_path FROM events WHERE id = ?',
                (event['id'],),
            ).fetchone()
            remaining_images = connection.execute(
                'SELECT id, image_path FROM event_images WHERE event_id = ?',
                (event['id'],),
            ).fetchall()
        self.assertIsNone(updated_event['poster_path'])
        self.assertEqual([image['id'] for image in remaining_images], [gallery[1]['id']])
        self.assertFalse(original_paths[0].exists())
        self.assertFalse(original_paths[1].exists())
        self.assertTrue(original_paths[2].exists())

        invalid_response = self.client.post(
            '/admin/events/new',
            data={
                'csrf_token': self.get_csrf(),
                'title': 'Invalid Image Test Event',
                'description': 'An event used to reject files with invalid image contents.',
                'category': 'Workshop',
                'date': '2099-12-21',
                'time': '12:30',
                'venue': 'Innovation Lab',
                'seat_limit': '50',
                'poster': (BytesIO(b'not an image'), 'fake.png'),
            },
            follow_redirects=True,
        )
        self.assertIn('not a valid image', invalid_response.get_data(as_text=True))
        with get_db_connection() as connection:
            self.assertIsNone(connection.execute(
                'SELECT id FROM events WHERE title = ?',
                ('Invalid Image Test Event',),
            ).fetchone())

    def test_notification_recipients_ownership_reading_and_event_updates(self):
        with get_db_connection() as connection:
            event_cursor = connection.execute(
                '''
                INSERT INTO events (title, description, category, date, time, venue, seat_limit, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    'Notification Test Event',
                    'An event used to verify notification ownership and updates.',
                    'Workshop',
                    '2099-12-22',
                    '14:00',
                    'Studio C',
                    5,
                    1,
                ),
            )
            event_id = event_cursor.lastrowid

        self.login('aarav@campuspulse.edu', 'Student@123')
        with get_db_connection() as connection:
            student_id = connection.execute(
                'SELECT id FROM users WHERE email = ?',
                ('aarav@campuspulse.edu',),
            ).fetchone()['id']
        self.client.post(
            f'/events/{event_id}/register',
            data={'csrf_token': self.get_csrf()},
        )
        with get_db_connection() as connection:
            student_notification = connection.execute(
                '''
                SELECT id FROM notifications
                WHERE recipient_id = ? AND event_id = ? AND type = 'registration_confirmed'
                ''',
                (student_id, event_id),
            ).fetchone()
            admin_notification = connection.execute(
                '''
                SELECT id FROM notifications
                WHERE recipient_id = 1 AND event_id = ? AND type = 'student_registered'
                ''',
                (event_id,),
            ).fetchone()
        self.assertIsNotNone(student_notification)
        self.assertIsNotNone(admin_notification)

        self.client.get('/logout')
        self.login('ananya@campuspulse.edu', 'Student@123')
        unauthorized = self.client.post(
            f"/notifications/{student_notification['id']}/read",
            data={'csrf_token': self.get_csrf()},
        )
        self.assertEqual(unauthorized.status_code, 404)

        self.client.get('/logout')
        self.login('aarav@campuspulse.edu', 'Student@123')
        marked = self.client.post(
            f"/notifications/{student_notification['id']}/read",
            data={'csrf_token': self.get_csrf()},
        )
        self.assertEqual(marked.status_code, 302)
        self.client.post(
            '/notifications/read-all',
            data={'csrf_token': self.get_csrf()},
        )
        with get_db_connection() as connection:
            unread = connection.execute(
                'SELECT COUNT(*) FROM notifications WHERE recipient_id = ? AND read_at IS NULL',
                (student_id,),
            ).fetchone()[0]
        self.assertEqual(unread, 0)

        self.client.get('/logout')
        self.login('admin@campuspulse.edu', 'Admin@123', route='/admin/login')
        updated = self.client.post(
            f'/admin/events/{event_id}/edit',
            data={
                'csrf_token': self.get_csrf(),
                'title': 'Notification Test Event Updated',
                'description': 'An event used to verify notification ownership and updates.',
                'category': 'Workshop',
                'date': '2099-12-22',
                'time': '14:00',
                'venue': 'Studio C',
                'seat_limit': '5',
            },
        )
        self.assertEqual(updated.status_code, 302)
        with get_db_connection() as connection:
            update_notice = connection.execute(
                '''
                SELECT message FROM notifications
                WHERE recipient_id = ? AND event_id = ? AND type = 'event_updated'
                ''',
                (student_id, event_id),
            ).fetchone()
        self.assertIsNotNone(update_notice)
        self.assertIn('Title: Notification Test Event → Notification Test Event Updated', update_notice['message'])

    def test_seeded_demo_data_shows_waitlist_and_feedback_to_admin(self):
        with get_db_connection() as connection:
            demo_event_count = connection.execute(
                '''
                SELECT COUNT(*) AS total FROM events
                WHERE title IN (
                    'Campus Innovation Expo',
                    'Cultural Night 2026',
                    'Intercollege Football League',
                    'AI for Everyday Problems',
                    'Startup Storytelling Seminar',
                    'Campus Wellness Week Kickoff'
                )
                '''
            ).fetchone()['total']
            waitlist_event_id = connection.execute(
                'SELECT event_id FROM waitlist LIMIT 1'
            ).fetchone()['event_id']
            feedback_event_id = connection.execute(
                'SELECT event_id FROM feedback LIMIT 1'
            ).fetchone()['event_id']
        self.assertEqual(demo_event_count, 6)

        self.login('admin@campuspulse.edu', 'Admin@123', route='/admin/login')
        waitlist_response = self.client.get(f'/admin/events/{waitlist_event_id}')
        self.assertIn('Priya Nair', waitlist_response.get_data(as_text=True))
        feedback_response = self.client.get(f'/admin/events/{feedback_event_id}')
        self.assertIn('Aarav Mehta', feedback_response.get_data(as_text=True))

    def test_invalid_login_and_csrf_and_sql_injection(self):
        response = self.login('fake@campuspulse.edu', 'wrongpass')
        self.assertIn('Invalid email or password', response.get_data(as_text=True))

        self.client.get('/login')
        csrf_response = self.client.post('/login', data={'email': 'aarav@campuspulse.edu', 'password': 'Student@123'}, follow_redirects=True)
        self.assertEqual(csrf_response.status_code, 403)

        injection_response = self.client.post(
            '/login',
            data={'email': "' OR 1=1 --", 'password': 'nonsense', 'csrf_token': self.get_csrf()},
            follow_redirects=True,
        )
        self.assertIn('Invalid email or password', injection_response.get_data(as_text=True))

    def test_student_cannot_access_admin_routes(self):
        self.login('aarav@campuspulse.edu', 'Student@123')
        response = self.client.get('/admin/dashboard', follow_redirects=True)
        self.assertIn('Student login', response.get_data(as_text=True))

    def test_feedback_rules_and_average_rating(self):
        with get_db_connection() as connection:
            connection.execute(
                'INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)',
                ('Feedback Tester', 'feedback@test.com', werkzeug.security.generate_password_hash('Student@123'), 'student'),
            )
            event_cursor = connection.execute(
                '''
                INSERT INTO events (title, description, category, date, time, venue, seat_limit, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                ('Past Event Feedback', 'This event has already happened.', 'Seminar', '2020-01-01', '10:00', 'Room T', 20, 1),
            )
            event_id = connection.execute('SELECT id FROM events WHERE title = ?', ('Past Event Feedback',)).fetchone()['id']
            user_id = connection.execute('SELECT id FROM users WHERE email = ?', ('feedback@test.com',)).fetchone()['id']
            connection.execute(
                'INSERT INTO registrations (user_id, event_id, status, registered_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)',
                (user_id, event_id, 'confirmed'),
            )

        self.login('feedback@test.com', 'Student@123')
        token = self.get_csrf()
        response = self.client.post(
            f'/feedback/{event_id}',
            data={'rating': '5', 'comment': 'A very polished event with a strong speaker and thoughtful setup.', 'csrf_token': token},
            follow_redirects=True,
        )
        self.assertIn('Feedback submitted successfully', response.get_data(as_text=True))

        summary = get_feedback_summary(event_id)
        self.assertEqual(summary['total_count'], 1)
        self.assertEqual(summary['average_rating'], 5.0)

        with get_db_connection() as connection:
            connection.execute(
                '''
                INSERT INTO events (title, description, category, date, time, venue, seat_limit, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                ('Future Event Feedback', 'This event is in the future and should reject feedback.', 'Workshop', '2099-12-20', '09:00', 'Room F', 25, 1),
            )
            future_event_id = connection.execute('SELECT id FROM events WHERE title = ?', ('Future Event Feedback',)).fetchone()['id']
            connection.execute(
                'INSERT INTO registrations (user_id, event_id, status, registered_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)',
                (user_id, future_event_id, 'confirmed'),
            )

        token = self.get_csrf()
        response = self.client.post(
            f'/feedback/{future_event_id}',
            data={'rating': '4', 'comment': 'This should be rejected because the event is not over yet.', 'csrf_token': token},
            follow_redirects=True,
        )
        self.assertIn('Feedback can only be submitted after the event date has passed', response.get_data(as_text=True))

    def test_event_browsing_and_filtering(self):
        self.login('aarav@campuspulse.edu', 'Student@123')
        response = self.client.get('/events?category=Technical', follow_redirects=True)
        self.assertIn('Event catalog', response.get_data(as_text=True))
        self.assertIn('Technical', response.get_data(as_text=True))

    def test_interests_persist_and_recommendations_exclude_unavailable_events(self):
        self.login('aarav@campuspulse.edu', 'Student@123')
        with get_db_connection() as connection:
            user_id = connection.execute(
                'SELECT id FROM users WHERE email = ?',
                ('aarav@campuspulse.edu',),
            ).fetchone()['id']
            connection.execute(
                '''
                INSERT INTO events (title, description, category, date, time, venue, seat_limit, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    'Personalized Sports Event',
                    'An upcoming sports event created for recommendation coverage.',
                    'Sports',
                    (date.today() + timedelta(days=40)).isoformat(),
                    '12:00',
                    'Sports Hall',
                    20,
                    1,
                ),
            )
            connection.execute(
                '''
                INSERT INTO events (title, description, category, date, time, venue, seat_limit, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    'Historical Category Event',
                    'A technical event matching the student registration history.',
                    'Technical',
                    (date.today() + timedelta(days=50)).isoformat(),
                    '13:00',
                    'Lab A',
                    20,
                    1,
                ),
            )

        response = self.client.post(
            '/profile',
            data={'csrf_token': self.get_csrf(), 'categories': ['Sports']},
            follow_redirects=True,
        )
        self.assertIn('Your interests have been updated', response.get_data(as_text=True))
        self.client.get('/logout')
        self.login('aarav@campuspulse.edu', 'Student@123')
        self.assertEqual(get_student_interests(user_id), ['Sports'])

        recommendations = get_recommendations(user_id)
        titles = [event['title'] for event in recommendations]
        self.assertEqual(recommendations[0]['category'], 'Sports')
        self.assertIn('Personalized Sports Event', titles)
        self.assertIn('Historical Category Event', titles)
        self.assertNotIn('Campus Innovation Expo', titles)
        self.assertNotIn('Campus Wellness Week Kickoff', titles)
        self.assertEqual(len(titles), len(set(titles)))

    def test_qr_passes_and_admin_attendance_check_in(self):
        self.login('aarav@campuspulse.edu', 'Student@123')
        with get_db_connection() as connection:
            user_id = connection.execute(
                'SELECT id FROM users WHERE email = ?',
                ('aarav@campuspulse.edu',),
            ).fetchone()['id']
            registration_ids = connection.execute(
                'SELECT id FROM registrations WHERE user_id = ? ORDER BY id',
                (user_id,),
            ).fetchall()
            test_event = connection.execute(
                '''
                INSERT INTO events (title, description, category, date, time, venue, seat_limit, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    'Second Pass Test Event',
                    'A second confirmed event for QR pass uniqueness coverage.',
                    'Workshop',
                    (date.today() + timedelta(days=45)).isoformat(),
                    '11:00',
                    'Workshop Room',
                    5,
                    1,
                ),
            )
            connection.execute(
                '''
                INSERT INTO registrations (user_id, event_id, status)
                VALUES (?, ?, 'confirmed')
                ''',
                (user_id, test_event.lastrowid),
            )
            registration_ids = connection.execute(
                'SELECT id FROM registrations WHERE user_id = ? ORDER BY id',
                (user_id,),
            ).fetchall()

        self.assertGreaterEqual(len(registration_ids), 2)
        pass_one = create_attendance_pass(user_id, registration_ids[0]['id'])
        pass_two = create_attendance_pass(user_id, registration_ids[1]['id'])
        self.assertNotEqual(pass_one['token'], pass_two['token'])

        passes_response = self.client.get('/my-qr-passes')
        self.assertEqual(passes_response.status_code, 200)
        self.assertIn('data:image/svg+xml;base64', passes_response.get_data(as_text=True))
        self.assertIn('Download QR pass', passes_response.get_data(as_text=True))
        self.assertEqual(self.client.get('/admin/attendance-scanner').status_code, 302)
        student_check_in = self.client.post(
            '/admin/attendance-scanner',
            data={'csrf_token': self.get_csrf(), 'pass_code': pass_two['token']},
        )
        self.assertEqual(student_check_in.status_code, 302)
        with get_db_connection() as connection:
            self.assertEqual(
                connection.execute('SELECT COUNT(*) FROM attendance').fetchone()[0],
                0,
            )

        self.client.get('/logout')
        self.login('admin@campuspulse.edu', 'Admin@123', route='/admin/login')
        response = self.client.post(
            '/admin/attendance-scanner',
            data={'csrf_token': self.get_csrf(), 'pass_code': pass_one['token']},
            follow_redirects=True,
        )
        self.assertIn('Attendance recorded for Aarav Mehta', response.get_data(as_text=True))
        with get_db_connection() as connection:
            event_id = connection.execute(
                'SELECT event_id FROM registrations WHERE id = ?',
                (registration_ids[0]['id'],),
            ).fetchone()['event_id']
        attendance_response = self.client.get(f'/admin/events/{event_id}')
        self.assertIn('1 present', attendance_response.get_data(as_text=True))
        self.assertIn('Present', attendance_response.get_data(as_text=True))

        duplicate = self.client.post(
            '/admin/attendance-scanner',
            data={'csrf_token': self.get_csrf(), 'pass_code': pass_one['token']},
            follow_redirects=True,
        )
        self.assertIn('Attendance has already been recorded', duplicate.get_data(as_text=True))
        with self.assertRaisesRegex(ValueError, 'invalid or no longer active'):
            check_in_attendance('not-a-valid-pass', 1)

    def test_cancelled_registration_pass_is_invalid(self):
        self.login('aarav@campuspulse.edu', 'Student@123')
        with get_db_connection() as connection:
            user_id = connection.execute(
                'SELECT id FROM users WHERE email = ?',
                ('aarav@campuspulse.edu',),
            ).fetchone()['id']
            event_cursor = connection.execute(
                '''
                INSERT INTO events (title, description, category, date, time, venue, seat_limit, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    'Cancellable Pass Event',
                    'An event used to verify cancelled passes cannot check in.',
                    'Workshop',
                    (date.today() + timedelta(days=35)).isoformat(),
                    '15:00',
                    'Studio C',
                    5,
                    1,
                ),
            )
            event_id = event_cursor.lastrowid
            connection.execute(
                'INSERT INTO registrations (user_id, event_id, status) VALUES (?, ?, ?)',
                (user_id, event_id, 'confirmed'),
            )
            registration_id = connection.execute(
                'SELECT id FROM registrations WHERE user_id = ? AND event_id = ?',
                (user_id, event_id),
            ).fetchone()['id']

        attendance_pass = create_attendance_pass(user_id, registration_id)
        self.client.post(
            f'/events/{event_id}/cancel',
            data={'csrf_token': self.get_csrf()},
        )
        with self.assertRaisesRegex(ValueError, 'invalid or no longer active'):
            check_in_attendance(attendance_pass['token'], 1)

    def test_phase_two_migration_preserves_legacy_data(self):
        legacy_path = Path(tempfile.mkdtemp()) / 'legacy.db'
        connection = sqlite3.connect(legacy_path)
        try:
            connection.executescript(
                '''
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
                    role TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
                    description TEXT NOT NULL, category TEXT NOT NULL, date TEXT NOT NULL,
                    time TEXT NOT NULL, venue TEXT NOT NULL, seat_limit INTEGER NOT NULL,
                    created_by INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE registrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                    event_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'confirmed',
                    registered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, event_id)
                );
                INSERT INTO users (id, name, email, password_hash, role)
                VALUES (1, 'Legacy Admin', 'legacy@example.com', 'hash', 'admin');
                INSERT INTO events (id, title, description, category, date, time, venue, seat_limit, created_by)
                VALUES (1, 'Legacy Event', 'Existing event data remains available.', 'Seminar',
                        '2099-12-15', '10:00', 'Hall', 10, 1);
                INSERT INTO registrations (id, user_id, event_id)
                VALUES (1, 1, 1);
                '''
            )
        finally:
            connection.close()

        with patch.object(database, 'DATABASE_PATH', legacy_path):
            init_db()
            with get_db_connection() as connection:
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM users').fetchone()[0], 1)
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM events').fetchone()[0], 1)
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM registrations').fetchone()[0], 1)
                tables = {
                    row['name'] for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                self.assertIn('user_interests', tables)
                self.assertIn('attendance_passes', tables)
                self.assertIn('attendance', tables)

    def _get_event_id(self, title):
        with get_db_connection() as connection:
            row = connection.execute('SELECT id FROM events WHERE title = ?', (title,)).fetchone()
            return row['id']


if __name__ == '__main__':
    unittest.main(verbosity=2)
