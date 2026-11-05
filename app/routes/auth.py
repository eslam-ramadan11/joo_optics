"""Authentication routes for user registration, login, and token management."""
from datetime import date, datetime
from typing import Tuple
from flask import Blueprint, request, g, current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
)

from app.extensions import bcrypt
from app.models.models import User
from app.services.auth_service import AuthService
from app.middleware.auth import login_required
from app.utils.limiter import limiter
from app.utils.response import api_response

bp = Blueprint('auth', __name__)

_MIN_BIRTH_YEAR_AGO = 120  # sanity bound, not an age-eligibility policy


@bp.route('/register', methods=['POST'])
@limiter.limit('5 per minute')
def register() -> Tuple[dict, int]:
    """Register a new user.
    
    Request JSON:
        - username (str): Unique username
        - email (str): Unique email
        - password (str): User password
        - date_of_birth (str): Required, format YYYY-MM-DD
    
    Returns:
        tuple: JSON response with access and refresh tokens or error message.
    """
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    dob_raw = (data.get('date_of_birth') or '').strip()

    if not username or not email or not password or not dob_raw:
        return api_response(False, {}, 'username, email, password and date_of_birth are required', 400)

    if len(password) < 10:
        return api_response(False, {}, 'password must be at least 10 characters', 400)

    try:
        date_of_birth = datetime.strptime(dob_raw, '%Y-%m-%d').date()
    except ValueError:
        return api_response(False, {}, 'date_of_birth must be in YYYY-MM-DD format', 400)

    today = date.today()
    if date_of_birth > today:
        return api_response(False, {}, 'date_of_birth cannot be in the future', 400)
    if date_of_birth.year < today.year - _MIN_BIRTH_YEAR_AGO:
        return api_response(False, {}, 'date_of_birth is not valid', 400)

    if User.query.filter((User.username == username) | (User.email == email)).first():
        return api_response(False, {}, 'username or email already exists', 409)

    try:
        user = AuthService.register_user(
            username=username, email=email, password=password, date_of_birth=date_of_birth
        )
        claims = {'is_admin': user.is_admin, 'token_version': user.token_version}
        access = create_access_token(identity=str(user.id), additional_claims=claims)
        refresh = create_refresh_token(identity=str(user.id))
        return api_response(True, {'access_token': access, 'refresh_token': refresh}, status_code=201)
    except Exception as e:
        current_app.logger.error(f'Error registering user: {e}')
        return api_response(False, {}, 'An error occurred while creating your account.', 500)


@bp.route('/login', methods=['POST'])
@limiter.limit('5 per minute')
def login() -> Tuple[dict, int]:
    """Authenticate a user and return access/refresh tokens.
    
    Request JSON:
        - username (str): Username or email
        - password (str): User password
    
    Returns:
        tuple: JSON response with access and refresh tokens or error message.
    """
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return api_response(False, {}, 'username and password required', 400)

    user = User.query.filter((User.username == username) | (User.email == username)).first()
    try:
        password_ok = bool(user) and bcrypt.check_password_hash(user.password_hash, password)
    except ValueError:
        # A malformed/corrupted password_hash should behave as "wrong
        # credentials", not crash the request with a 500.
        password_ok = False

    if not password_ok:
        return api_response(False, {}, 'invalid credentials', 401)

    claims = {'is_admin': user.is_admin, 'token_version': user.token_version}
    access = create_access_token(identity=str(user.id), additional_claims=claims)
    refresh = create_refresh_token(identity=str(user.id))
    return api_response(True, {'access_token': access, 'refresh_token': refresh})


@bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
@limiter.limit('30 per minute')
def refresh() -> Tuple[dict, int]:
    """Refresh access token using refresh token.
    
    Returns:
        tuple: JSON response with new access token or error message.
    """
    identity = get_jwt_identity()
    try:
        uid = int(identity)
    except Exception:
        uid = identity
    user = User.query.get(uid)
    if not user:
        return api_response(False, {}, 'User not found', 404)
    claims = {'is_admin': user.is_admin, 'token_version': user.token_version}
    access = create_access_token(identity=str(user.id), additional_claims=claims)
    return api_response(True, {'access_token': access})


@bp.route('/change-password', methods=['POST'])
@login_required
@limiter.limit('5 per minute')
def change_password() -> Tuple[dict, int]:
    """Change user password (requires old password).
    
    Request JSON:
        - old_password (str): Current password
        - new_password (str): New password
    
    Returns:
        tuple: JSON response with success or error message.
    """
    data = request.get_json() or {}
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')

    if not old_password or not new_password:
        return api_response(False, {}, 'old_password and new_password required', 400)

    if len(new_password) < 10:
        return api_response(False, {}, 'new_password must be at least 10 characters', 400)

    user = g.current_user
    if not bcrypt.check_password_hash(user.password_hash, old_password):
        return api_response(False, {}, 'old password is incorrect', 401)

    try:
        AuthService.change_password(user, new_password)
        return api_response(True, {}, 'password updated')
    except Exception as e:
        current_app.logger.error(f'Error changing password for user {user.id}: {e}')
        return api_response(False, {}, 'An error occurred while updating your password.', 500)
