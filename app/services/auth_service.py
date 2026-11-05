"""Authentication service for user registration and password management."""
from datetime import date
from typing import Optional

from app.extensions import db, bcrypt
from app.models.models import User


class AuthService:
    """Service layer for authentication operations."""

    @staticmethod
    def register_user(username: str, email: str, password: str, date_of_birth: Optional[date] = None) -> User:
        """Register a new user with hashed password.
        
        Args:
            username: The user's username.
            email: The user's email address.
            password: The user's plaintext password (will be hashed with bcrypt).
            date_of_birth: The user's date of birth. The public /register
                endpoint requires this for every new signup; it's optional
                here at the service level so internal callers (create_admin.py,
                make_admin.py, tests) don't all need updating.
        
        Returns:
            The created User object.
        """
        pw_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(username=username, email=email, password_hash=pw_hash, date_of_birth=date_of_birth)
        db.session.add(user)
        db.session.commit()
        return user

    @staticmethod
    def change_password(user: User, new_password: str) -> None:
        """Change a user's password.
        
        Args:
            user: The User object whose password will be changed.
            new_password: The new plaintext password (will be hashed with bcrypt).
        """
        user.password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
        user.token_version += 1
        db.session.add(user)
        db.session.commit()
