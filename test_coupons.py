"""Tests for the coupon system: app/services/coupon_service.py (the
service-layer logic that decides how much a coupon is worth, used
identically by both the checkout preview and the real order-creation
path - see order_service.py), plus the admin CRUD and public /validate
API routes.
"""
from datetime import datetime, timedelta

import pytest

from app import create_app
from app.extensions import db
from app.models.models import User, Product, Coupon, Order, ShippingAddress
from app.services import coupon_service
from flask_jwt_extended import create_access_token


@pytest.fixture
def reset_db():
    """Shadow conftest.py's autouse reset_db - see test_orders.py for why:
    this file seeds its own isolated per-test database in the app fixture
    below, and the global autouse fixture would otherwise wipe it before
    the test body runs."""
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

    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        admin = User(username='admin', email='admin@example.com', password_hash='x', is_admin=True)
        customer = User(username='cust', email='cust@example.com', password_hash='x')
        db.session.add_all([admin, customer])
        db.session.commit()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def auth_header(app, user_id, is_admin=False):
    with app.app_context():
        token = create_access_token(identity=str(user_id), additional_claims={'is_admin': is_admin})
        return {'Authorization': f'Bearer {token}'}


def make_priced_items(product_id=1, category='men sunglasses', quantity=1, frame_price=100.0, lens_price=0.0):
    return [{
        'product_id': product_id, 'category': category, 'quantity': quantity,
        'frame_price': frame_price, 'lens_price': lens_price,
    }]


# =======================================================================
# Service-layer tests: validate_and_calculate - the single source of
# truth used both by the checkout preview and real order creation.
# =======================================================================

def test_code_not_found(app):
    with app.app_context():
        customer = User.query.filter_by(username='cust').first()
        coupon, discount, error = coupon_service.validate_and_calculate(
            'NOPE', customer.id, make_priced_items()
        )
        assert coupon is None
        assert discount == 0.0
        assert error == coupon_service.ERROR_NOT_FOUND


def test_code_lookup_is_case_insensitive(app):
    with app.app_context():
        customer = User.query.filter_by(username='cust').first()
        c = Coupon(code='SAVE10', discount_type='percentage', discount_value=10, apply_to='all')
        db.session.add(c)
        db.session.commit()

        coupon, discount, error = coupon_service.validate_and_calculate(
            'save10', customer.id, make_priced_items(frame_price=100.0)
        )
        assert error is None
        assert coupon.code == 'SAVE10'
        assert discount == 10.0


def test_inactive_coupon_rejected(app):
    with app.app_context():
        customer = User.query.filter_by(username='cust').first()
        c = Coupon(code='OFF', discount_type='fixed', discount_value=5, apply_to='all', is_active=False)
        db.session.add(c)
        db.session.commit()

        _, _, error = coupon_service.validate_and_calculate('OFF', customer.id, make_priced_items())
        assert error == coupon_service.ERROR_INACTIVE


def test_not_yet_started_coupon_rejected(app):
    with app.app_context():
        customer = User.query.filter_by(username='cust').first()
        future = datetime.utcnow() + timedelta(days=1)
        c = Coupon(code='SOON', discount_type='fixed', discount_value=5, apply_to='all', start_date=future)
        db.session.add(c)
        db.session.commit()

        _, _, error = coupon_service.validate_and_calculate('SOON', customer.id, make_priced_items())
        assert error == coupon_service.ERROR_NOT_STARTED


def test_expired_coupon_rejected(app):
    with app.app_context():
        customer = User.query.filter_by(username='cust').first()
        past = datetime.utcnow() - timedelta(days=1)
        c = Coupon(code='OLD', discount_type='fixed', discount_value=5, apply_to='all', end_date=past)
        db.session.add(c)
        db.session.commit()

        _, _, error = coupon_service.validate_and_calculate('OLD', customer.id, make_priced_items())
        assert error == coupon_service.ERROR_EXPIRED


def test_total_usage_limit_enforced(app):
    with app.app_context():
        customer = User.query.filter_by(username='cust').first()
        addr = ShippingAddress(user_id=customer.id, city='C', full_address='a', phone_number='1')
        db.session.add(addr)
        c = Coupon(code='LIMITED', discount_type='fixed', discount_value=5, apply_to='all', max_total_uses=1)
        db.session.add(c)
        db.session.commit()
        # One prior order already used this coupon.
        db.session.add(Order(user_id=customer.id, address_id=addr.id, total_amount=95.0, coupon_id=c.id))
        db.session.commit()

        _, _, error = coupon_service.validate_and_calculate('LIMITED', customer.id, make_priced_items())
        assert error == coupon_service.ERROR_TOTAL_LIMIT


