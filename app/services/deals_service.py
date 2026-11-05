"""Service for the homepage 'Today's Deals' countdown (see DealsCountdown
in app/models/models.py for the full design rationale). A tiny singleton -
there is at most one meaningful row, always the one with the lowest id.
"""
from datetime import datetime
from typing import Optional

from app.extensions import db
from app.models.models import DealsCountdown


def get_countdown() -> Optional[DealsCountdown]:
    """Return the singleton countdown row, or None if the admin has never
    set one. None is equivalent to 'no active countdown' - callers should
    treat it the same as a row with ends_at=None.
    """
    return DealsCountdown.query.order_by(DealsCountdown.id.asc()).first()


def is_countdown_expired() -> bool:
    """True only if a countdown was actually set and its end time has
    passed. No countdown at all (get_countdown() is None, or ends_at is
    None) is NOT 'expired' - it means the deals section has no
    expiration and shows indefinitely.
    """
    countdown = get_countdown()
    return bool(countdown and countdown.ends_at and countdown.ends_at <= datetime.utcnow())


def set_countdown(ends_at: datetime) -> DealsCountdown:
    """Start (or replace) the countdown - always updates the same
    singleton row rather than accumulating history."""
    countdown = get_countdown()
    if countdown:
        countdown.ends_at = ends_at
    else:
        countdown = DealsCountdown(ends_at=ends_at)
        db.session.add(countdown)
    db.session.commit()
    return countdown


def clear_countdown() -> None:
    """Cancel any active countdown - the deals section goes back to
    showing indefinitely (until the admin removes products via
    DailyDeal directly)."""
    countdown = get_countdown()
    if countdown:
        countdown.ends_at = None
        db.session.commit()
