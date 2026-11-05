"""Authentication/authorization decorators.

login_required: validates the JWT and loads the current user into g.current_user.
admin_required: same, plus requires user.is_admin to be True.
"""
from functools import wraps

from flask import g
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt

from app.models.models import User
from app.utils.response import api_response


def _load_current_user():
    verify_jwt_in_request()
    identity = get_jwt_identity()
    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        user_id = identity
    user = User.query.get(user_id)
    claims = get_jwt()
    if user and claims.get('token_version', 0) != user.token_version:
        return None
    return user


def login_required(fn):
    """Require a valid JWT and attach the authenticated user to g.current_user."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = _load_current_user()
        if not user:
            return api_response(False, {}, 'user not found', 401)
        g.current_user = user
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    """Require a valid JWT belonging to an admin user."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = _load_current_user()
        if not user:
            return api_response(False, {}, 'user not found', 401)
        if not user.is_admin:
            return api_response(False, {}, 'Forbidden: admin access required', 403)
        g.current_user = user
        return fn(*args, **kwargs)
    return wrapper