def test_per_customer_usage_limit_enforced(app):
    with app.app_context():
        customer = User.query.filter_by(username='cust').first()
        addr = ShippingAddress(user_id=customer.id, city='C', full_address='a', phone_number='1')
        db.session.add(addr)
        c = Coupon(code='ONCE', discount_type='fixed', discount_value=5, apply_to='all', max_uses_per_customer=1)
        db.session.add(c)
        db.session.commit()
        db.session.add(Order(user_id=customer.id, address_id=addr.id, total_amount=95.0, coupon_id=c.id))
        db.session.commit()

        _, _, error = coupon_service.validate_and_calculate('ONCE', customer.id, make_priced_items())
        assert error == coupon_service.ERROR_CUSTOMER_LIMIT


def test_min_order_amount_checked_against_eligible_amount_not_full_cart(app):
    """Per spec: min_order_amount is checked against the ELIGIBLE portion
    of the cart (what this coupon's scope actually covers), not the raw
    cart total - e.g. a 'lenses_only' coupon with min_order_amount=200
    should fail if the lens portion alone is under 200, even if frames
    make the total cart much bigger."""
    with app.app_context():
        customer = User.query.filter_by(username='cust').first()
        c = Coupon(
            code='LENSMIN', discount_type='fixed', discount_value=10,
            apply_to='lenses_only', min_order_amount=200,
        )
        db.session.add(c)
        db.session.commit()

        # Frame is expensive (500) but lens is cheap (50) - eligible
        # amount (lenses_only) is only 50, well under the 200 minimum,
        # even though the full cart (550) would clear it.
        items = make_priced_items(frame_price=500.0, lens_price=50.0)
        _, _, error = coupon_service.validate_and_calculate('LENSMIN', customer.id, items)
        assert error == coupon_service.ERROR_MIN_ORDER


def test_category_scope_only_counts_matching_items(app):
    with app.app_context():
        customer = User.query.filter_by(username='cust').first()
        c = Coupon(
            code='CATSALE', discount_type='percentage', discount_value=50,
            apply_to='category', apply_to_value='kids glasses',
        )
        db.session.add(c)
        db.session.commit()

        items = [
            {'product_id': 1, 'category': 'kids glasses', 'quantity': 1, 'frame_price': 100.0, 'lens_price': 0.0},
            {'product_id': 2, 'category': 'men sunglasses', 'quantity': 1, 'frame_price': 200.0, 'lens_price': 0.0},
        ]
        coupon, discount, error = coupon_service.validate_and_calculate('CATSALE', customer.id, items)
        assert error is None
        # Only the kids-glasses item (100) counts - 50% of that is 50,
        # not 50% of the full 300 cart.
        assert discount == 50.0


def test_item_not_in_scope_at_all_is_not_eligible(app):
    with app.app_context():
        customer = User.query.filter_by(username='cust').first()
        c = Coupon(
            code='SPECIFIC', discount_type='fixed', discount_value=10,
            apply_to='specific_products', apply_to_value='999',
        )
        db.session.add(c)
        db.session.commit()

        items = make_priced_items(product_id=1)  # not product 999
        _, _, error = coupon_service.validate_and_calculate('SPECIFIC', customer.id, items)
        assert error == coupon_service.ERROR_NOT_ELIGIBLE


def test_percentage_discount_calculation(app):
    with app.app_context():
        customer = User.query.filter_by(username='cust').first()
        c = Coupon(code='PCT20', discount_type='percentage', discount_value=20, apply_to='all')
        db.session.add(c)
        db.session.commit()

        _, discount, error = coupon_service.validate_and_calculate(
            'PCT20', customer.id, make_priced_items(frame_price=150.0)
        )
        assert error is None
        assert discount == 30.0  # 20% of 150


def test_percentage_discount_capped_by_max_discount_amount(app):
    with app.app_context():
        customer = User.query.filter_by(username='cust').first()
        c = Coupon(
            code='BIGPCT', discount_type='percentage', discount_value=50,
            apply_to='all', max_discount_amount=30,
        )
        db.session.add(c)
        db.session.commit()

        # 50% of 500 would be 250, but max_discount_amount caps it at 30.
        _, discount, error = coupon_service.validate_and_calculate(
            'BIGPCT', customer.id, make_priced_items(frame_price=500.0)
        )
        assert error is None
        assert discount == 30.0


def test_fixed_discount_capped_at_eligible_amount(app):
    """A fixed discount larger than the cart itself must never push the
    total negative - it should cap at the eligible amount."""
    with app.app_context():
        customer = User.query.filter_by(username='cust').first()
        c = Coupon(code='HUGE', discount_type='fixed', discount_value=1000, apply_to='all')
        db.session.add(c)
        db.session.commit()

        _, discount, error = coupon_service.validate_and_calculate(
            'HUGE', customer.id, make_priced_items(frame_price=40.0)
        )
        assert error is None
        assert discount == 40.0  # capped, never negative-total territory


