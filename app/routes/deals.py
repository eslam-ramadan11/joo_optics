"""Public route serving the homepage 'Today's Deals' section.

Admin management (add/remove/reorder, and the countdown) lives in
app/routes/admin.py, matching how other admin-curated lists (coupons,
product images) are organized there. This is the read-only,
customer-facing side.
"""
from typing import Tuple

from flask import Blueprint

from app.models.models import DailyDeal
from app.services import deals_service
from app.utils.response import api_response
from app.utils.limiter import limiter

bp = Blueprint('deals', __name__)


@bp.route('', methods=['GET'])
@limiter.limit('100 per minute')
def list_deals() -> Tuple[dict, int]:
    """Return today's curated deals, in admin-controlled display order,
    plus the countdown end time (if any) so the homepage can render a
    live countdown.

    If the countdown has expired, products is returned empty - server-
    side, so the deals session reliably ends on any fresh page load
    regardless of client-side clocks or whether a browser tab was left
    open past the deadline. The underlying DailyDeal rows are untouched,
    so the admin can start a new countdown later without re-curating.
    """
    countdown = deals_service.get_countdown()
    ends_at = countdown.ends_at if countdown else None
    expired = deals_service.is_countdown_expired()

    items = []
    if not expired:
        deals = DailyDeal.query.order_by(DailyDeal.sort_order.asc()).all()
        for d in deals:
            p = d.product
            if not p:
                continue
            items.append({
                'id': p.id,
                'name': p.name,
                'price': p.price,
                'old_price': p.old_price,
                'image_file': p.image_file,
                'category': p.category,
                'stock_quantity': p.stock_quantity,
                'discount_badge': p.discount_badge,
            })

    return api_response(True, {
        'products': items,
        'ends_at': ends_at.isoformat() if ends_at and not expired else None,
    })
