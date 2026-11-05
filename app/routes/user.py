"""User profile routes."""
from typing import Tuple

from flask import Blueprint, current_app, g, request
from marshmallow import ValidationError

from app.middleware.auth import login_required
from app.schemas.user_profile_schema import UserProfileSchema
from app.services.user_service import UserService
from app.utils.limiter import limiter
from app.utils.response import api_response

bp = Blueprint('user', __name__)
user_profile_schema = UserProfileSchema()


@bp.route('/profile', methods=['GET'])
@login_required
@limiter.limit('30 per minute')
def get_profile() -> Tuple[dict, int]:
    """Return the authenticated user's profile."""
    user = g.current_user
    return api_response(
        True,
        {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_admin': user.is_admin,
            'created_at': user.created_at.isoformat() if user.created_at else None,
        },
    )


@bp.route('/profile', methods=['PUT'])
@login_required
@limiter.limit('30 per minute')
def update_profile() -> Tuple[dict, int]:
    """Update the authenticated user's profile."""
    json_data = request.get_json() or {}
    try:
        data = user_profile_schema.load(json_data, partial=True)
    except ValidationError as exc:
        return api_response(False, {}, exc.messages, 400)

    try:
        user = UserService.update_profile(g.current_user, data)
    except ValueError as exc:
        return api_response(False, {}, str(exc), 400)
    except Exception as exc:
        current_app.logger.error(f'Error updating profile for user {g.current_user.id}: {exc}')
        return api_response(False, {}, 'An error occurred while updating your profile.', 500)

    return api_response(
        True,
        {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_admin': user.is_admin,
            'created_at': user.created_at.isoformat() if user.created_at else None,
        },
    )
