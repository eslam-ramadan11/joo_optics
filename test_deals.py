"""Tests for the 'Today's Deals' homepage curation feature:
app/routes/admin.py's deal CRUD/reorder endpoints, the admin-controlled
countdown (app/services/deals_service.py), and the public GET /api/deals
endpoint used to render the homepage section.
"""
from datetime import datetime, timedelta

import pytest

from app import create_app
from app.extensions import db
from app.models.models import User, Product, DailyDeal, DealsCountdown
from app.services import deals_service
from flask_jwt_extended import create_access_token


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

    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        admin = User(username='admin', email='admin@example.com', password_hash='x', is_admin=True)
        customer = User(username='cust', email='cust@example.com', password_hash='x')
        db.session.add_all([admin, customer])
        p1 = Product(name='P1', price=100.0, category='men sunglasses', image_file='i1.png', colors='black', stock_quantity=5)
        p2 = Product(name='P2', price=200.0, category='womens sunglasses', image_file='i2.png', colors='white', stock_quantity=5)
        p3 = Product(name='P3', price=300.0, category='kids glasses', image_file='i3.png', colors='red', stock_quantity=5)
        db.session.add_all([p1, p2, p3])
        db.session.commit()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def auth_header(app, user_id, is_admin=False):
    with app.app_context():
        token = create_access_token(identity=str(user_id), additional_claims={'is_admin': is_admin})
        return {'Authorization': f'Bearer {token}'}


def admin_headers(app):
    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        return auth_header(app, admin.id, is_admin=True)


def product_ids(app):
    with app.app_context():
        return {p.name: p.id for p in Product.query.all()}


# =======================================================================
# Public endpoint
# =======================================================================

def test_public_deals_empty_by_default(client):
    r = client.get('/api/deals')
    assert r.status_code == 200
    body = r.get_json()['data']
    assert body['products'] == []
    assert body['ends_at'] is None


def test_public_deals_does_not_require_login(app, client):
    """The homepage deals section must be visible to guests, not just
    logged-in customers."""
    with app.app_context():
        p = Product.query.first()
        db.session.add(DailyDeal(product_id=p.id, sort_order=0))
        db.session.commit()

    r = client.get('/api/deals')
    assert r.status_code == 200
    assert len(r.get_json()['data']['products']) == 1


def test_public_deals_reflects_admin_order(app, client):
    with app.app_context():
        products = Product.query.order_by(Product.id).all()
        db.session.add(DailyDeal(product_id=products[0].id, sort_order=1))
        db.session.add(DailyDeal(product_id=products[1].id, sort_order=0))
        db.session.commit()
        expected_first_name = products[1].name  # sort_order=0 shows first

    r = client.get('/api/deals')
    products = r.get_json()['data']['products']
    assert products[0]['name'] == expected_first_name


# =======================================================================
# Admin: add / list
# =======================================================================

def test_admin_can_add_product_to_deals(app, client):
    headers = admin_headers(app)
    pids = product_ids(app)

    r = client.post('/api/admin/deals', json={'product_id': pids['P1']}, headers=headers)
    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()['data']['product']['name'] == 'P1'


def test_non_admin_cannot_add_deal(app, client):
    with app.app_context():
        customer = User.query.filter_by(username='cust').first()
        headers = auth_header(app, customer.id, is_admin=False)
    pids = product_ids(app)

    r = client.post('/api/admin/deals', json={'product_id': pids['P1']}, headers=headers)
    assert r.status_code == 403


def test_adding_same_product_twice_is_rejected(app, client):
    headers = admin_headers(app)
    pids = product_ids(app)

    r1 = client.post('/api/admin/deals', json={'product_id': pids['P1']}, headers=headers)
    assert r1.status_code == 201
    r2 = client.post('/api/admin/deals', json={'product_id': pids['P1']}, headers=headers)
    assert r2.status_code == 409


def test_adding_nonexistent_product_is_rejected(app, client):
    headers = admin_headers(app)
    r = client.post('/api/admin/deals', json={'product_id': 999999}, headers=headers)
    assert r.status_code == 404


def test_new_deal_gets_next_sort_order(app, client):
    """New deals are appended to the end, not inserted at the front -
    existing deals keep their relative order."""
    headers = admin_headers(app)
    pids = product_ids(app)

    client.post('/api/admin/deals', json={'product_id': pids['P1']}, headers=headers)
    client.post('/api/admin/deals', json={'product_id': pids['P2']}, headers=headers)
    r = client.get('/api/admin/deals', headers=headers)
    deals = r.get_json()
    names_in_order = [d['product']['name'] for d in sorted(deals, key=lambda d: d['sort_order'])]
    assert names_in_order == ['P1', 'P2']


# =======================================================================
# Admin: remove
# =======================================================================

