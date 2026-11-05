"""Payment service for managing order payments."""
from typing import Optional, Dict
import uuid
from datetime import datetime

from flask import current_app

from app.extensions import db
from app.models.models import Payment, PaymentAttempt, Order
from app.services import paymob_service
from app.services import tracking_service
from app.services.paymob_service import PaymobError, PAYMOB_TOKEN_LIFETIME_SECONDS


class PaymentService:
    """Service layer for payment operations."""

    @staticmethod
    def generate_transaction_id() -> str:
        """Generate a unique transaction ID using UUID."""
        return str(uuid.uuid4())

    @staticmethod
    def create_payment(
        order_id: int,
        payment_method: str,
    ) -> Optional[Payment]:
        """Create (or reuse) a payment record for an order.

        SECURITY: the payment amount is never taken from caller input — it is
        always order.total_amount, computed server-side when the order was
        created. This prevents a client from recording a payment for less
        than what the order actually costs.

        Reuses the existing Payment row if one is already pending or failed
        for this order - e.g. a card payment via Paymob failed and the
        order is now being recorded as cash on delivery instead. Payment
        rows are one-per-order (see Payment.order_id's unique constraint),
        so this is an update, not a second row.

        Args:
            order_id: The ID of the order.
            payment_method: The payment method (e.g., 'cash', 'paymob_card').

        Returns:
            Payment: The created (or reused) payment object.

        Raises:
            ValueError: If order not found, order was cancelled, or an
                existing payment for this order is already completed,
                cancelled, or flagged manual_refund_required (i.e. it's
                concluded or needs human resolution, not just retryable).
        """
        order = Order.query.get(order_id)
        if not order:
            raise ValueError(f'Order {order_id} not found')

        if order.status == 'cancelled':
            raise ValueError(f'Order {order_id} has been cancelled and can no longer be paid for')

        # Lock the order row so a double-click/concurrent request for the
        # same order is serialized rather than racing to both decide
        # there's "no existing payment" and both try to insert one
        # (which order_id's unique constraint would only catch as a
        # confusing IntegrityError, not a clean ValueError).
        order = Order.query.filter_by(id=order.id).with_for_update().first()
        payment = Payment.query.filter_by(order_id=order_id).with_for_update().first()

        if payment and payment.payment_status not in ('pending', 'failed'):
            raise ValueError(f'Payment for order {order_id} is already {payment.payment_status}')

        transaction_id = PaymentService.generate_transaction_id()
        if payment:
            payment.payment_method = payment_method
            payment.payment_status = 'pending'
            payment.transaction_id = transaction_id
            payment.amount = order.total_amount
            payment.paymob_order_id = None
            payment.paymob_iframe_url = None
            payment.paymob_token_issued_at = None
        else:
            payment = Payment(
                order_id=order_id,
                amount=order.total_amount,
                payment_method=payment_method,
                payment_status='pending',
                transaction_id=transaction_id,
            )
        db.session.add(payment)
        db.session.commit()

        if payment_method == 'cash':
            # Cash on delivery has no further gateway confirmation coming -
            # this is the moment the purchase is genuinely confirmed. See
            # tracking_service.report_purchase_if_new for the idempotency
            # guard (safe to call unconditionally, including on retries).
            try:
                tracking_service.report_purchase_if_new(order_id)
            except Exception as e:
                # Belt-and-suspenders on top of report_purchase_if_new's own
                # internal safety: tracking must never affect the payment
                # that already succeeded above.
                current_app.logger.error(f'Purchase tracking failed for order {order_id}: {e}')

        return payment

    @staticmethod
    def get_payment(payment_id: int) -> Optional[Payment]:
        """Get a payment by ID."""
        return Payment.query.get(payment_id)

    @staticmethod
    def get_payment_by_order(order_id: int) -> Optional[Payment]:
        """Get a payment by order ID."""
        return Payment.query.filter_by(order_id=order_id).first()

    @staticmethod
    def get_payment_by_paymob_order_id(paymob_order_id: str) -> Optional[Payment]:
        """Get a payment by Paymob's own order id (used to match webhooks)."""
        payment = Payment.query.filter_by(paymob_order_id=str(paymob_order_id)).first()
        if payment:
            return payment
        attempt = PaymentAttempt.query.filter_by(paymob_order_id=str(paymob_order_id)).first()
        return attempt.payment if attempt else None

    @staticmethod
    def update_payment_status(payment: Payment, status: str) -> Payment:
        """Update the payment status (admin only, enforced at the route layer)."""
        payment.payment_status = status
        payment.payment_date = datetime.utcnow()
        db.session.add(payment)
        db.session.commit()
        return payment

    @staticmethod
    def initiate_paymob_payment(order: Order, user) -> Dict[str, str]:
        """Start (or resume) a Paymob card/wallet payment for an order.

        Reuses the existing Payment row if one is already pending for this
        order (e.g. the customer re-opens the iframe after closing it),
        rather than raising like create_payment() does - a customer must be
        able to retry a failed/abandoned payment attempt.

        LOCKING / IDEMPOTENCY: the order row is locked (SELECT ... FOR
        UPDATE) for the duration of this call, so two near-simultaneous
        requests for the same order (double-click, two open tabs, a retried
        request) are serialized rather than racing each other to register
        separate orders with Paymob. Within that lock, if a still-valid
        cached Paymob session already exists (see paymob_iframe_url /
        paymob_token_issued_at), it's returned as-is instead of calling
        Paymob again - so a duplicate request never creates a second,
        redundant Paymob order for work that's already in flight.

        Raises:
            ValueError: if a payment already exists and is not pending
                (i.e. it already succeeded - don't charge again), the
                order doesn't belong to this user, or the order has been
                cancelled.
            PaymobError: if any Paymob API call fails.
        """
        if order.user_id != user.id:
            raise ValueError('This order does not belong to you')

        if order.status == 'cancelled':
            raise ValueError(f'Order {order.id} has been cancelled and can no longer be paid for')

        if not order.total_amount or order.total_amount <= 0:
            # e.g. a 100% coupon: there is nothing to charge, and Paymob
            # rejects a zero amount (the customer would see a 502).
            raise ValueError('This order has nothing to pay online (total is 0). Please choose cash on delivery.')

        # Re-fetch with a row lock: any concurrent call for this same
        # order (from here or from a second request racing in) blocks
        # until this transaction commits or rolls back.
        order = Order.query.filter_by(id=order.id).with_for_update().first()
        payment = Payment.query.filter_by(order_id=order.id).with_for_update().first()

        if payment and payment.payment_status not in ('pending', 'failed'):
            raise ValueError(f'Payment for order {order.id} is already {payment.payment_status}')

        if payment and payment.payment_status == 'pending' and payment.paymob_iframe_url and payment.paymob_token_issued_at:
            age_seconds = (datetime.utcnow() - payment.paymob_token_issued_at).total_seconds()
            if age_seconds < PAYMOB_TOKEN_LIFETIME_SECONDS:
                # A duplicate/concurrent/rapid-retry request for the same
                # order - the existing session is still good, so hand
                # back the same iframe_url rather than registering
                # another order with Paymob for no reason.
                return {'iframe_url': payment.paymob_iframe_url}

        result = paymob_service.initiate_payment(order, user)
        issued_at = datetime.utcnow()

        if payment:
            payment.payment_method = 'paymob_card'
            payment.payment_status = 'pending'
            payment.paymob_order_id = result['paymob_order_id']
            payment.paymob_iframe_url = result['iframe_url']
            payment.paymob_token_issued_at = issued_at
            payment.amount = order.total_amount
        else:
            payment = Payment(
                order_id=order.id,
                amount=order.total_amount,
                payment_method='paymob_card',
                payment_status='pending',
                paymob_order_id=result['paymob_order_id'],
                paymob_iframe_url=result['iframe_url'],
                paymob_token_issued_at=issued_at,
            )
        db.session.add(payment)
        db.session.commit()

        attempt = PaymentAttempt(
            order_id=order.id,
            payment_id=payment.id,
            paymob_order_id=result['paymob_order_id'],
            amount=order.total_amount,
            status='pending',
        )
        db.session.add(attempt)
        db.session.commit()

        return {'iframe_url': result['iframe_url']}

    @staticmethod
    def process_paymob_webhook(transaction_obj: Dict) -> Optional[Payment]:
        """Apply a verified Paymob transaction-processed webhook to our records.

        HMAC verification happens in the route before this is ever called -
        this function additionally cross-checks that the transaction's own
        reported details (amount, currency, integration) actually match
        what we expect for the Payment it claims to be about, rather than
        trusting a signed-but-unverified-in-substance payload. A valid HMAC
        only proves the payload wasn't tampered with in transit; it doesn't
        prove the payload describes the transaction we think it does.

        Idempotent: if this transaction_id was already processed, it's a
        no-op (Paymob retries webhooks, so this must be safe to call more
        than once for the same transaction).

        Returns the updated Payment, or None if no matching payment/order
        could be found (e.g. a stale/foreign webhook) or if the webhook's
        own reported details don't match what we expect - callers should
        still return 200 to Paymob in either case so it stops retrying, but
        should log it for investigation. On a mismatch, payment_status is
        left exactly as it was: not "completed" (that would be trusting an
        unverified claim), and not "failed" either (we don't actually know
        what happened - a mismatch could be a data anomaly on a genuine
        success, not proof the payment failed). A human needs to look at it.
        """
        paymob_order_id = str(transaction_obj.get('order', {}).get('id', ''))
        transaction_id = str(transaction_obj.get('id', ''))

        # STRICT TYPE CHECK: bool(x) is true for any non-empty value,
        # including the string "false" - so a webhook payload where
        # success arrives as something other than a real JSON boolean
        # (a string, a number, null) must be treated as invalid rather
        # than silently coerced one way or the other.
        success = transaction_obj.get('success')
        if not isinstance(success, bool):
            current_app.logger.error(
                f"Paymob webhook rejected: 'success' field is {type(success).__name__} "
                f"({success!r}), not a boolean - transaction_id={transaction_id}"
            )
            return None

        attempt = PaymentAttempt.query.filter_by(paymob_order_id=paymob_order_id).first()
        payment = attempt.payment if attempt else PaymentService.get_payment_by_paymob_order_id(paymob_order_id)
        if not payment:
            return None

        if attempt and payment.paymob_order_id != paymob_order_id:
            if success:
                attempt.status = 'manual_refund_required'
                attempt.transaction_id = transaction_id
                attempt.processed_at = datetime.utcnow()
                db.session.add(attempt)
                db.session.commit()
                current_app.logger.error(
                    f'Late successful Paymob attempt {paymob_order_id} for order {payment.order_id}; '
                    'marked for manual refund instead of attaching it to a newer attempt.'
                )
            return payment

        if payment.transaction_id == transaction_id and payment.payment_status in ('completed', 'failed', 'manual_refund_required'):
            # Already processed this exact transaction - no-op.
            return payment

        if payment.payment_status == 'manual_refund_required':
            # Already flagged for manual attention - never auto-overwrite
            # that (even from a webhook with a different transaction_id
            # than the one that originally triggered it). A human needs
            # to resolve this via the admin panel, not another webhook.
            current_app.logger.error(
                f'Paymob webhook received for payment {payment.id} (order {payment.order_id}) '
                f'which is already flagged manual_refund_required - ignoring, no auto-resolution.'
            )
            return payment

        if payment.payment_status == 'completed':
            # A DIFFERENT transaction arriving after the payment already
            # succeeded (e.g. an earlier declined attempt whose webhook was
            # delayed, or a refund/void callback). Never overwrite a
            # completed payment: flipping it to 'failed' would let the
            # customer pay a second time for an order that is already paid.
            # If it claims success too, that may be a genuine second charge
            # - log it loudly so a human checks the Paymob dashboard.
            if success:
                current_app.logger.error(
                    f'Paymob reported a SECOND successful transaction {transaction_id} for payment '
                    f'{payment.id} (order {payment.order_id}) which is already completed with '
                    f'transaction {payment.transaction_id} - possible double charge, check Paymob.'
                )
            else:
                current_app.logger.warning(
                    f'Ignoring non-success webhook (transaction {transaction_id}) for already-completed '
                    f'payment {payment.id} (order {payment.order_id}).'
                )
            return payment

        # Cross-check the webhook's own reported transaction details
        # against what we actually expect for this payment, rather than
        # trusting amount/currency/integration purely because the HMAC
        # matched. Every check logs specifically on failure so a mismatch
        # is diagnosable, not just silently dropped.
        expected_amount_cents = int(round(payment.amount * 100))
        reported_amount_cents = transaction_obj.get('amount_cents')
        if reported_amount_cents != expected_amount_cents:
            current_app.logger.error(
                f'Paymob webhook amount mismatch for payment {payment.id} '
                f'(order {payment.order_id}): expected {expected_amount_cents} cents, '
                f'webhook reported {reported_amount_cents!r} - rejecting, not marking completed'
            )
            return None

        reported_currency = transaction_obj.get('currency')
        if reported_currency != 'EGP':
            current_app.logger.error(
                f'Paymob webhook currency mismatch for payment {payment.id}: '
                f"expected 'EGP', webhook reported {reported_currency!r} - rejecting"
            )
            return None

        expected_integration_id = current_app.config.get('PAYMOB_INTEGRATION_ID')
        reported_integration_id = transaction_obj.get('integration_id')
        # Compare as strings: Paymob may report this as an int while our
        # config (sourced from an env var) is always a str - a naive
        # int-vs-str comparison would false-positive as a mismatch.
        if expected_integration_id is None or str(reported_integration_id) != str(expected_integration_id):
            current_app.logger.error(
                f'Paymob webhook integration_id mismatch for payment {payment.id}: '
                f'expected {expected_integration_id!r}, webhook reported '
                f'{reported_integration_id!r} - rejecting'
            )
            return None

        if payment.payment_status == 'cancelled':
            # The order (and this payment along with it) was already
            # cancelled - see OrderService.update_order_status - before
            # this webhook arrived. If Paymob is now reporting success,
            # money was actually captured for an order we've told the
            # customer won't be fulfilled. Neither "completed" (contradicts
            # the cancellation) nor silently staying "cancelled" (hides
            # that a real charge went through) is correct here - this
            # needs a human to actually issue a refund.
            if success:
                payment.payment_status = 'manual_refund_required'
                payment.transaction_id = transaction_id
                payment.payment_date = datetime.utcnow()
                db.session.add(payment)
                db.session.commit()
                current_app.logger.error(
                    f'Paymob reported SUCCESS for payment {payment.id} (order {payment.order_id}) '
                    f'after the order was already cancelled - marked manual_refund_required. '
                    f'A real charge needs to be refunded to the customer.'
                )
            # A failure webhook for an already-cancelled payment is not a
            # conflict - it's consistent, so it's left as 'cancelled'
            # rather than overwritten to 'failed'.
            return payment

        payment.payment_status = 'completed' if success else 'failed'
        payment.transaction_id = transaction_id
        payment.payment_date = datetime.utcnow()
        db.session.add(payment)
        if attempt:
            attempt.status = payment.payment_status
            attempt.transaction_id = transaction_id
            attempt.processed_at = datetime.utcnow()
            db.session.add(attempt)

        if success:
            order = Order.query.get(payment.order_id)
            if order and order.status == 'pending':
                order.status = 'processing'
                db.session.add(order)

        db.session.commit()

        if success:
            try:
                tracking_service.report_purchase_if_new(payment.order_id)
            except Exception as e:
                current_app.logger.error(f'Purchase tracking failed for order {payment.order_id}: {e}')

        return payment
