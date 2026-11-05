"""Admin blueprint: endpoints for admin dashboard, product creation and orders listing."""
from typing import List, Dict
from datetime import datetime, timedelta

from flask import Blueprint, current_app, jsonify, url_for, request, g
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from marshmallow import ValidationError

from app.middleware.auth import admin_required
from app.services.order_service import OrderService
from app.services.auth_service import AuthService
from app.services import deals_service
from app.extensions import db
from app.models.models import Product, Order, User, Coupon, DailyDeal
from app.schemas.coupon_schema import CouponSchema
from app.utils.response import api_response
from app.utils.limiter import limiter

bp = Blueprint('admin', __name__)
coupon_schema = CouponSchema()


@bp.route('/orders', methods=['GET'])
@admin_required
def list_orders():
    """Return all orders for admin view."""
    orders = OrderService.list_orders()
    out: List[Dict] = []
    for o in orders:
        # The order's prescription is the first item that has one - the
        # first item may be plain sunglasses with no prescription at all.
        rx = next((it.prescription for it in o.order_items if it.prescription), None)
        items = []
        for it in o.order_items:
            items.append({
                'product_id': it.product_id,
                'product_name': it.product.name if it.product else None,
                'quantity': it.quantity,
                'item_price': it.item_price,
                'lens_type': it.lens_type,
                'sph_r': getattr(it.prescription, 'sph_r', None) if it.prescription else None,
                'cyl_r': getattr(it.prescription, 'cyl_r', None) if it.prescription else None,
                'axis_r': getattr(it.prescription, 'axis_r', None) if it.prescription else None,
                'sph_l': getattr(it.prescription, 'sph_l', None) if it.prescription else None,
                'cyl_l': getattr(it.prescription, 'cyl_l', None) if it.prescription else None,
                'axis_l': getattr(it.prescription, 'axis_l', None) if it.prescription else None,
            })

        out.append({
            'order_id': o.id,
            'date': o.date_posted.isoformat(),
            'status': o.status,
            'user_id': o.user_id,
            'username': o.user.username if o.user else None,
            'customer_email': o.user.email if o.user else None,
            # Where to deliver and who to call - without these the shop
            # has no way to actually fulfil a cash-on-delivery order.
            'shipping': {
                'city': o.shipping_address.city,
                'full_address': o.shipping_address.full_address,
                'phone_number': o.shipping_address.phone_number,
            } if o.shipping_address else None,
            'items': items,
            'total_amount': o.total_amount,
            'discount_amount': o.discount_amount,
            'coupon_code': o.coupon.code if o.coupon else None,
            'payment_id': o.payment.id if o.payment else None,
            'payment_status': o.payment.payment_status if o.payment else None,
            'payment_method': o.payment.payment_method if o.payment else None,
            'prescription_id': rx.id if rx else None,
            'prescription_url': url_for(
                'prescriptions.download_prescription_file',
                prescription_id=rx.id,
                _external=False,
            ) if rx else None,
        })

    return jsonify(out)


@bp.route('/dashboard-stats', methods=['GET'])
@admin_required
def dashboard_stats():
    """Return simple aggregated statistics for dashboard."""
    total_sales = 0.0
    total_orders = 0
    total_customers = 0
    chart_data = []
    chart_labels = []

    try:
        total_orders = Order.query.count()
        paid_orders = Order.query.join(Order.payment).filter(
            Order.payment.has(payment_status='completed')
        ).all()
        total_sales = sum(o.total_amount for o in paid_orders)
        total_customers = User.query.count()

        categories = [row[0] for row in Product.query.with_entities(Product.category).distinct().order_by(Product.category).all()]
        for cat in categories:
            # FIX: raw SQL must be wrapped in sqlalchemy.text() for
            # db.session.execute() to accept it (SQLAlchemy 1.4/2.0). Without
            # this the call raised and was silently swallowed below, so the
            # chart always came back empty.
            sql = text(
                "select sum(oi.item_price * oi.quantity) from order_items oi "
                "join products p on p.id = oi.product_id "
                "where p.category = :cat"
            )
            val = db.session.execute(sql, {'cat': cat}).scalar() or 0
            chart_labels.append(cat)
            chart_data.append(float(val))

    except Exception:
        current_app.logger.exception('Error computing dashboard stats')

    return jsonify({
        'total_sales': float(total_sales),
        'total_orders': int(total_orders),
        'total_customers': int(total_customers),
        'chart_labels': chart_labels,
        'chart_data': chart_data
    })


@bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    """Return registered users for admin management."""
    from datetime import date

    users = User.query.order_by(User.created_at.desc()).all()

    def _age(dob):
        if not dob:
            return None
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    return jsonify([
        {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_admin': user.is_admin,
            'created_at': user.created_at.isoformat() if user.created_at else None,
            'date_of_birth': user.date_of_birth.isoformat() if user.date_of_birth else None,
            'age': _age(user.date_of_birth),
        }
        for user in users
    ])


@bp.route('/users', methods=['POST'])
@admin_required
@limiter.limit('10 per minute')
def create_admin_user():
    """Create a brand-new user account with admin rights already granted.

    This is separate from the public /api/auth/register endpoint (which
    always creates non-admin accounts) - only an existing admin can reach
    this one, and it's the only place in the whole API that can set
    is_admin=True on creation.
    """
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')

    if not username or not email or not password:
        return api_response(False, {}, 'username, email and password are required', 400)

    if len(password) < 12:
        return api_response(False, {}, 'admin password must be at least 12 characters', 400)

    if User.query.filter((User.username == username) | (User.email == email)).first():
        return api_response(False, {}, 'username or email already exists', 409)

    try:
        user = AuthService.register_user(username=username, email=email, password=password)
        user.is_admin = True
        db.session.add(user)
        db.session.commit()
        return api_response(True, {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_admin': user.is_admin,
        }, status_code=201)
    except Exception as e:
        current_app.logger.error(f'Error creating admin user: {e}')
        return api_response(False, {}, 'Could not create the admin account.', 500)


@bp.route('/users/<int:user_id>/role', methods=['PUT'])
@admin_required
@limiter.limit('20 per minute')
def update_user_role(user_id: int):
    """Promote a user to admin, or demote an admin back to a regular user.

    SECURITY / SAFETY:
    - An admin can't demote themselves (avoids locking yourself out by
      accident - ask another admin to do it if that's really the intent).
    - The last remaining admin can't be demoted, ever, from this endpoint -
      otherwise the site could end up with zero admins and no way back in
      short of directly editing the database again.
    """
    data = request.get_json() or {}
    if 'is_admin' not in data:
        return api_response(False, {}, 'is_admin (true/false) is required', 400)

    # bool("false") is True - only accept a real JSON boolean so a string
    # can never promote a user to admin by accident.
    if not isinstance(data['is_admin'], bool):
        return api_response(False, {}, 'is_admin must be true or false (a JSON boolean)', 400)
    make_admin = data['is_admin']

    user = User.query.get(user_id)
    if not user:
        return api_response(False, {}, 'User not found', 404)

    current_admin = g.current_user
    if not make_admin:
        if user.id == current_admin.id:
            return api_response(False, {}, "You can't remove your own admin rights.", 400)

        admin_count = User.query.filter_by(is_admin=True).count()
        if user.is_admin and admin_count <= 1:
            return api_response(False, {}, 'Cannot remove the last remaining admin.', 400)

    user.is_admin = make_admin
    db.session.add(user)
    db.session.commit()

    return api_response(True, {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'is_admin': user.is_admin,
    })


def _coupon_dict(c: Coupon) -> dict:
    return {
        'id': c.id,
        'code': c.code,
        'discount_type': c.discount_type,
        'discount_value': c.discount_value,
        'start_date': c.start_date.isoformat() if c.start_date else None,
        'end_date': c.end_date.isoformat() if c.end_date else None,
        'is_active': c.is_active,
        'max_total_uses': c.max_total_uses,
        'max_uses_per_customer': c.max_uses_per_customer,
        'apply_to': c.apply_to,
        'apply_to_value': c.apply_to_value,
        'min_order_amount': c.min_order_amount,
        'max_discount_amount': c.max_discount_amount,
        'created_at': c.created_at.isoformat() if c.created_at else None,
        'total_uses': Order.query.filter_by(coupon_id=c.id).count(),
    }


@bp.route('/coupons', methods=['GET'])
@admin_required
def list_coupons():
    """List all discount coupons for the admin panel."""
    coupons = Coupon.query.order_by(Coupon.created_at.desc()).all()
    return jsonify([_coupon_dict(c) for c in coupons])


