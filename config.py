import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    # ── Core ──────────────────────────────────────────────────────────────────
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', f'sqlite:///{os.path.join(basedir, "tailor_app.db")}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── Session & cookies ────────────────────────────────────────────────────
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = False   # overridden to True in ProductionConfig
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SECURE = False  # overridden to True in ProductionConfig

    # ── CSRF ─────────────────────────────────────────────────────────────────
    WTF_CSRF_TIME_LIMIT = 3600

    # ── File uploads ─────────────────────────────────────────────────────────
    UPLOAD_FOLDER = os.path.join(basedir, 'app', 'static', 'uploads')
    MAX_CONTENT_LENGTH = 4 * 1024 * 1024  # 4 MB max upload
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

    # ── Flask-Mail (MailHog locally; swap for SendGrid/SES in prod) ──────────
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'localhost')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 1025))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'false').lower() == 'true'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'false').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@tailorapp.com')

    # ── Business settings ────────────────────────────────────────────────────
    BOOKING_ADVANCE_DAYS = int(os.environ.get('BOOKING_ADVANCE_DAYS', 30))

    # Payment split percentages (must sum to 100)
    PLATFORM_FEE_PERCENT = int(os.environ.get('PLATFORM_FEE_PERCENT', 10))
    TAILOR_SHARE_PERCENT = int(os.environ.get('TAILOR_SHARE_PERCENT', 80))
    AGENT_SHARE_PERCENT = int(os.environ.get('AGENT_SHARE_PERCENT', 10))

    # ── Minimum password length ──────────────────────────────────────────────
    MIN_PASSWORD_LENGTH = 10


class DevelopmentConfig(Config):
    """Local dev — verbose errors, SQLite, insecure cookies (HTTP ok)."""
    DEBUG = True
    TESTING = False


class TestingConfig(Config):
    """Pytest — in-memory DB, CSRF disabled, fast."""
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key-not-for-production'


class ProductionConfig(Config):
    """Production — must have SECRET_KEY + DATABASE_URL in env."""
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True

    def __init__(self):
        super().__init__()
        # Fail-fast: refuse to start with the insecure default key
        if self.SECRET_KEY == 'dev-secret-change-in-production':
            raise RuntimeError(
                'SECRET_KEY environment variable must be set in production. '
                'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
            )
        if 'sqlite' in (self.SQLALCHEMY_DATABASE_URI or '').lower():
            import warnings
            warnings.warn(
                'SQLite is not recommended for production. Set DATABASE_URL to a '
                'PostgreSQL connection string.',
                stacklevel=2,
            )


# Map name → class for create_app(config_name='production') style usage
config_map = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}
