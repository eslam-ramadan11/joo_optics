"""Service layer for user profile management."""
from typing import Any, Dict, Optional

from app.extensions import db
from app.models.models import User

# SECURITY: explicit whitelist of fields a user is allowed to self-update.
# Even though the route already validates through UserProfileSchema (which
# has no is_admin/password_hash/id fields), we enforce the whitelist again
# here so this service can never be misused by some future caller that
# forgets to go through the schema.
_EDITABLE_FIELDS = {'username', 'email', 'date_of_birth'}


class UserService:
    """Handle user profile retrieval and updates."""

    @staticmethod
    def get_profile(user_id: int) -> Optional[User]:
        """Return a user by id."""
        return User.query.get(user_id)

    @staticmethod
    def update_profile(user: User, data: Dict[str, Any]) -> User:
        """Update profile information for a user.

        Only fields in _EDITABLE_FIELDS are ever applied, regardless of
        what keys are present in `data`.
        """
        data = {k: v for k, v in data.items() if k in _EDITABLE_FIELDS}

        if 'username' in data and data['username'] != user.username:
            existing = User.query.filter(User.username == data['username'], User.id != user.id).first()
            if existing:
                raise ValueError('username already exists')

        if 'email' in data and data['email'] != user.email:
            existing = User.query.filter(User.email == data['email'], User.id != user.id).first()
            if existing:
                raise ValueError('email already exists')

        for key, value in data.items():
            setattr(user, key, value)

        db.session.add(user)
        db.session.commit()
        return user
