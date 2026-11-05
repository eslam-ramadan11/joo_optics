"""Coupon routes: the customer-facing preview/validate endpoint.

Admin CRUD for coupons lives in app/routes/admin.py (matching how other
admin-only management endpoints - products, users - are organized there).
"""
from typing import Tuple, List, Dict, Any

from flask import Blueprint, request, g

from app.models.models import Product, Prescription
from app.services import lens_pricing, coupon_service
from app.utils.response import api_response
from app.utils.limiter import limiter
from app.middleware.auth import login_required

bp = Blueprint('coupons', __name__)


def _resolve_priced_items(user_id: int, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build the priced_items list coupon_service needs, from raw client
    item data - mirrors exactly how OrderService prices each item (same
    Product lookup, same lens_pricing calls), so a previewed discount here
    always matches what actually gets charged at checkout.

    Raises ValueError on any invalid product/prescription reference -
    callers should catch this and surface it as a normal error response.
    """
    product_ids = {int(it['product_id']) for it in items}
    products = {p.id: p for p in Product.query.filter(Product.id.in_(product_ids)).all()}

    prescription_ids = {int(it['prescription_id']) for it in items if it.get('prescription_id') is not None}
    prescriptions = {}
    if prescription_ids:
        owned = Prescription.query.filter(
            Prescription.id.in_(prescription_ids), Prescription.user_id == user_id
        ).all()
        prescriptions = {p.id: p for p in owned}

    priced_items = []
    for it in items:
        pid = int(it['product_id'])
        product = products.get(pid)
        if not product:
            raise ValueError(f'product {pid} not found')

        qty = int(it.get('quantity', 1))
        lens_type = (it.get('lens_type') or '').strip()
        lens_price = 0.0

        if lens_type:
            prescription_id = it.get('prescription_id')
            prescription = prescriptions.get(int(prescription_id)) if prescription_id is not None else None
            if prescription:
                tier = lens_pricing.calculate_tier(
                    prescription.sph_r, prescription.cyl_r, prescription.sph_l, prescription.cyl_l
                )
                price = lens_pricing.get_price(lens_type, tier)
                lens_price = float(price) if price is not None else 0.0
            # If there's no valid prescription yet, lens_price stays 0 -
            # this only affects the live preview (e.g. "lenses only"
            # coupons showing $0 discount until a prescription is picked)
            # and never affects the real charge, which OrderService
            # computes independently and will reject an unpriceable
            # lens/prescription combination outright.

        priced_items.append({
            'product_id': pid,
            'category': product.category,
            'quantity': qty,
            'frame_price': float(product.price),
            'lens_price': lens_price,
        })

    return priced_items


@bp.route('/validate', methods=['POST'])
@login_required
@limiter.limit('30 per minute')
def validate_coupon() -> Tuple[dict, int]:
    """Preview a coupon's discount against the customer's current cart.

    Request JSON:
        code (str): the coupon code
        items (list): [{product_id, quantity, prescription_id?, lens_type?}, ...]
            - same shape as the order-creation payload.

    This never records a "use" of the coupon - that only happens when an
    order is actually placed (see OrderService.create_order).
    """
    data = request.get_json() or {}
    code = (data.get('code') or '').strip()
    items = data.get('items') or []

    if not code:
        return api_response(False, {}, 'coupon code is required', 400)
    if not items:
        return api_response(False, {}, 'cart is empty', 400)

    try:
        priced_items = _resolve_priced_items(g.current_user.id, items)
    except (ValueError, TypeError, KeyError) as e:
        return api_response(False, {}, f'invalid cart data: {e}', 400)

    subtotal = sum((it['frame_price'] + it['lens_price']) * it['quantity'] for it in priced_items)

    coupon, discount, error = coupon_service.validate_and_calculate(code, g.current_user.id, priced_items)

    if error:
        return api_response(False, {'subtotal': round(subtotal, 2)}, error, 400)

    return api_response(True, {
        'code': coupon.code,
        'subtotal': round(subtotal, 2),
        'discount': discount,
        'total': round(subtotal - discount, 2),
    })
