import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / 'instance'
DEFAULT_DB_PATH = INSTANCE_DIR / 'campuspulse.db'
DATABASE_PATH = Path(os.environ.get('CAMPUSPULSE_DB_PATH', str(DEFAULT_DB_PATH)))
SECRET_KEY = os.environ.get('CAMPUSPULSE_SECRET_KEY', 'dev-secret-key-change-me')

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = False
PERMANENT_SESSION_LIFETIME = 3600