def test_frames_only_scope_excludes_lens_price(app):
    with app.app_context():
        customer = User.query.filter_by(username='cust').first()
        c = Coupon(code='FRAMEDEAL', discount_type='percentage', discount_value=100, apply_to='frames_only')
        db.session.add(c)
        db.session.commit()

        items = make_priced_items(frame_price=100.0, lens_price=200.0)
        _, discount, error = coupon_service.validate_and_calculate('FRAMEDEAL', customer.id, items)
        assert error is None
        # 100% of frame price only (100), not the lens price (200).
        assert discount == 100.0


# =======================================================================
# API-level tests: admin CRUD + public validate endpoint
# =======================================================================

def test_admin_can_create_coupon(app, client):
    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        headers = auth_header(app, admin.id, is_admin=True)

    r = client.post('/api/admin/coupons', json={
        'code': 'newcode', 'discount_type': 'fixed', 'discount_value': 15, 'apply_to': 'all',
    }, headers=headers)
    assert r.status_code == 201, r.get_data(as_text=True)
    body = r.get_json()
    # Codes are normalized to uppercase regardless of how they're typed.
    assert body['data']['code'] == 'NEWCODE'


def test_non_admin_cannot_create_coupon(app, client):
    with app.app_context():
        customer = User.query.filter_by(username='cust').first()
        headers = auth_header(app, customer.id, is_admin=False)

    r = client.post('/api/admin/coupons', json={
        'code': 'HACK', 'discount_type': 'fixed', 'discount_value': 15, 'apply_to': 'all',
    }, headers=headers)
    assert r.status_code == 403


def test_duplicate_coupon_code_rejected(app, client):
    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        headers = auth_header(app, admin.id, is_admin=True)

    payload = {'code': 'DUPE', 'discount_type': 'fixed', 'discount_value': 5, 'apply_to': 'all'}
    r1 = client.post('/api/admin/coupons', json=payload, headers=headers)
    assert r1.status_code == 201
    r2 = client.post('/api/admin/coupons', json=payload, headers=headers)
    assert r2.status_code == 409


def test_percentage_discount_value_over_100_rejected(app, client):
    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        headers = auth_header(app, admin.id, is_admin=True)

    r = client.post('/api/admin/coupons', json={
        'code': 'TOOMUCH', 'discount_type': 'percentage', 'discount_value': 150, 'apply_to': 'all',
    }, headers=headers)
    assert r.status_code == 400


def test_deleting_used_coupon_is_blocked(app, client):
    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        customer = User.query.filter_by(username='cust').first()
        headers = auth_header(app, admin.id, is_admin=True)

        addr = ShippingAddress(user_id=customer.id, city='C', full_address='a', phone_number='1')
        db.session.add(addr)
        c = Coupon(code='USEDCODE', discount_type='fixed', discount_value=5, apply_to='all')
        db.session.add(c)
        db.session.commit()
        db.session.add(Order(user_id=customer.id, address_id=addr.id, total_amount=95.0, coupon_id=c.id))
        db.session.commit()
        coupon_id = c.id

    r = client.delete(f'/api/admin/coupons/{coupon_id}', headers=headers)
    assert r.status_code == 400
    with app.app_context():
        assert Coupon.query.get(coupon_id) is not None  # still there


def test_deleting_unused_coupon_succeeds(app, client):
    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        headers = auth_header(app, admin.id, is_admin=True)
        c = Coupon(code='UNUSED', discount_type='fixed', discount_value=5, apply_to='all')
        db.session.add(c)
        db.session.commit()
        coupon_id = c.id

    r = client.delete(f'/api/admin/coupons/{coupon_id}', headers=headers)
    assert r.status_code == 200
    with app.app_context():
        assert Coupon.query.get(coupon_id) is None


def test_public_validate_requires_login(app, client):
    r = client.post('/api/coupons/validate', json={'code': 'ANY', 'items': []})
    assert r.status_code == 401


def test_public_validate_returns_specific_error_message(app, client):
    with app.app_context():
        customer = User.query.filter_by(username='cust').first()
        product = Product(name='P', price=100.0, category='men sunglasses', image_file='i.png', colors='black', stock_quantity=5)
        db.session.add(product)
        db.session.commit()
        headers = auth_header(app, customer.id, is_admin=False)
        product_id = product.id

    r = client.post('/api/coupons/validate', json={
        'code': 'DOESNOTEXIST',
        'items': [{'product_id': product_id, 'quantity': 1}],
    }, headers=headers)
    assert r.status_code == 400
    assert r.get_json()['message'] == coupon_service.ERROR_NOT_FOUND