@bp.route('/coupons', methods=['POST'])
@admin_required
@limiter.limit('30 per minute')
def create_coupon():
    """Create a new discount coupon."""
    try:
        data = coupon_schema.load(request.get_json() or {})
    except ValidationError as err:
        return api_response(False, {}, str(err.messages), 400)

    if Coupon.query.filter_by(code=data['code']).first():
        return api_response(False, {}, 'A coupon with this code already exists.', 409)

    coupon = Coupon(**data)
    db.session.add(coupon)
    try:
        db.session.commit()
    except IntegrityError:
        # Backstop for the rare race between the check above and this
        # commit (two admins creating the same code within milliseconds
        # of each other) - the DB's own unique constraint on code is what
        # actually prevents the duplicate; this just keeps the response a
        # friendly message instead of falling through to a generic 500.
        db.session.rollback()
        return api_response(False, {}, 'A coupon with this code already exists.', 409)
    return api_response(True, _coupon_dict(coupon), status_code=201)


@bp.route('/coupons/<int:coupon_id>', methods=['PUT'])
@admin_required
@limiter.limit('30 per minute')
def update_coupon(coupon_id: int):
    """Update an existing discount coupon (partial update)."""
    coupon = Coupon.query.get(coupon_id)
    if not coupon:
        return api_response(False, {}, 'Coupon not found', 404)

    try:
        data = coupon_schema.load(request.get_json() or {}, partial=True)
    except ValidationError as err:
        return api_response(False, {}, str(err.messages), 400)

    if 'code' in data and data['code'] != coupon.code:
        if Coupon.query.filter_by(code=data['code']).first():
            return api_response(False, {}, 'A coupon with this code already exists.', 409)

    for field, value in data.items():
        setattr(coupon, field, value)

    db.session.add(coupon)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return api_response(False, {}, 'A coupon with this code already exists.', 409)
    return api_response(True, _coupon_dict(coupon))


@bp.route('/coupons/<int:coupon_id>', methods=['DELETE'])
@admin_required
@limiter.limit('30 per minute')
def delete_coupon(coupon_id: int):
    """Delete a discount coupon.

    Blocked if the coupon has already been used on any real order - that
    would leave order records pointing at nothing, and silently erases
    the fact that a discount was given. Deactivate it instead if it just
    needs to stop working going forward.
    """
    coupon = Coupon.query.get(coupon_id)
    if not coupon:
        return api_response(False, {}, 'Coupon not found', 404)

    used_count = Order.query.filter_by(coupon_id=coupon.id).count()
    if used_count > 0:
        return api_response(
            False, {},
            f'This coupon has been used on {used_count} order(s) and cannot be deleted. '
            f'Set it to inactive instead.',
            400,
        )

    db.session.delete(coupon)
    db.session.commit()
    return api_response(True, {}, 'Coupon deleted')


def _deal_dict(d: DailyDeal) -> dict:
    p = d.product
    return {
        'id': d.id,
        'sort_order': d.sort_order,
        'added_at': d.added_at.isoformat() if d.added_at else None,
        'product': {
            'id': p.id,
            'name': p.name,
            'price': p.price,
            'old_price': p.old_price,
            'image_file': p.image_file,
            'category': p.category,
            'stock_quantity': p.stock_quantity,
            'discount_badge': p.discount_badge,
        } if p else None,
    }


@bp.route('/deals', methods=['GET'])
@admin_required
def list_deals_admin():
    """List today's deals for the admin panel (includes full product info)."""
    deals = DailyDeal.query.order_by(DailyDeal.sort_order.asc()).all()
    return jsonify([_deal_dict(d) for d in deals])


@bp.route('/deals', methods=['POST'])
@admin_required
@limiter.limit('30 per minute')
def add_deal():
    """Add a product to the homepage 'Today's Deals' section."""
    data = request.get_json() or {}
    product_id = data.get('product_id')
    if not product_id:
        return api_response(False, {}, 'product_id is required', 400)

    product = Product.query.get(int(product_id))
    if not product:
        return api_response(False, {}, 'Product not found', 404)

    if DailyDeal.query.filter_by(product_id=product.id).first():
        return api_response(False, {}, 'This product is already in Today\'s Deals.', 409)

    max_order = db.session.query(db.func.max(DailyDeal.sort_order)).scalar()
    deal = DailyDeal(product_id=product.id, sort_order=(max_order or 0) + 1)
    db.session.add(deal)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return api_response(False, {}, 'This product is already in Today\'s Deals.', 409)
    return api_response(True, _deal_dict(deal), status_code=201)


