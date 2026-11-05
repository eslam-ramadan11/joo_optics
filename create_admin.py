#!/usr/bin/env python
"""One-off helper: create a ready-made admin account in one step.

Unlike make_admin.py (which promotes an EXISTING user), this creates a
brand-new user AND grants admin rights immediately - no need to register
on the website first.

The password is NOT stored in this file (a password written in source code
is a security hole). You are asked for it when you run the script, or you
can set the ADMIN_PASSWORD environment variable instead.

Usage:
    python create_admin.py
"""
import getpass
import os
import sys

from app import create_app
from app.extensions import db
from app.models.models import User
from app.services.auth_service import AuthService

USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@joooptics.local')


def _get_password() -> str:
    password = os.environ.get('ADMIN_PASSWORD')
    if password:
        return password
    while True:
        first = getpass.getpass('Choose an admin password (at least 10 characters): ')
        if len(first) < 10:
            print('Too short - use at least 10 characters.')
            continue
        if first != getpass.getpass('Type it again: '):
            print("The two passwords don't match - try again.")
            continue
        return first


def main():
    app = create_app()

    with app.app_context():
        existing = User.query.filter(
            (User.username == USERNAME) | (User.email == EMAIL)
        ).first()

        if existing:
            if existing.is_admin:
                print(f"'{USERNAME}' already exists and is already an admin. Nothing to do.")
            else:
                existing.is_admin = True
                db.session.commit()
                print(f"'{USERNAME}' already existed as a regular user - promoted to admin.")
            return

        password = _get_password()
        if len(password) < 10:
            print('ADMIN_PASSWORD must be at least 10 characters.')
            sys.exit(1)

        user = AuthService.register_user(username=USERNAME, email=EMAIL, password=password)
        user.is_admin = True
        db.session.commit()

        print("Admin account created:")
        print(f"  username: {USERNAME}")
        print(f"  email:    {EMAIL}")
        print("Log in with these at /login.html, then go to admin/admin.html.")


if __name__ == '__main__':
    main()