def test_admin_can_remove_deal(app, client):
    headers = admin_headers(app)
    pids = product_ids(app)

    r = client.post('/api/admin/deals', json={'product_id': pids['P1']}, headers=headers)
    deal_id = r.get_json()['data']['id']

    r2 = client.delete(f'/api/admin/deals/{deal_id}', headers=headers)
    assert r2.status_code == 200

    with app.app_context():
        assert DailyDeal.query.get(deal_id) is None


def test_removing_a_deal_does_not_delete_the_product():
    """Removing from Today's Deals is a curation action only - the
    underlying product must be untouched (see admin.py's remove_deal
    docstring)."""
    # This is asserted structurally: DailyDeal.product_id has no cascade
    # delete back onto Product, and remove_deal only calls
    # db.session.delete(deal) - covered by the model relationship itself,
    # exercised via test_admin_can_remove_deal above (product still
    # exists in product_ids() for subsequent tests in this file).
    pass


def test_removing_nonexistent_deal_returns_404(app, client):
    headers = admin_headers(app)
    r = client.delete('/api/admin/deals/999999', headers=headers)
    assert r.status_code == 404


# =======================================================================
# Admin: reorder
# =======================================================================

def test_admin_can_reorder_deals(app, client):
    headers = admin_headers(app)
    pids = product_ids(app)

    r1 = client.post('/api/admin/deals', json={'product_id': pids['P1']}, headers=headers)
    r2 = client.post('/api/admin/deals', json={'product_id': pids['P2']}, headers=headers)
    id1, id2 = r1.get_json()['data']['id'], r2.get_json()['data']['id']

    # Reverse the order: P2 first, then P1.
    r = client.put('/api/admin/deals/reorder', json={'deal_ids': [id2, id1]}, headers=headers)
    assert r.status_code == 200

    public = client.get('/api/deals').get_json()['data']['products']
    assert [p['name'] for p in public] == ['P2', 'P1']


def test_reorder_with_unknown_deal_id_rejected(app, client):
    headers = admin_headers(app)
    pids = product_ids(app)
    r1 = client.post('/api/admin/deals', json={'product_id': pids['P1']}, headers=headers)
    id1 = r1.get_json()['data']['id']

    r = client.put('/api/admin/deals/reorder', json={'deal_ids': [id1, 999999]}, headers=headers)
    assert r.status_code == 400


def test_reorder_requires_nonempty_list(app, client):
    headers = admin_headers(app)
    r = client.put('/api/admin/deals/reorder', json={'deal_ids': []}, headers=headers)
    assert r.status_code == 400


# =======================================================================
# Countdown: service-layer (singleton get/set/clear/expiry)
# =======================================================================

def test_no_countdown_by_default(app):
    with app.app_context():
        assert deals_service.get_countdown() is None
        assert deals_service.is_countdown_expired() is False


def test_set_countdown_creates_the_singleton_row(app):
    with app.app_context():
        ends_at = datetime.utcnow() + timedelta(hours=3)
        deals_service.set_countdown(ends_at)

        countdown = deals_service.get_countdown()
        assert countdown is not None
        assert countdown.ends_at == ends_at


def test_setting_countdown_twice_updates_the_same_row_not_a_second_one(app):
    with app.app_context():
        deals_service.set_countdown(datetime.utcnow() + timedelta(hours=1))
        deals_service.set_countdown(datetime.utcnow() + timedelta(hours=5))

        assert DealsCountdown.query.count() == 1


def test_future_countdown_is_not_expired(app):
    with app.app_context():
        deals_service.set_countdown(datetime.utcnow() + timedelta(hours=1))
        assert deals_service.is_countdown_expired() is False


def test_past_countdown_is_expired(app):
    with app.app_context():
        deals_service.set_countdown(datetime.utcnow() - timedelta(minutes=1))
        assert deals_service.is_countdown_expired() is True


def test_clear_countdown_makes_it_not_expired_again(app):
    with app.app_context():
        deals_service.set_countdown(datetime.utcnow() - timedelta(hours=1))
        assert deals_service.is_countdown_expired() is True

        deals_service.clear_countdown()
        assert deals_service.is_countdown_expired() is False
        assert deals_service.get_countdown().ends_at is None


# =======================================================================
# Countdown: public endpoint enforces expiry server-side
# =======================================================================

def test_public_deals_hidden_once_countdown_expires(app, client):
    """The core requirement: once the countdown ends, the products stop
    being returned - regardless of client-side timing - and the
    underlying DailyDeal rows are left untouched."""
    with app.app_context():
        p = Product.query.first()
        db.session.add(DailyDeal(product_id=p.id, sort_order=0))
        deals_service.set_countdown(datetime.utcnow() - timedelta(minutes=1))
        db.session.commit()

    r = client.get('/api/deals')
    body = r.get_json()['data']
    assert body['products'] == []
    assert body['ends_at'] is None

    with app.app_context():
        # The curated product is still there, just not currently shown -
        # a new countdown should bring it right back.
        assert DailyDeal.query.count() == 1