def test_public_validate_does_not_record_a_use(app, client):
    """Previewing a coupon must never count against its usage limits -
    only an actual placed order does (see order_service.create_order)."""
    with app.app_context():
        customer = User.query.filter_by(username='cust').first()
        product = Product(name='P', price=100.0, category='men sunglasses', image_file='i.png', colors='black', stock_quantity=5)
        db.session.add(product)
        c = Coupon(code='PREVIEW', discount_type='fixed', discount_value=10, apply_to='all', max_total_uses=1)
        db.session.add(c)
        db.session.commit()
        headers = auth_header(app, customer.id, is_admin=False)
        product_id = product.id

    for _ in range(3):
        r = client.post('/api/coupons/validate', json={
            'code': 'PREVIEW',
            'items': [{'product_id': product_id, 'quantity': 1}],
        }, headers=headers)
        assert r.status_code == 200, r.get_data(as_text=True)


# =======================================================================
# Coupon row locking (race-condition fix)
#
# NOTE: SQLite (used by these tests) does not implement real row-level
# locking the way PostgreSQL does - SQLAlchemy silently omits the FOR
# UPDATE clause on this dialect rather than erroring. These tests confirm
# the lock=True code path is wired correctly and doesn't break normal
# coupon behavior; they cannot exercise genuine concurrent-request
# blocking, which only a PostgreSQL-backed test (or the real app in
# production) can demonstrate.
# =======================================================================

def test_find_coupon_with_lock_returns_same_result_as_without(app):
    with app.app_context():
        c = Coupon(code='LOCKTEST', discount_type='fixed', discount_value=5, apply_to='all')
        db.session.add(c)
        db.session.commit()

        unlocked = coupon_service.find_coupon('LOCKTEST', lock=False)
        locked = coupon_service.find_coupon('LOCKTEST', lock=True)
        assert unlocked.id == locked.id == c.id


def test_validate_and_calculate_with_lock_still_works_correctly(app):
    """The lock parameter must not change any validation or discount
    logic - only the earlier order-creation tests already cover every
    business rule; this just confirms lock=True doesn't disturb them."""
    with app.app_context():
        customer = User.query.filter_by(username='cust').first()
        c = Coupon(code='LOCKCALC', discount_type='percentage', discount_value=20, apply_to='all')
        db.session.add(c)
        db.session.commit()

        coupon, discount, error = coupon_service.validate_and_calculate(
            'LOCKCALC', customer.id, make_priced_items(frame_price=100.0), lock=True
        )
        assert error is None
        assert discount == 20.0


def test_order_creation_uses_locked_coupon_lookup(app, client):
    """End-to-end: placing a real order with a coupon still succeeds and
    correctly counts against max_total_uses, now going through the
    locked lookup path."""
    with app.app_context():
        customer = User.query.filter_by(username='cust').first()
        addr = ShippingAddress(user_id=customer.id, city='C', full_address='a', phone_number='1')
        product = Product(name='P', price=100.0, category='men sunglasses',
                           image_file='i.png', colors='black', stock_quantity=10)
        db.session.add_all([addr, product])
        c = Coupon(code='ONEUSE', discount_type='fixed', discount_value=10, apply_to='all', max_total_uses=1)
        db.session.add(c)
        db.session.commit()
        headers = auth_header(app, customer.id, is_admin=False)
        address_id, product_id = addr.id, product.id

    payload = {
        'address_id': address_id,
        'items': [{'product_id': product_id, 'quantity': 1}],
        'coupon_code': 'ONEUSE',
    }
    r1 = client.post('/api/orders', json=payload, headers=headers)
    assert r1.status_code == 201, r1.get_data(as_text=True)
    assert r1.get_json()['data']['discount_amount'] == 10.0

    # A second order attempting to reuse the same (now exhausted) coupon
    # is rejected - this is the sequential case, which already worked
    # before this fix; the fix specifically closes the *concurrent* gap,
    # which SQLite can't demonstrate (see module note above).
    r2 = client.post('/api/orders', json=payload, headers=headers)
    assert r2.status_code == 400


def test_role_change_requires_a_real_boolean_not_the_string_false(app, client):
    """bool("false") is True - a string must never promote a user to admin."""
    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        cust = User.query.filter_by(username='cust').first()
        headers = auth_header(app, admin.id, is_admin=True)
        cust_id = cust.id

    r = client.put(f'/api/admin/users/{cust_id}/role', json={'is_admin': 'false'}, headers=headers)
    assert r.status_code == 400
    with app.app_context():
        assert User.query.get(cust_id).is_admin is False

    ok = client.put(f'/api/admin/users/{cust_id}/role', json={'is_admin': True}, headers=headers)
    assert ok.status_code == 200
    assert ok.get_json()['data']['is_admin'] is True
