import re
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db_connection


auth_bp = Blueprint('auth', __name__)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please log in to continue.', 'error')
            return redirect(url_for('auth.login'))
        return view(*args, **kwargs)
    return wrapped


def student_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get('role') != 'student':
            flash('Student access is required for this page.', 'error')
            return redirect(url_for('student.dashboard'))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('Administrative access is required for this page.', 'error')
            return redirect(url_for('auth.login'))
        return view(*args, **kwargs)
    return wrapped


def _validate_email(email):
    pattern = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'
    return bool(re.fullmatch(pattern, email))


@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        confirm_password = request.form.get('confirm_password') or ''

        if len(name) < 2:
            flash('Please enter a valid full name.', 'error')
            return render_template('auth/signup.html')
        if not _validate_email(email):
            flash('Please provide a valid email address.', 'error')
            return render_template('auth/signup.html')
        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
            return render_template('auth/signup.html')
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('auth/signup.html')

        with get_db_connection() as connection:
            existing_user = connection.execute(
                'SELECT * FROM users WHERE email = ?',
                (email,),
            ).fetchone()
            if existing_user:
                flash('An account with that email already exists.', 'error')
                return render_template('auth/signup.html')

            cursor = connection.execute(
                'INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)',
                (name, email, generate_password_hash(password), 'student'),
            )
            user_id = cursor.lastrowid

        session.clear()
        session['user_id'] = user_id
        session['role'] = 'student'
        flash('Your student account was created successfully.', 'success')
        return redirect(url_for('student.dashboard'))

    return render_template('auth/signup.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        if session.get('role') == 'admin':
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('student.dashboard'))

    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''

        with get_db_connection() as connection:
            user = connection.execute(
                'SELECT * FROM users WHERE email = ?',
                (email,),
            ).fetchone()

        if not user or not check_password_hash(user['password_hash'], password):
            flash('Invalid email or password. Please try again.', 'error')
            return render_template('auth/login.html')

        session.clear()
        session['user_id'] = user['id']
        session['role'] = user['role']
        flash('Welcome back.', 'success')

        if user['role'] == 'admin':
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('student.dashboard'))

    return render_template('auth/login.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('auth.login'))
