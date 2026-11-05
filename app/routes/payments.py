"""Payment routes for handling payment operations."""
from flask import Blueprint, request, g, current_app
from marshmallow import ValidationError

from app.middleware.auth import login_required, admin_required
from app.services.payment_service import PaymentService
from app.services import tracking_service
from app.services.order_service import OrderService
from app.services.paymob_service import PaymobError, verify_hmac
from app.schemas.payment_schema import PaymentSchema, PaymentUpdateSchema
from app.utils.response import api_response
from app.utils.limiter import limiter, RATE_LIMITS

bp = Blueprint('payments', __name__)
payment_schema = PaymentSchema()
payment_update_schema = PaymentUpdateSchema()


@bp.route('', methods=['POST'])
@login_required
@limiter.limit(RATE_LIMITS['payments'])
def create_payment() -> tuple:
    """Create a payment for an order.

    The payment amount is always order.total_amount computed server-side —
    it is never accepted from the request body.
    """
    json_data = request.get_json() or {}

    try:
        data = payment_schema.load(json_data)
    except ValidationError as e:
        return api_response(False, {}, e.messages, 400)

    order_id = data['order_id']
    order = OrderService.get_order(order_id)
    if not order:
        return api_response(False, {}, 'Order not found', 404)

    user = g.current_user
    if order.user_id != user.id and not user.is_admin:
        return api_response(False, {}, 'Forbidden', 403)

    try:
        payment = PaymentService.create_payment(
            order_id=order_id,
            payment_method=data['payment_method']
        )
    except ValueError as e:
        return api_response(False, {}, str(e), 400)

    return api_response(
        True,
        {
            'id': payment.id,
            'order_id': payment.order_id,
            'amount': payment.amount,
            'payment_method': payment.payment_method,
            'payment_status': payment.payment_status,
            'transaction_id': payment.transaction_id,
        },
        status_code=201
    )


@bp.route('/<int:payment_id>', methods=['GET'])
@login_required
@limiter.limit(RATE_LIMITS['payments'])
def get_payment(payment_id: int) -> tuple:
    """Get payment details by ID (owner or admin only)."""
    payment = PaymentService.get_payment(payment_id)
    if not payment:
        return api_response(False, {}, 'Payment not found', 404)

    user = g.current_user
    if payment.order.user_id != user.id and not user.is_admin:
        return api_response(False, {}, 'Forbidden', 403)

    return api_response(True, {
        'id': payment.id,
        'order_id': payment.order_id,
        'amount': payment.amount,
        'payment_method': payment.payment_method,
        'payment_status': payment.payment_status,
        'transaction_id': payment.transaction_id,
        'payment_date': payment.payment_date.isoformat() if payment.payment_date else None,
    })


@bp.route('/<int:payment_id>', methods=['PUT'])
@admin_required
@limiter.limit(RATE_LIMITS['payments'])
def update_payment(payment_id: int) -> tuple:
    """Update payment status (admin only)."""
    payment = PaymentService.get_payment(payment_id)
    if not payment:
        return api_response(False, {}, 'Payment not found', 404)

    json_data = request.get_json() or {}
    try:
        data = payment_update_schema.load(json_data)
    except ValidationError as e:
        return api_response(False, {}, e.messages, 400)

    payment = PaymentService.update_payment_status(payment, data['payment_status'])
    return api_response(True, {
        'id': payment.id,
        'order_id': payment.order_id,
        'payment_status': payment.payment_status,
        'transaction_id': payment.transaction_id,
    })


@bp.route('/paymob/initiate', methods=['POST'])
@login_required
@limiter.limit(RATE_LIMITS['payments'])
def initiate_paymob_payment() -> tuple:
    """Start (or resume) a Paymob card/wallet payment for one of the caller's orders.

    Returns an iframe_url the frontend should redirect the browser to.
    Actual payment success/failure is only ever recorded via the webhook
    below - this endpoint just kicks off the flow.
    """
    json_data = request.get_json() or {}
    order_id = json_data.get('order_id')
    if not order_id:
        return api_response(False, {}, 'order_id is required', 400)

    order = OrderService.get_order(order_id)
    if not order:
        return api_response(False, {}, 'Order not found', 404)

    user = g.current_user
    try:
        result = PaymentService.initiate_paymob_payment(order, user)
        return api_response(True, result)
    except ValueError as e:
        return api_response(False, {}, str(e), 400)
    except PaymobError as e:
        current_app.logger.error(f'Paymob initiate failed for order {order_id}: {e}')
        return api_response(False, {}, 'Could not start the payment. Please try again shortly.', 502)


@bp.route('/paymob/webhook', methods=['POST'])
@limiter.exempt
def paymob_webhook() -> tuple:
    """Server-to-server callback Paymob calls when a transaction is processed.

    SECURITY: this endpoint has no JWT (Paymob can't send one), so the HMAC
    signature is the ONLY thing standing between this endpoint and anyone
    on the internet being able to mark arbitrary orders as paid. Every
    payload is verified before any database write; anything that fails
    verification is rejected and nothing is changed.

    Always returns 200 once the payload is at least well-formed, even if no
    matching payment was found, so Paymob doesn't retry forever on a stale
    webhook - the mismatch is logged for investigation instead.
    """
    payload = request.get_json(silent=True) or {}
    transaction_obj = payload.get('obj', {})
    received_hmac = request.args.get('hmac', '')

    if not verify_hmac(transaction_obj, received_hmac):
        current_app.logger.warning('Rejected Paymob webhook with invalid HMAC')
        return api_response(False, {}, 'invalid signature', 401)

    payment = PaymentService.process_paymob_webhook(transaction_obj)
    if not payment:
        current_app.logger.warning(
            f"Paymob webhook for unknown order.id={transaction_obj.get('order', {}).get('id')}"
        )

    return api_response(True, {})


@bp.route('/order/<int:order_id>/status', methods=['GET'])
@login_required
@limiter.limit(RATE_LIMITS['payments'])
def get_order_payment_status(order_id: int) -> tuple:
    """Return the current (server-verified) payment status for an order.

    Used by the post-payment redirect page to show a real result instead of
    trusting the redirect's own query params, which the customer's browser
    could edit.
    """
    order = OrderService.get_order(order_id)
    if not order:
        return api_response(False, {}, 'Order not found', 404)

    user = g.current_user
    if order.user_id != user.id and not user.is_admin:
        return api_response(False, {}, 'Forbidden', 403)

    payment = PaymentService.get_payment_by_order(order_id)
    if not payment:
        return api_response(True, {'payment_status': 'not_started'})

    tracking = tracking_service.mark_client_purchase_notified(order_id, user.id)

    return api_response(True, {
        'payment_status': payment.payment_status,
        'payment_method': payment.payment_method,
        'tracking': tracking,
    })
