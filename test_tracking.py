"""Tests for the conversion-tracking system: app/services/tracking_service.py
and its integration points in payment_service.py / order_service.py.

Covers the FINAL PAYMENT-READINESS + TRACKING requirements specifically:
- Purchase is reported exactly once server-side per order, regardless of
  how many times a webhook is retried or create_payment is called.
- Payment failure and order cancellation never produce a Purchase.
- The client-side "should I fire my pixel" flag is also one-time, checked
  independently of the server-side report (a page refresh must never
  cause a second client-side fire even if the server already reported
  the event via webhook before the page ever loaded).
- UTM/attribution fields are stored with the order as given.

Meta CAPI / GA4 Measurement Protocol HTTP calls are mocked throughout -
these tests exercise our own idempotency and data-handling logic, not
Meta/Google's live APIs.
"""
from unittest.mock import patch

import pytest

from app import create_app
from app.extensions import db
from app.models.models import User, Product, Order, Payment, ShippingAddress
from app.services.payment_service import PaymentService
from app.services.order_service import OrderService
from app.services import tracking_service


@pytest.fixture
def reset_db():
    """Shadow conftest.py's autouse reset_db - see test_orders.py."""
    yield


@pytest.fixture
def app(tmp_path):
    db_path = (tmp_path / 'test.db').resolve()

    class TestConfig:
        TESTING = True
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_path.as_posix()}'
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        SECRET_KEY = 'test'
        JWT_SECRET_KEY = 'test'
        PAYMOB_INTEGRATION_ID = '54321'
        PAYMOB_HMAC_SECRET = 'test-hmac-secret'
        PAYMOB_API_KEY = 'test-api-key'
        PAYMOB_IFRAME_ID = 'test-iframe-id'
        # Deliberately unset: Meta/GA4 aren't configured in tests, which
        # exercises the "not configured - skip gracefully" path too.
        META_PIXEL_ID = ''
        META_ACCESS_TOKEN = ''
        GA4_MEASUREMENT_ID = ''
        GA4_API_SECRET = ''

    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
    yield app


def make_order(app, total_amount=100.0, status='pending', attribution=None):
    with app.app_context():
        user = User(username='cust', email='cust@example.com', password_hash='x')
        db.session.add(user)
        db.session.commit()
        addr = ShippingAddress(user_id=user.id, city='C', full_address='a', phone_number='1')
        db.session.add(addr)
        db.session.commit()
        product = Product(name='P', price=total_amount, category='men sunglasses',
                           image_file='i.png', colors='black', stock_quantity=10)
        db.session.add(product)
        db.session.commit()

        order = OrderService.create_order(
            user_id=user.id,
            address_id=addr.id,
            items=[{'product_id': product.id, 'quantity': 1, 'prescription_id': None, 'lens_type': ''}],
            attribution=attribution,
        )
        if status != 'pending':
            order.status = status
            db.session.add(order)
            db.session.commit()
        return order.id, user.id


def webhook_payload(paymob_order_id, transaction_id='txn-1', amount_cents=10000,
                     currency='EGP', integration_id='54321', success=True):
    return {
        'id': transaction_id,
        'amount_cents': amount_cents,
        'currency': currency,
        'integration_id': integration_id,
        'success': success,
        'order': {'id': paymob_order_id},
    }


# =======================================================================
# UTM / attribution stored with the order
# =======================================================================

def test_utm_parameters_saved_with_order(app):
    attribution = {
        'utm_source': 'facebook', 'utm_medium': 'cpc', 'utm_campaign': 'summer_sale',
        'utm_content': 'ad_variant_a', 'utm_term': 'sunglasses',
        'fbp': 'fb.1.111.aaa', 'fbc': 'fb.1.222.bbb', 'ga4_client_id': 'GA1.2.123.456',
    }
    order_id, _ = make_order(app, attribution=attribution)
    with app.app_context():
        order = Order.query.get(order_id)
        assert order.utm_source == 'facebook'
        assert order.utm_medium == 'cpc'
        assert order.utm_campaign == 'summer_sale'
        assert order.utm_content == 'ad_variant_a'
        assert order.utm_term == 'sunglasses'
        assert order.fbp == 'fb.1.111.aaa'
        assert order.fbc == 'fb.1.222.bbb'
        assert order.ga4_client_id == 'GA1.2.123.456'


def test_order_creation_succeeds_with_no_attribution_at_all(app):
    """Every attribution field is optional - a direct-traffic order (no
    UTM, no fbclid, ad blocker) must still place successfully."""
    order_id, _ = make_order(app, attribution=None)
    with app.app_context():
        order = Order.query.get(order_id)
        assert order.utm_source is None
        assert order.fbp is None
        assert order.ga4_client_id is None


def test_partial_attribution_is_stored_as_given(app):
    """Only some fields present (e.g. UTM but no fbclid) - the rest stay
    null rather than blocking order creation."""
    order_id, _ = make_order(app, attribution={'utm_source': 'google', 'utm_medium': 'organic'})
    with app.app_context():
        order = Order.query.get(order_id)
        assert order.utm_source == 'google'
        assert order.utm_campaign is None
        assert order.fbp is None


# =======================================================================
# Server-side Purchase idempotency (report_purchase_if_new)
# =======================================================================

def test_purchase_reported_exactly_once_for_cash_order(app):
    order_id, _ = make_order(app, total_amount=100.0)
    with app.app_context():
        with patch('app.services.tracking_service._send_meta_purchase') as mock_meta, \
             patch('app.services.tracking_service._send_ga4_purchase') as mock_ga4:
            PaymentService.create_payment(order_id, 'cash')

            assert mock_meta.call_count == 1
            assert mock_ga4.call_count == 1

            order = Order.query.get(order_id)
            assert order.purchase_tracked_at is not None


