"""
Pytest fixtures for TailorApp.

Run: pytest tests/ -v
"""
import pytest
from app import create_app, db as _db
from config import TestingConfig


@pytest.fixture(scope='session')
def app():
    """Create a test application with an in-memory SQLite DB."""
    _app = create_app(TestingConfig)
    with _app.app_context():
        _db.create_all()
        yield _app
        _db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    """Flask test client — resets DB between tests."""
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='function')
def db(app):
    """Return the DB session; rolls back after each test."""
    with app.app_context():
        yield _db
        _db.session.rollback()
