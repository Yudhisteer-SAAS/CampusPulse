import os
import tempfile
import unittest
from pathlib import Path

import werkzeug

os.environ.setdefault('CAMPUSPULSE_DB_PATH', str(Path(tempfile.mkdtemp()) / 'campuspulse.db'))
os.environ.setdefault('CAMPUSPULSE_SECRET_KEY', 'test-secret-key')

from app import app
from database import get_db_connection, init_db, seed_database
from services.feedback import get_feedback_summary, submit_feedback


class CampusPulseAppTests(unittest.TestCase):
    def setUp(self):
        init_db()
        seed_database()
        self.client = app.test_client()

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
        response = self.login('maya@campuspulse.edu', 'Student@123')
        self.assertIn('Welcome back', response.get_data(as_text=True))

        event_id = self._get_event_id('Design Sprint Challenge')
        token = self.get_csrf()
        response = self.client.post(
            f'/events/{event_id}/register',
            data={'csrf_token': token},
            follow_redirects=True,
        )
        self.assertIn('Registration confirmed successfully', response.get_data(as_text=True))

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

    def test_invalid_login_and_csrf_and_sql_injection(self):
        response = self.login('fake@campuspulse.edu', 'wrongpass')
        self.assertIn('Invalid email or password', response.get_data(as_text=True))

        self.client.get('/login')
        csrf_response = self.client.post('/login', data={'email': 'maya@campuspulse.edu', 'password': 'Student@123'}, follow_redirects=True)
        self.assertEqual(csrf_response.status_code, 403)

        injection_response = self.client.post(
            '/login',
            data={'email': "' OR 1=1 --", 'password': 'nonsense', 'csrf_token': self.get_csrf()},
            follow_redirects=True,
        )
        self.assertIn('Invalid email or password', injection_response.get_data(as_text=True))

    def test_student_cannot_access_admin_routes(self):
        self.login('maya@campuspulse.edu', 'Student@123')
        response = self.client.get('/admin/dashboard', follow_redirects=True)
        self.assertIn('Student login', response.get_data(as_text=True))

    def test_feedback_rules_and_average_rating(self):
        with get_db_connection() as connection:
            connection.execute(
                'INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)',
                ('Feedback Tester', 'feedback@test.com', werkzeug.security.generate_password_hash('Student@123'), 'student'),
            )
            connection.execute(
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
        self.login('maya@campuspulse.edu', 'Student@123')
        response = self.client.get('/events?category=Technical', follow_redirects=True)
        self.assertIn('Event catalog', response.get_data(as_text=True))
        self.assertIn('Technical', response.get_data(as_text=True))

    def _get_event_id(self, title):
        with get_db_connection() as connection:
            row = connection.execute('SELECT id FROM events WHERE title = ?', (title,)).fetchone()
            return row['id']


if __name__ == '__main__':
    unittest.main(verbosity=2)