@bp.route('/deals/<int:deal_id>', methods=['DELETE'])
@admin_required
@limiter.limit('30 per minute')
def remove_deal(deal_id: int):
    """Remove a product from Today's Deals (the product itself is untouched)."""
    deal = DailyDeal.query.get(deal_id)
    if not deal:
        return api_response(False, {}, 'Deal not found', 404)

    db.session.delete(deal)
    db.session.commit()
    return api_response(True, {}, 'Removed from Today\'s Deals')


@bp.route('/deals/reorder', methods=['PUT'])
@admin_required
@limiter.limit('30 per minute')
def reorder_deals():
    """Set the display order of Today's Deals.

    Request JSON: { "deal_ids": [3, 1, 2] } - the full list of deal ids in
    the desired display order (first shows first on the homepage).
    """
    data = request.get_json() or {}
    deal_ids = data.get('deal_ids')
    if not isinstance(deal_ids, list) or not deal_ids:
        return api_response(False, {}, 'deal_ids (non-empty list) is required', 400)

    deals = {d.id: d for d in DailyDeal.query.filter(DailyDeal.id.in_(deal_ids)).all()}
    if len(deals) != len(set(deal_ids)):
        return api_response(False, {}, 'One or more deal ids not found', 400)

    for index, deal_id in enumerate(deal_ids):
        deals[deal_id].sort_order = index
        db.session.add(deals[deal_id])

    db.session.commit()
    return api_response(True, {}, 'Order updated')


def _countdown_dict(countdown) -> dict:
    return {'ends_at': countdown.ends_at.isoformat() if countdown and countdown.ends_at else None}


@bp.route('/deals/countdown', methods=['GET'])
@admin_required
def get_deals_countdown():
    """Return the current Today's Deals countdown state, if any."""
    return api_response(True, _countdown_dict(deals_service.get_countdown()))


@bp.route('/deals/countdown', methods=['PUT'])
@admin_required
@limiter.limit('30 per minute')
def set_deals_countdown():
    """Start (or replace) the Today's Deals countdown.

    Request JSON, exactly one of:
        duration_minutes (number): end time computed server-side as
            now + this many minutes - preferred for quick-preset buttons
            ("3 hours", "24 hours") since it can't be thrown off by the
            admin's own device clock being wrong.
        ends_at (ISO datetime string): an exact end time, for a custom
            date/time picker. Must be in the future.
    """
    data = request.get_json() or {}
    duration_minutes = data.get('duration_minutes')
    ends_at_raw = data.get('ends_at')

    if duration_minutes is not None:
        try:
            duration_minutes = float(duration_minutes)
        except (TypeError, ValueError):
            return api_response(False, {}, 'duration_minutes must be a number', 400)
        if duration_minutes <= 0:
            return api_response(False, {}, 'duration_minutes must be positive', 400)
        ends_at = datetime.utcnow() + timedelta(minutes=duration_minutes)
    elif ends_at_raw:
        try:
            ends_at = datetime.fromisoformat(str(ends_at_raw).replace('Z', '+00:00')).replace(tzinfo=None)
        except ValueError:
            return api_response(False, {}, 'ends_at must be a valid ISO datetime', 400)
        if ends_at <= datetime.utcnow():
            return api_response(False, {}, 'ends_at must be in the future', 400)
    else:
        return api_response(False, {}, 'Provide either duration_minutes or ends_at', 400)

    countdown = deals_service.set_countdown(ends_at)
    return api_response(True, _countdown_dict(countdown))


@bp.route('/deals/countdown', methods=['DELETE'])
@admin_required
@limiter.limit('30 per minute')
def cancel_deals_countdown():
    """Cancel the countdown - Today's Deals goes back to showing
    indefinitely (the curated product list itself is untouched)."""
    deals_service.clear_countdown()
    return api_response(True, {}, 'Countdown cancelled')
