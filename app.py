import secrets

from flask import Flask, abort, render_template, request, session

from config import SECRET_KEY
from database import get_db_connection, init_db, seed_database
from routes.admin import admin_bp
from routes.auth import auth_bp
from routes.notifications import notifications_bp
from routes.student import student_bp
from services.notifications import get_notification_summary


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = SECRET_KEY
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = False
    app.config['MAX_CONTENT_LENGTH'] = 56 * 1024 * 1024

    init_db()
    seed_database()

    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(notifications_bp)

    @app.before_request
    def ensure_csrf_token():
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_hex(32)

        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            submitted_token = request.form.get('csrf_token') or request.headers.get('X-CSRFToken')
            if not submitted_token or submitted_token != session.get('csrf_token'):
                abort(403)

    @app.after_request
    def add_security_headers(response):
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "worker-src 'self' blob:; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self';"
        )
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.context_processor
    def inject_current_user():
        user_id = session.get('user_id')
        user = None
        if user_id:
            with get_db_connection() as connection:
                user = connection.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        notification_summary = (
            get_notification_summary(user['id']) if user else {'unread_count': 0, 'recent': []}
        )
        notification_preview = []
        for item in notification_summary['recent']:
            notification = dict(item)
            event_id = notification['related_event_id']
            notification['event_url'] = (
                f"/admin/events/{event_id}"
                if event_id and user['role'] == 'admin'
                else f"/events/{event_id}"
                if event_id
                else None
            )
            notification_preview.append(notification)
        return {
            'current_user': user,
            'notification_unread_count': notification_summary['unread_count'],
            'notification_preview': notification_preview,
        }

    @app.errorhandler(403)
    def access_forbidden(error):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def page_not_found(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(error):
        return render_template('errors/500.html'), 500

    return app


app = create_app()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
