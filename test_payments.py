"""Tests for the Paymob payment security hardening:
- webhook amount/currency/integration_id cross-verification
- strict boolean typing on the webhook's 'success' field
- initiate_paymob_payment locking/idempotency (no duplicate Paymob orders
  on double-click/concurrent requests)
- the cancelled-order-then-late-success-webhook policy
  (manual_refund_required)

Paymob's own HTTP API is mocked throughout (paymob_service.initiate_payment)
- these tests exercise PaymentService's own logic, not Paymob's live API.
"""
import itertools
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app import create_app
from app.extensions import db
from app.models.models import User, Product, Order, Payment, ShippingAddress
from app.services.payment_service import PaymentService


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

    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
    yield app


_order_counter = itertools.count(1)


def make_order(app, total_amount=100.0, status='pending'):
    """Create a user + address + order, return (order_id, user_id).
    Each call creates its own user so it can be called more than once
    per test without hitting the UNIQUE constraints on username/email."""
    n = next(_order_counter)
    with app.app_context():
        user = User(username=f'cust{n}', email=f'cust{n}@example.com', password_hash='x')
        db.session.add(user)
        db.session.commit()
        addr = ShippingAddress(user_id=user.id, city='C', full_address='a', phone_number='1')
        db.session.add(addr)
        db.session.commit()
        order = Order(user_id=user.id, address_id=addr.id, total_amount=total_amount, status=status)
        db.session.add(order)
        db.session.commit()
        return order.id, user.id


def get_order_and_user(app, order_id, user_id):
    order = Order.query.get(order_id)
    user = User.query.get(user_id)
    return order, user


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
# Webhook: amount / currency / integration_id verification
# =======================================================================

