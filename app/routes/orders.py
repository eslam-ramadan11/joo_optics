"""Order management routes for creating and managing orders."""
from typing import Tuple
import hashlib
import json
from flask import Blueprint, request, g, current_app
from marshmallow import ValidationError

from app.middleware.auth import login_required, admin_required
from app.services.order_service import OrderService
from app.schemas.order_schema import OrderSchema
from app.utils.response import api_response
from app.utils.limiter import limiter

bp = Blueprint('orders', __name__)
order_schema = OrderSchema()


@bp.route('', methods=['POST'])
@login_required
@limiter.limit('20 per minute')
def create_order() -> Tuple[dict, int]:
    """Create a new order.

    Request JSON:
        - address_id (int): Shipping address ID (must belong to the caller)
        - items (list): product_id, prescription_id, quantity, lens_type.
          Pricing is always computed server-side from the current product
          price — any price sent by the client is ignored.
        - coupon_code (str, optional): discount code. Re-validated from
          scratch server-side - any subtotal/discount shown to the
          customer beforehand is just a preview, never trusted here.

    Returns:
        tuple: JSON response with created order ID/total or error message.
    """
    json_data = request.get_json() or {}
    try:
        data = order_schema.load(json_data)
    except ValidationError as e:
        return api_response(False, {}, e.messages, 400)
    except Exception as e:
        current_app.logger.error(f'Unexpected error validating order payload: {e}')
        return api_response(False, {}, 'Invalid request data.', 400)

    user = g.current_user
    idempotency_key = (request.headers.get('Idempotency-Key') or '').strip() or None
    fingerprint = hashlib.sha256(json.dumps(
        json_data, sort_keys=True, separators=(',', ':'), default=str
    ).encode('utf-8')).hexdigest() if idempotency_key else None
    try:
        order = OrderService.create_order(
            user_id=user.id,
            address_id=data['address_id'],
            items=data['items'],
            coupon_code=data.get('coupon_code'),
            attribution={
                key: data.get(key)
                for key in ('utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'fbp', 'fbc', 'ga4_client_id')
            },
            idempotency_key=idempotency_key,
            idempotency_fingerprint=fingerprint,
        )
        return api_response(True, {
            'id': order.id,
            'total_amount': order.total_amount,
            'discount_amount': order.discount_amount,
        }, status_code=201)
    except ValueError as e:
        return api_response(False, {}, str(e), 400)
    except Exception as e:
        current_app.logger.error(f"Error creating order: {e}")
        return api_response(False, {}, "An error occurred while creating the order.", 500)


@bp.route('', methods=['GET'])
@login_required
@limiter.limit('20 per minute')
def list_orders() -> Tuple[dict, int]:
    """List orders for the current user (or all if admin)."""
    user = g.current_user
    try:
        items = OrderService.list_orders(user_id=user.id if not user.is_admin else None)
        order_list = [
            {
                'id': o.id,
                'user_id': o.user_id,
                'total_amount': o.total_amount,
                'discount_amount': o.discount_amount,
                'coupon_code': o.coupon.code if o.coupon else None,
                'status': o.status,
                'date_posted': o.date_posted.isoformat() if o.date_posted else None,
                # So the customer's order list can offer "pay online"
                # again after an abandoned/declined card attempt.
                'payment_status': o.payment.payment_status if o.payment else None,
                'payment_method': o.payment.payment_method if o.payment else None,
            }
            for o in items
        ]
        return api_response(True, order_list)
    except Exception as e:
        current_app.logger.error(f"Error listing orders: {e}")
        return api_response(False, {}, "An error occurred while listing orders.", 500)


@bp.route('/<int:order_id>', methods=['GET'])
@login_required
@limiter.limit('20 per minute')
def get_order(order_id: int) -> Tuple[dict, int]:
    """Retrieve order details by ID (owner or admin only)."""
    o = OrderService.get_order(order_id)
    if not o:
        return api_response(False, {}, 'Order not found', 404)

    user = g.current_user
    if o.user_id != user.id and not user.is_admin:
        return api_response(False, {}, 'Forbidden', 403)

    data = {
        'id': o.id,
        'user_id': o.user_id,
        'address_id': o.address_id,
        'status': o.status,
        'total_amount': o.total_amount,
        'discount_amount': o.discount_amount,
        'coupon_code': o.coupon.code if o.coupon else None,
        'date_posted': o.date_posted.isoformat() if o.date_posted else None,
        'payment_status': o.payment.payment_status if o.payment else None,
        'payment_method': o.payment.payment_method if o.payment else None,
        'items': [
            {
                'product_id': it.product_id,
                'product_name': it.product.name if it.product else None,
                'prescription_id': it.prescription_id,
                'quantity': it.quantity,
                'item_price': it.item_price,
            }
            for it in o.order_items
        ],
    }
    return api_response(True, data)


@bp.route('/<int:order_id>', methods=['PUT'])
@admin_required
@limiter.limit('20 per minute')
def update_order(order_id: int) -> Tuple[dict, int]:
    """Update order status (admin only)."""
    o = OrderService.get_order(order_id)
    if not o:
        return api_response(False, {}, 'Order not found', 404)

    json_data = request.get_json() or {}
    status = json_data.get('status', '').strip()
    if not status:
        return api_response(False, {}, 'status is required', 400)

    valid_statuses = ['pending', 'processing', 'shipped', 'delivered', 'cancelled']
    if status not in valid_statuses:
        return api_response(False, {}, f'status must be one of {valid_statuses}', 400)

    try:
        o = OrderService.update_order_status(o, status)
        return api_response(True, {'id': o.id, 'status': o.status})
    except Exception as e:
        current_app.logger.error(f"Error updating order {order_id}: {e}")
        return api_response(False, {}, "An error occurred while updating the order.", 500)


@bp.route('/<int:order_id>', methods=['DELETE'])
@admin_required
@limiter.limit('20 per minute')
def delete_order(order_id: int) -> Tuple[dict, int]:
    """Delete an order (admin only)."""
    o = OrderService.get_order(order_id)
    if not o:
        return api_response(False, {}, 'Order not found', 404)

    try:
        OrderService.delete_order(o)
        return api_response(True, {}, 'Order deleted')
    except Exception as e:
        current_app.logger.error(f"Error deleting order {order_id}: {e}")
        return api_response(False, {}, "An error occurred while deleting the order.", 500)
