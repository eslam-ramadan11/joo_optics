"""One-shot production maintenance tasks.

Run from a scheduler with the same environment as the application:
    python maintenance.py release-expired-reservations
"""
import sys

from app import create_app
from app.services.order_service import OrderService


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        if len(sys.argv) != 2 or sys.argv[1] != 'release-expired-reservations':
            raise SystemExit('usage: python maintenance.py release-expired-reservations')
        print(OrderService.release_expired_reservations())