def test_webhook_wrong_amount_rejected(app):
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order, user = get_order_and_user(app, order_id, user_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://x', 'paymob_order_id': 'pm-1'}):
            PaymentService.initiate_paymob_payment(order, user)

        # Order total is 100.0 EGP -> expected 10000 cents. Webhook reports
        # a different amount entirely.
        result = PaymentService.process_paymob_webhook(
            webhook_payload('pm-1', amount_cents=500)  # 5.00 EGP instead of 100.00
        )
        assert result is None
        payment = Payment.query.filter_by(order_id=order_id).first()
        assert payment.payment_status == 'pending'  # untouched, not completed


def test_webhook_correct_amount_accepted(app):
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order, user = get_order_and_user(app, order_id, user_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://x', 'paymob_order_id': 'pm-2'}):
            PaymentService.initiate_paymob_payment(order, user)

        result = PaymentService.process_paymob_webhook(webhook_payload('pm-2', amount_cents=10000))
        assert result is not None
        assert result.payment_status == 'completed'


def test_webhook_wrong_currency_rejected(app):
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order, user = get_order_and_user(app, order_id, user_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://x', 'paymob_order_id': 'pm-3'}):
            PaymentService.initiate_paymob_payment(order, user)

        result = PaymentService.process_paymob_webhook(
            webhook_payload('pm-3', amount_cents=10000, currency='USD')
        )
        assert result is None
        payment = Payment.query.filter_by(order_id=order_id).first()
        assert payment.payment_status == 'pending'


def test_webhook_wrong_integration_id_rejected(app):
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order, user = get_order_and_user(app, order_id, user_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://x', 'paymob_order_id': 'pm-4'}):
            PaymentService.initiate_paymob_payment(order, user)

        # Configured PAYMOB_INTEGRATION_ID is '54321' - webhook reports a
        # different one (e.g. from a different Paymob integration/account).
        result = PaymentService.process_paymob_webhook(
            webhook_payload('pm-4', amount_cents=10000, integration_id='99999')
        )
        assert result is None
        payment = Payment.query.filter_by(order_id=order_id).first()
        assert payment.payment_status == 'pending'


def test_webhook_integration_id_int_vs_str_does_not_false_positive(app):
    """Paymob may report integration_id as a JSON number while our config
    (from an env var) is always a string - these must still match."""
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order, user = get_order_and_user(app, order_id, user_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://x', 'paymob_order_id': 'pm-5'}):
            PaymentService.initiate_paymob_payment(order, user)

        result = PaymentService.process_paymob_webhook(
            webhook_payload('pm-5', amount_cents=10000, integration_id=54321)  # int, not str
        )
        assert result is not None
        assert result.payment_status == 'completed'


# =======================================================================
# Webhook: strict success typing
# =======================================================================

def test_webhook_success_as_string_false_is_rejected_not_treated_as_true(app):
    """bool('false') is True in Python - this must not silently mark the
    payment completed."""
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order, user = get_order_and_user(app, order_id, user_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://x', 'paymob_order_id': 'pm-6'}):
            PaymentService.initiate_paymob_payment(order, user)

        payload = webhook_payload('pm-6', amount_cents=10000, success='false')
        result = PaymentService.process_paymob_webhook(payload)
        assert result is None
        payment = Payment.query.filter_by(order_id=order_id).first()
        assert payment.payment_status == 'pending'


def test_webhook_success_as_int_is_rejected(app):
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order, user = get_order_and_user(app, order_id, user_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://x', 'paymob_order_id': 'pm-7'}):
            PaymentService.initiate_paymob_payment(order, user)

        payload = webhook_payload('pm-7', amount_cents=10000, success=1)
        result = PaymentService.process_paymob_webhook(payload)
        assert result is None


# =======================================================================
# Payment success / failure (the normal, correctly-verified paths)
# =======================================================================

def test_payment_success_marks_completed_and_advances_order(app):
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order, user = get_order_and_user(app, order_id, user_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://x', 'paymob_order_id': 'pm-8'}):
            PaymentService.initiate_paymob_payment(order, user)

        result = PaymentService.process_paymob_webhook(
            webhook_payload('pm-8', amount_cents=10000, success=True)
        )
        assert result.payment_status == 'completed'
        order = Order.query.get(order_id)
        assert order.status == 'processing'


def test_payment_failure_marks_failed_and_leaves_order_pending(app):
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order, user = get_order_and_user(app, order_id, user_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://x', 'paymob_order_id': 'pm-9'}):
            PaymentService.initiate_paymob_payment(order, user)

        result = PaymentService.process_paymob_webhook(
            webhook_payload('pm-9', amount_cents=10000, success=False)
        )
        assert result.payment_status == 'failed'
        order = Order.query.get(order_id)
        assert order.status == 'pending'  # unchanged


# =======================================================================
# Duplicate webhook (idempotency)
# =======================================================================

def test_duplicate_webhook_same_transaction_id_is_a_noop(app):
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order, user = get_order_and_user(app, order_id, user_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://x', 'paymob_order_id': 'pm-10'}):
            PaymentService.initiate_paymob_payment(order, user)

        payload = webhook_payload('pm-10', transaction_id='txn-dup', amount_cents=10000, success=True)
        first = PaymentService.process_paymob_webhook(payload)
        assert first.payment_status == 'completed'
        first_date = first.payment_date

        # Paymob retries the exact same webhook.
        second = PaymentService.process_paymob_webhook(payload)
        assert second.payment_status == 'completed'
        assert second.payment_date == first_date  # untouched, proves it was a no-op


# =======================================================================
# Duplicate payment initiation (locking / idempotency)
# =======================================================================

def test_duplicate_initiation_reuses_cached_session_no_second_paymob_call(app):
    """Simulates a double-click: two initiate calls for the same order in
    quick succession must not register two separate Paymob orders."""
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order, user = get_order_and_user(app, order_id, user_id)

        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://paymob/first', 'paymob_order_id': 'pm-11'}) as mock_initiate:
            result1 = PaymentService.initiate_paymob_payment(order, user)
            assert mock_initiate.call_count == 1

            # "Double-click": call again immediately, order object re-fetched
            # fresh each time exactly as the route does.
            order = Order.query.get(order_id)
            result2 = PaymentService.initiate_paymob_payment(order, user)

            # Paymob's API must NOT have been called a second time.
            assert mock_initiate.call_count == 1
            assert result1['iframe_url'] == result2['iframe_url'] == 'https://paymob/first'

        payments = Payment.query.filter_by(order_id=order_id).all()
        assert len(payments) == 1  # exactly one Payment row, not two


def test_initiation_after_token_expiry_calls_paymob_again(app):
    """A genuinely stale session (past PAYMOB_TOKEN_LIFETIME_SECONDS) must
    get a fresh Paymob order - this is not the double-click case."""
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order, user = get_order_and_user(app, order_id, user_id)

        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://paymob/first', 'paymob_order_id': 'pm-12'}):
            PaymentService.initiate_paymob_payment(order, user)

        # Simulate the cached token having been issued over an hour ago.
        payment = Payment.query.filter_by(order_id=order_id).first()
        payment.paymob_token_issued_at = datetime.utcnow() - timedelta(hours=2)
        db.session.add(payment)
        db.session.commit()

        order = Order.query.get(order_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://paymob/second', 'paymob_order_id': 'pm-12-b'}) as mock_initiate:
            result = PaymentService.initiate_paymob_payment(order, user)
            assert mock_initiate.call_count == 1
            assert result['iframe_url'] == 'https://paymob/second'


def test_retry_after_failed_payment_gets_a_fresh_session_not_the_stale_one(app):
    """A 'failed' payment already concluded - retrying must not silently
    hand back the old (failed) session's iframe_url."""
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order, user = get_order_and_user(app, order_id, user_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://paymob/failed-attempt', 'paymob_order_id': 'pm-13'}):
            PaymentService.initiate_paymob_payment(order, user)

        payment = Payment.query.filter_by(order_id=order_id).first()
        payment.payment_status = 'failed'
        db.session.add(payment)
        db.session.commit()

        order = Order.query.get(order_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://paymob/retry', 'paymob_order_id': 'pm-13-b'}) as mock_initiate:
            result = PaymentService.initiate_paymob_payment(order, user)
            assert mock_initiate.call_count == 1
            assert result['iframe_url'] == 'https://paymob/retry'


def test_paymob_order_id_is_unique_at_db_level(app):
    """DB-level backstop: two different Payment rows must never share the
    same paymob_order_id."""
    order1_id, user1_id = make_order(app, total_amount=50.0)
    order2_id, user2_id = make_order(app, total_amount=75.0)
    with app.app_context():
        p1 = Payment(order_id=order1_id, amount=50.0, payment_method='paymob_card',
                     payment_status='pending', paymob_order_id='dup-id')
        db.session.add(p1)
        db.session.commit()

        p2 = Payment(order_id=order2_id, amount=75.0, payment_method='paymob_card',
                     payment_status='pending', paymob_order_id='dup-id')
        db.session.add(p2)
        with pytest.raises(Exception):  # IntegrityError from the unique constraint
            db.session.commit()
        db.session.rollback()


# =======================================================================
# Cancelled order + later successful webhook
# =======================================================================

def test_cancelled_order_then_success_webhook_becomes_manual_refund_required(app):
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order, user = get_order_and_user(app, order_id, user_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://x', 'paymob_order_id': 'pm-14'}):
            PaymentService.initiate_paymob_payment(order, user)

        # Admin cancels the order while the Paymob payment is still
        # pending - cascades to cancel the payment too (see
        # OrderService.update_order_status).
        from app.services.order_service import OrderService
        order = Order.query.get(order_id)
        OrderService.update_order_status(order, 'cancelled')
        payment = Payment.query.filter_by(order_id=order_id).first()
        assert payment.payment_status == 'cancelled'

        # Paymob's webhook arrives late, reporting success anyway.
        result = PaymentService.process_paymob_webhook(
            webhook_payload('pm-14', amount_cents=10000, success=True)
        )
        assert result.payment_status == 'manual_refund_required'

        # Order status itself must stay cancelled - not silently
        # resurrected to 'processing'.
        order = Order.query.get(order_id)
        assert order.status == 'cancelled'


def test_cancelled_order_then_failure_webhook_stays_cancelled(app):
    """A failure webhook after cancellation is consistent, not a conflict -
    should not be overwritten to 'failed'."""
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order, user = get_order_and_user(app, order_id, user_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://x', 'paymob_order_id': 'pm-15'}):
            PaymentService.initiate_paymob_payment(order, user)

        from app.services.order_service import OrderService
        order = Order.query.get(order_id)
        OrderService.update_order_status(order, 'cancelled')

        result = PaymentService.process_paymob_webhook(
            webhook_payload('pm-15', amount_cents=10000, success=False)
        )
        assert result.payment_status == 'cancelled'


def test_cannot_initiate_new_payment_for_cancelled_order(app):
    order_id, user_id = make_order(app, total_amount=100.0, status='cancelled')
    with app.app_context():
        order, user = get_order_and_user(app, order_id, user_id)
        with pytest.raises(ValueError):
            PaymentService.initiate_paymob_payment(order, user)


def test_manual_refund_required_payment_ignores_further_webhooks(app):
    """Once flagged, a payment must not be auto-resolved by yet another
    webhook (even a different transaction_id)."""
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order, user = get_order_and_user(app, order_id, user_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://x', 'paymob_order_id': 'pm-16'}):
            PaymentService.initiate_paymob_payment(order, user)

        from app.services.order_service import OrderService
        order = Order.query.get(order_id)
        OrderService.update_order_status(order, 'cancelled')

        PaymentService.process_paymob_webhook(
            webhook_payload('pm-16', transaction_id='txn-a', amount_cents=10000, success=True)
        )
        payment = Payment.query.filter_by(order_id=order_id).first()
        assert payment.payment_status == 'manual_refund_required'

        # A second, different webhook (different transaction_id) arrives.
        result = PaymentService.process_paymob_webhook(
            webhook_payload('pm-16', transaction_id='txn-b', amount_cents=10000, success=True)
        )
        assert result.payment_status == 'manual_refund_required'  # unchanged


# =======================================================================
# create_payment: retry after a failed Paymob attempt (switching to cash)
# =======================================================================

def test_create_payment_reuses_failed_paymob_attempt_as_cash(app):
    """A card payment failed via Paymob - the customer (or admin) now
    records the order as cash on delivery instead. This must reuse the
    existing Payment row (order_id is unique), not reject with
    'payment already exists'."""
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order, user = get_order_and_user(app, order_id, user_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://x', 'paymob_order_id': 'pm-17'}):
            PaymentService.initiate_paymob_payment(order, user)

        payment = Payment.query.filter_by(order_id=order_id).first()
        payment.payment_status = 'failed'
        db.session.add(payment)
        db.session.commit()

        result = PaymentService.create_payment(order_id, 'cash')
        assert result.payment_method == 'cash'
        assert result.payment_status == 'pending'
        # Stale Paymob session details from the failed attempt are cleared.
        assert result.paymob_order_id is None
        assert result.paymob_iframe_url is None

        # Still exactly one Payment row for this order.
        assert Payment.query.filter_by(order_id=order_id).count() == 1


def test_create_payment_rejects_if_already_completed(app):
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order, user = get_order_and_user(app, order_id, user_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://x', 'paymob_order_id': 'pm-18'}):
            PaymentService.initiate_paymob_payment(order, user)

        PaymentService.process_paymob_webhook(
            webhook_payload('pm-18', amount_cents=10000, success=True)
        )
        payment = Payment.query.filter_by(order_id=order_id).first()
        assert payment.payment_status == 'completed'

        with pytest.raises(ValueError):
            PaymentService.create_payment(order_id, 'cash')


def test_create_payment_rejects_for_cancelled_order(app):
    order_id, user_id = make_order(app, total_amount=100.0, status='cancelled')
    with app.app_context():
        with pytest.raises(ValueError):
            PaymentService.create_payment(order_id, 'cash')


# =======================================================================
# Regressions found by the independent pre-launch review
# =======================================================================

def test_paymob_initiate_builds_billing_data_from_the_orders_shipping_address(app):
    """paymob_service.initiate_payment used to read `order.address` (which
    does not exist) and crashed with AttributeError on every card payment.
    Only the three Paymob HTTP calls are mocked here - the code between
    them (the billing-data construction) runs for real."""
    from app.services import paymob_service

    order_id, user_id = make_order(app, total_amount=250.0)
    captured = {}

    def fake_payment_key(auth_token, paymob_order_id, amount_cents, billing_data):
        captured['amount_cents'] = amount_cents
        captured['billing'] = billing_data
        return 'payment-token'

    with app.app_context():
        order, user = get_order_and_user(app, order_id, user_id)
        with patch.object(paymob_service, 'get_auth_token', return_value='auth'), \
             patch.object(paymob_service, 'register_order', return_value='pm-77'), \
             patch.object(paymob_service, 'get_payment_key', side_effect=fake_payment_key):
            result = paymob_service.initiate_payment(order, user)

    assert result['paymob_order_id'] == 'pm-77'
    assert 'payment-token' in result['iframe_url']
    assert captured['amount_cents'] == 25000
    assert captured['billing']['city'] == 'C'
    assert captured['billing']['street'] == 'a'
    assert captured['billing']['phone_number'] == '1'


def test_late_failed_webhook_for_a_different_transaction_never_overwrites_a_completed_payment(app):
    order_id, user_id = make_order(app, total_amount=100.0)
    with app.app_context():
        order, user = get_order_and_user(app, order_id, user_id)
        with patch('app.services.paymob_service.initiate_payment',
                   return_value={'iframe_url': 'https://x', 'paymob_order_id': 'pm-20'}):
            PaymentService.initiate_paymob_payment(order, user)

        ok = PaymentService.process_paymob_webhook(
            webhook_payload('pm-20', transaction_id='txn-ok', success=True))
        assert ok.payment_status == 'completed'

        # An earlier declined attempt's webhook arrives late.
        late = PaymentService.process_paymob_webhook(
            webhook_payload('pm-20', transaction_id='txn-declined-earlier', success=False))
        assert late.payment_status == 'completed'
        assert late.transaction_id == 'txn-ok'

        # A second *successful* transaction must not silently replace the first either.
        again = PaymentService.process_paymob_webhook(
            webhook_payload('pm-20', transaction_id='txn-second', success=True))
        assert again.payment_status == 'completed'
        assert again.transaction_id == 'txn-ok'


def test_zero_total_order_cannot_be_started_as_a_card_payment(app):
    order_id, user_id = make_order(app, total_amount=0.0)
    with app.app_context():
        order, user = get_order_and_user(app, order_id, user_id)
        with patch('app.services.paymob_service.initiate_payment') as mocked:
            with pytest.raises(ValueError):
                PaymentService.initiate_paymob_payment(order, user)
            mocked.assert_not_called()
