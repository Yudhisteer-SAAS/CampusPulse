from flask import Blueprint, abort, jsonify, redirect, render_template, session, url_for

from database import get_db_connection
from routes.auth import login_required
from services.notifications import (
    get_notifications,
    get_notification_summary,
    mark_all_notifications_read,
    mark_notification_read,
)


notifications_bp = Blueprint('notifications', __name__, url_prefix='/notifications')


@notifications_bp.route('/')
@login_required
def index():
    return render_template('notifications/index.html', notifications=get_notifications(session['user_id']))


@notifications_bp.route('/recent')
@login_required
def recent():
    summary = get_notification_summary(session['user_id'])
    notifications = []
    for item in summary['recent']:
        notification = dict(item)
        event_id = notification['related_event_id']
        notification['event_url'] = (
            url_for('admin.event_detail', event_id=event_id)
            if event_id and session.get('role') == 'admin'
            else url_for('student.event_detail', event_id=event_id)
            if event_id
            else None
        )
        notifications.append(notification)
    return jsonify({'unread_count': summary['unread_count'], 'notifications': notifications})


@notifications_bp.route('/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_read(notification_id):
    if not mark_notification_read(session['user_id'], notification_id):
        with get_db_connection() as connection:
            exists = connection.execute(
                'SELECT 1 FROM notifications WHERE id = ? AND recipient_id = ?',
                (notification_id, session['user_id']),
            ).fetchone()
        if not exists:
            abort(404)
    return redirect(url_for('notifications.index'))


@notifications_bp.route('/read-all', methods=['POST'])
@login_required
def mark_all_read():
    mark_all_notifications_read(session['user_id'])
    return redirect(url_for('notifications.index'))
