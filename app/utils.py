"""Session token helpers. Role/username always come from the DB, never from a header."""

import secrets
import datetime
from functools import wraps
from flask import request, jsonify, current_app
from sqlalchemy import update
from app.models import db, Session, User


LOCKOUT_THRESHOLD = 5
LOCKOUT_MINUTES = 5


def register_failed_attempt(username):
    """Atomically increments a user's failed_attempts counter and applies
    lockout once the threshold is reached.

    The increment is done as a single ``UPDATE users SET failed_attempts =
    failed_attempts + 1`` statement rather than the previous
    read-modify-write (``user.failed_attempts += 1``), which had a race
    window: under concurrent requests, several requests could each read the
    same starting count before any of them committed, so increments were
    lost and the lockout threshold could be bypassed by brute-forcing in
    parallel instead of sequentially. Computing the new value in the
    database itself removes that window; SQLite serializes writers, so this
    single statement can't lose an increment no matter how many requests
    arrive at once.

    Returns (user, attempts, just_locked). just_locked is True only for the
    single request that actually flips the account into a locked state, so
    callers can log a distinct "account locked" event without every
    concurrent request racing to log it.
    """
    db.session.execute(
        update(User)
        .where(User.username == username)
        .values(failed_attempts=User.failed_attempts + 1)
    )
    db.session.commit()

    user = User.query.filter_by(username=username).first()
    if user is None:
        return None, 0, False

    now = datetime.datetime.utcnow()
    just_locked = False
    if user.failed_attempts >= LOCKOUT_THRESHOLD and (
        not user.locked_until or user.locked_until <= now
    ):
        user.locked_until = now + datetime.timedelta(minutes=LOCKOUT_MINUTES)
        db.session.commit()
        just_locked = True

    return user, user.failed_attempts, just_locked


def reset_failed_attempts(user):
    """Clears the lockout state after a successful authentication step."""
    user.failed_attempts = 0
    user.locked_until = None
    db.session.commit()


def create_session(username, role):
    """Issue a new session token after successful login."""
    token = secrets.token_hex(32)
    timeout = current_app.config.get("SESSION_TIMEOUT_MINUTES", 30)
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=timeout)

    session_row = Session(
        token=token, username=username, role=role, expires_at=expires_at
    )
    db.session.add(session_row)
    db.session.commit()
    return token, expires_at


def _extract_token():
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return request.headers.get("X-Session-Token")


def get_current_session():
    """Validate the token against the DB. Returns None if missing/expired."""
    token = _extract_token()
    if not token:
        return None

    session_row = Session.query.filter_by(token=token).first()
    if not session_row:
        return None

    if session_row.expires_at < datetime.datetime.utcnow():
        db.session.delete(session_row)
        db.session.commit()
        return None

    return session_row


def invalidate_session(token):
    session_row = Session.query.filter_by(token=token).first()
    if session_row:
        db.session.delete(session_row)
        db.session.commit()
        return True
    return False


def require_auth(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        session_row = get_current_session()
        if session_row is None:
            return jsonify({"error": "Authentication required or session expired"}), 401
        request.current_session = session_row
        return view_func(*args, **kwargs)
    return wrapped


def require_role(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            session_row = get_current_session()
            if session_row is None:
                return jsonify({"error": "Authentication required or session expired"}), 401
            if session_row.role not in allowed_roles:
                return jsonify({"error": "Forbidden: insufficient role"}), 403
            request.current_session = session_row
            return view_func(*args, **kwargs)
        return wrapped
    return decorator
