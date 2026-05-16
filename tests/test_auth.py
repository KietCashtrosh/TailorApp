"""
Auth blueprint tests — register, login, logout, password validation.
"""
import pytest
from app.models import User


# ── Helpers ──────────────────────────────────────────────────────────────────

def register(client, name='Test User', email='test@example.com',
             phone='9000000001', password='StrongPass1', confirm=None, role='customer'):
    return client.post('/auth/register', data={
        'name': name,
        'email': email,
        'phone': phone,
        'password': password,
        'confirm_password': confirm or password,
        'role': role,
    }, follow_redirects=True)


def login(client, email='test@example.com', password='StrongPass1'):
    return client.post('/auth/login', data={
        'email': email,
        'password': password,
    }, follow_redirects=True)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestRegister:
    def test_customer_can_register(self, client, db):
        resp = register(client)
        assert resp.status_code == 200
        user = User.query.filter_by(email='test@example.com').first()
        assert user is not None
        assert user.role == 'customer'
        assert user.approval_status == 'approved'

    def test_duplicate_email_rejected(self, client, db):
        register(client)
        resp = register(client)  # same email
        assert b'already exists' in resp.data

    def test_short_password_rejected(self, client, db):
        resp = register(client, email='short@example.com', password='abc', confirm='abc')
        assert b'at least' in resp.data
        assert User.query.filter_by(email='short@example.com').first() is None

    def test_password_mismatch_rejected(self, client, db):
        resp = register(client, email='mismatch@example.com',
                        password='StrongPass1', confirm='different99')
        assert b'do not match' in resp.data

    def test_tailor_starts_pending(self, client, db):
        resp = register(client, email='tailor@example.com',
                        password='StrongPass1', role='tailor')
        user = User.query.filter_by(email='tailor@example.com').first()
        assert user is not None
        assert user.approval_status == 'pending'

    def test_invalid_role_rejected(self, client, db):
        resp = register(client, email='hacker@example.com',
                        password='StrongPass1', role='admin')
        assert User.query.filter_by(email='hacker@example.com').first() is None


class TestLogin:
    def test_valid_login_redirects(self, client, db):
        register(client)
        resp = login(client)
        assert resp.status_code == 200
        # Should NOT be on the login page any more
        assert b'Sign In' not in resp.data or b'Welcome' in resp.data

    def test_wrong_password_rejected(self, client, db):
        register(client)
        resp = login(client, password='wrongpassword')
        assert b'Invalid email or password' in resp.data

    def test_unknown_email_rejected(self, client, db):
        resp = login(client, email='nobody@example.com', password='StrongPass1')
        assert b'Invalid email or password' in resp.data


class TestLogout:
    def test_logout_requires_post(self, client, db):
        """Logout via GET should be rejected (405)."""
        register(client)
        login(client)
        resp = client.get('/auth/logout')
        assert resp.status_code == 405

    def test_logout_post_works(self, client, db):
        register(client)
        login(client)
        resp = client.post('/auth/logout', follow_redirects=True)
        assert resp.status_code == 200
        assert b'logged out' in resp.data
