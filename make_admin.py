#!/usr/bin/env python
"""One-off helper: promote an existing user to admin.

There is no API endpoint for this on purpose - only someone with direct
access to the server/database should be able to grant admin rights.

Usage:
    python make_admin.py <username>
"""
import sys

from app import create_app
from app.extensions import db
from app.models.models import User


def main():
    if len(sys.argv) != 2:
        print("Usage: python make_admin.py <username>")
        sys.exit(1)

    username = sys.argv[1]
    app = create_app()

    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if not user:
            print(f"No user found with username '{username}'. "
                  f"Register that account on the website first, then run this again.")
            sys.exit(1)

        if user.is_admin:
            print(f"'{username}' is already an admin.")
            sys.exit(0)

        user.is_admin = True
        db.session.commit()
        print(f"Done - '{username}' is now an admin. Log out and log back in on the site to pick it up.")


if __name__ == '__main__':
    main()
