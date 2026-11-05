"""Coupon (discount code) service - validation and discount calculation.

Single source of truth used both by the /api/coupons/validate preview
endpoint and by OrderService.create_order at actual checkout, so the
discount a customer previews always matches what they're actually
charged.

IMPORTANT: this module never computes or modifies lens prices - it only
reads the already-computed frame_price/lens_price for each item (as
resolved by app.services.lens_pricing elsewhere) to decide how much of
the order a given coupon's scope applies to.
"""
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from app.models.models import Coupon, Order

ERROR_NOT_FOUND = 'كود الخصم غير صحيح.'
ERROR_EXPIRED = 'كود الخصم منتهي الصلاحية.'
ERROR_NOT_STARTED = 'كود الخصم غير متاح حاليًا.'
ERROR_INACTIVE = 'كود الخصم غير فعال.'
ERROR_TOTAL_LIMIT = 'تم الوصول إلى الحد الأقصى لاستخدام هذا الكود.'
ERROR_CUSTOMER_LIMIT = 'لقد استخدمت هذا الكود من قبل.'
ERROR_MIN_ORDER = 'الحد الأدنى للطلب غير متحقق لتطبيق هذا الكود.'
ERROR_NOT_ELIGIBLE = 'هذا الكود لا ينطبق على المنتجات في سلتك.'

VALID_APPLY_TO = {'all', 'cart', 'specific_products', 'category', 'lenses_only', 'frames_only'}
VALID_DISCOUNT_TYPES = {'percentage', 'fixed'}


def normalize_code(code: str) -> str:
    """Coupon codes are matched case-insensitively - always compare/store
    the normalized (uppercase, trimmed) form."""
    return (code or '').strip().upper()


def find_coupon(code: str, lock: bool = False) -> Optional[Coupon]:
    """lock=True acquires a row lock (SELECT ... FOR UPDATE) for the
    duration of the caller's transaction - only appropriate when about
    to actually commit to using this coupon (i.e. from
    OrderService.create_order), never for a preview/validate-only call.
    See validate_and_calculate's lock parameter for why this matters."""
    query = Coupon.query.filter_by(code=normalize_code(code))
    if lock:
        query = query.with_for_update()
    return query.first()


def _resolve_eligible_amount(coupon: Coupon, priced_items: List[Dict[str, Any]]) -> float:
    """Sum the portion of priced_items this coupon's scope applies to.

    Each item in priced_items must have: product_id, category, quantity,
    frame_price (per unit, the Product.price), lens_price (per unit, 0 if
    this item has no lens).
    """
    apply_to = coupon.apply_to
    specific_ids = set()
    if apply_to == 'specific_products' and coupon.apply_to_value:
        specific_ids = {int(x) for x in coupon.apply_to_value.split(',') if x.strip().isdigit()}

    total = 0.0
    for item in priced_items:
        qty = item['quantity']
        frame_total = item['frame_price'] * qty
        lens_total = item['lens_price'] * qty

        if apply_to in ('all', 'cart'):
            total += frame_total + lens_total
        elif apply_to == 'specific_products':
            if item['product_id'] in specific_ids:
                total += frame_total + lens_total
        elif apply_to == 'category':
            if coupon.apply_to_value and item['category'] == coupon.apply_to_value:
                total += frame_total + lens_total
        elif apply_to == 'lenses_only':
            total += lens_total
        elif apply_to == 'frames_only':
            total += frame_total

    return total


def validate_and_calculate(
    code: str,
    user_id: int,
    priced_items: List[Dict[str, Any]],
    lock: bool = False,
) -> Tuple[Optional[Coupon], float, Optional[str]]:
    """Validate a coupon code for a user and a priced cart, and compute the
    resulting discount.

    Args:
        lock: pass True only when this call is actually about to result
            in the coupon being used (OrderService.create_order) - it
            locks the coupon row for the rest of the caller's
            transaction, so two concurrent orders using the same
            single-use (or nearly-exhausted) coupon are serialized
            rather than both reading "0 uses so far" and both
            succeeding, which would let a coupon be used more times
            than max_total_uses/max_uses_per_customer allow. The public
            preview endpoint (/api/coupons/validate) must NOT set this -
            locking rows for a customer who's just checking whether a
            code works, and who may never actually place the order,
            would hold that lock for no reason and create needless
            contention.

    Returns (coupon, discount_amount, error_message). On any validation
    failure, coupon is None and discount_amount is 0.0 - callers should
    treat a non-None error as authoritative regardless of what coupon
    lookup happened internally.
    """
    coupon = find_coupon(code, lock=lock)
    if not coupon:
        return None, 0.0, ERROR_NOT_FOUND

    if not coupon.is_active:
        return None, 0.0, ERROR_INACTIVE

    now = datetime.utcnow()
    if coupon.start_date and now < coupon.start_date:
        return None, 0.0, ERROR_NOT_STARTED
    if coupon.end_date and now > coupon.end_date:
        return None, 0.0, ERROR_EXPIRED

    if coupon.max_total_uses is not None:
        total_uses = Order.query.filter_by(coupon_id=coupon.id).count()
        if total_uses >= coupon.max_total_uses:
            return None, 0.0, ERROR_TOTAL_LIMIT

    if coupon.max_uses_per_customer is not None:
        customer_uses = Order.query.filter_by(coupon_id=coupon.id, user_id=user_id).count()
        if customer_uses >= coupon.max_uses_per_customer:
            return None, 0.0, ERROR_CUSTOMER_LIMIT

    eligible_amount = _resolve_eligible_amount(coupon, priced_items)

    if coupon.min_order_amount is not None and eligible_amount < coupon.min_order_amount:
        return None, 0.0, ERROR_MIN_ORDER

    if eligible_amount <= 0:
        return None, 0.0, ERROR_NOT_ELIGIBLE

    if coupon.discount_type == 'percentage':
        discount = eligible_amount * (coupon.discount_value / 100.0)
        if coupon.max_discount_amount is not None:
            discount = min(discount, coupon.max_discount_amount)
    else:  # 'fixed'
        discount = coupon.discount_value

    # Never discount more than the eligible amount itself - keeps the
    # final total from going negative and matches "a coupon can't
    # discount more than what it's actually discounting".
    discount = max(0.0, min(discount, eligible_amount))

    return coupon, round(discount, 2), None