def test_calling_report_purchase_if_new_twice_only_sends_once(app):
    """Direct test of the idempotency guard itself, independent of which
    caller invokes it - covers duplicate webhook delivery."""
    order_id, _ = make_order(app, total_amount=100.0)
    with app.app_context():
        with patch('app.services.tracking_service._send_meta_purchase') as mock_meta:
            first = tracking_service.report_purchase_if_new(order_id)
            second = tracking_service.report_purchase_if_new(order_id)

            assert first is True   # this call actually reported it
            assert second is False  # already reported, no-op
            assert mock_meta.call_count == 1


def test_duplicate_paymob_webhook_does_not_double_report_purchase(app):
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order = Order.query.get(order_id)
        user = User.query.get(user_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://x', 'paymob_order_id': 'pm-1'}):
            PaymentService.initiate_paymob_payment(order, user)

        with patch('app.services.tracking_service._send_meta_purchase') as mock_meta:
            payload = webhook_payload('pm-1', transaction_id='txn-dup', amount_cents=10000, success=True)
            PaymentService.process_paymob_webhook(payload)
            # Paymob retries the identical webhook.
            PaymentService.process_paymob_webhook(payload)

            assert mock_meta.call_count == 1


def test_payment_failure_does_not_report_purchase(app):
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order = Order.query.get(order_id)
        user = User.query.get(user_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://x', 'paymob_order_id': 'pm-2'}):
            PaymentService.initiate_paymob_payment(order, user)

        with patch('app.services.tracking_service._send_meta_purchase') as mock_meta:
            PaymentService.process_paymob_webhook(
                webhook_payload('pm-2', amount_cents=10000, success=False)
            )
            assert mock_meta.call_count == 0

        order = Order.query.get(order_id)
        assert order.purchase_tracked_at is None


def test_cancelled_order_never_reports_purchase_even_with_later_success_webhook(app):
    """The order is cancelled before any payment success - a webhook
    reporting success afterward must not be treated as a genuine Purchase
    (it becomes manual_refund_required instead - see test_payments.py)."""
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order = Order.query.get(order_id)
        user = User.query.get(user_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://x', 'paymob_order_id': 'pm-3'}):
            PaymentService.initiate_paymob_payment(order, user)

        order = Order.query.get(order_id)
        OrderService.update_order_status(order, 'cancelled')

        with patch('app.services.tracking_service._send_meta_purchase') as mock_meta:
            PaymentService.process_paymob_webhook(
                webhook_payload('pm-3', amount_cents=10000, success=True)
            )
            assert mock_meta.call_count == 0

        order = Order.query.get(order_id)
        assert order.purchase_tracked_at is None


def test_order_creation_itself_never_reports_purchase(app):
    """Placing an order is not a purchase confirmation - only a
    completed payment (or recorded cash payment) is. Nothing about
    OrderService.create_order should touch purchase_tracked_at."""
    order_id, _ = make_order(app, total_amount=100.0)
    with app.app_context():
        order = Order.query.get(order_id)
        assert order.purchase_tracked_at is None
        assert order.purchase_client_notified_at is None


# =======================================================================
# Client-side "should_fire" idempotency (mark_client_purchase_notified)
# =======================================================================

def test_client_should_fire_true_exactly_once_then_false_on_refresh(app):
    order_id, _ = make_order(app, total_amount=100.0)
    with app.app_context():
        user_id = Order.query.get(order_id).user_id
        PaymentService.create_payment(order_id, 'cash')

        first = tracking_service.mark_client_purchase_notified(order_id, user_id)
        assert first['paid'] is True
        assert first['should_fire'] is True

        # Customer refreshes payment-result.html (or, for cash, somehow
        # calls the status endpoint again).
        second = tracking_service.mark_client_purchase_notified(order_id, user_id)
        assert second['paid'] is True
        assert second['should_fire'] is False


def test_client_should_fire_false_when_not_yet_paid(app):
    order_id, _ = make_order(app, total_amount=100.0)
    with app.app_context():
        user_id = Order.query.get(order_id).user_id
        # No payment created at all yet.
        result = tracking_service.mark_client_purchase_notified(order_id, user_id)
        assert result['paid'] is False
        assert result['should_fire'] is False


def test_client_should_fire_independent_of_which_party_reports_first(app):
    """If the webhook (server-side) already reported the purchase before
    the customer's browser ever loads the result page, the client-side
    flag must still correctly say 'yes, fire' the first time the browser
    actually checks - the two guards are intentionally separate."""
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order = Order.query.get(order_id)
        user = User.query.get(user_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://x', 'paymob_order_id': 'pm-4'}):
            PaymentService.initiate_paymob_payment(order, user)

        with patch('app.services.tracking_service._send_meta_purchase'):
            PaymentService.process_paymob_webhook(
                webhook_payload('pm-4', amount_cents=10000, success=True)
            )

        order = Order.query.get(order_id)
        assert order.purchase_tracked_at is not None  # server already reported
        assert order.purchase_client_notified_at is None  # client hasn't checked yet

        result = tracking_service.mark_client_purchase_notified(order_id, user_id)
        assert result['should_fire'] is True  # still fires for the browser, once

        second = tracking_service.mark_client_purchase_notified(order_id, user_id)
        assert second['should_fire'] is False


def test_client_check_rejects_wrong_user(app):
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        other = User(username='other', email='other@example.com', password_hash='x')
        db.session.add(other)
        db.session.commit()
        result = tracking_service.mark_client_purchase_notified(order_id, other.id)
        assert result is None