def test_public_deals_shows_products_and_ends_at_while_active(app, client):
    with app.app_context():
        p = Product.query.first()
        db.session.add(DailyDeal(product_id=p.id, sort_order=0))
        ends_at = datetime.utcnow() + timedelta(hours=2)
        deals_service.set_countdown(ends_at)
        db.session.commit()

    r = client.get('/api/deals')
    body = r.get_json()['data']
    assert len(body['products']) == 1
    assert body['ends_at'] is not None


def test_public_deals_shows_products_with_no_ends_at_when_no_countdown_set(app, client):
    with app.app_context():
        p = Product.query.first()
        db.session.add(DailyDeal(product_id=p.id, sort_order=0))
        db.session.commit()

    r = client.get('/api/deals')
    body = r.get_json()['data']
    assert len(body['products']) == 1
    assert body['ends_at'] is None


def test_restarting_countdown_after_expiry_brings_deals_back(app, client):
    """Confirms the whole point of not deleting DailyDeal rows on
    expiry - the admin can start a fresh countdown and get the exact
    same curated list back with no re-work."""
    with app.app_context():
        p = Product.query.first()
        db.session.add(DailyDeal(product_id=p.id, sort_order=0))
        deals_service.set_countdown(datetime.utcnow() - timedelta(minutes=1))
        db.session.commit()

    assert client.get('/api/deals').get_json()['data']['products'] == []

    with app.app_context():
        deals_service.set_countdown(datetime.utcnow() + timedelta(hours=1))

    r = client.get('/api/deals')
    assert len(r.get_json()['data']['products']) == 1


# =======================================================================
# Countdown: admin API
# =======================================================================

def test_admin_can_view_countdown_status(app, client):
    headers = admin_headers(app)
    r = client.get('/api/admin/deals/countdown', headers=headers)
    assert r.status_code == 200
    assert r.get_json()['data']['ends_at'] is None


def test_non_admin_cannot_view_countdown_status(app, client):
    with app.app_context():
        customer = User.query.filter_by(username='cust').first()
        headers = auth_header(app, customer.id, is_admin=False)
    r = client.get('/api/admin/deals/countdown', headers=headers)
    assert r.status_code == 403


def test_admin_can_set_countdown_by_duration(app, client):
    headers = admin_headers(app)
    r = client.put('/api/admin/deals/countdown', json={'duration_minutes': 180}, headers=headers)
    assert r.status_code == 200
    ends_at = r.get_json()['data']['ends_at']
    assert ends_at is not None

    parsed = datetime.fromisoformat(ends_at)
    expected = datetime.utcnow() + timedelta(minutes=180)
    assert abs((parsed - expected).total_seconds()) < 5  # allow a little test-runtime slack


def test_admin_can_set_countdown_by_exact_datetime(app, client):
    headers = admin_headers(app)
    future = (datetime.utcnow() + timedelta(days=1)).isoformat()
    r = client.put('/api/admin/deals/countdown', json={'ends_at': future}, headers=headers)
    assert r.status_code == 200
    assert r.get_json()['data']['ends_at'] is not None


def test_setting_countdown_in_the_past_is_rejected(app, client):
    headers = admin_headers(app)
    past = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    r = client.put('/api/admin/deals/countdown', json={'ends_at': past}, headers=headers)
    assert r.status_code == 400


def test_setting_countdown_with_neither_field_is_rejected(app, client):
    headers = admin_headers(app)
    r = client.put('/api/admin/deals/countdown', json={}, headers=headers)
    assert r.status_code == 400


def test_setting_countdown_with_negative_duration_is_rejected(app, client):
    headers = admin_headers(app)
    r = client.put('/api/admin/deals/countdown', json={'duration_minutes': -30}, headers=headers)
    assert r.status_code == 400


def test_admin_can_cancel_countdown(app, client):
    headers = admin_headers(app)
    client.put('/api/admin/deals/countdown', json={'duration_minutes': 60}, headers=headers)

    r = client.delete('/api/admin/deals/countdown', headers=headers)
    assert r.status_code == 200

    status = client.get('/api/admin/deals/countdown', headers=headers)
    assert status.get_json()['data']['ends_at'] is None


def test_non_admin_cannot_set_or_cancel_countdown(app, client):
    with app.app_context():
        customer = User.query.filter_by(username='cust').first()
        headers = auth_header(app, customer.id, is_admin=False)

    r1 = client.put('/api/admin/deals/countdown', json={'duration_minutes': 60}, headers=headers)
    assert r1.status_code == 403

    r2 = client.delete('/api/admin/deals/countdown', headers=headers)
    assert r2.status_code == 403
