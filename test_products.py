import io
import json
import pytest

from app import create_app
from app.extensions import db
from app.models.models import User, Product
from flask_jwt_extended import create_access_token

PNG_BYTES = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32


@pytest.fixture
def reset_db():
    """Shadow conftest.py's autouse `reset_db(app)` - see test_orders.py
    for the full explanation. This file's own `app` fixture already
    creates and seeds an isolated per-test database."""
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
        # create an admin user
        admin = User(username='admin', email='admin@example.com', password_hash='x', is_admin=True)
        db.session.add(admin)
        db.session.commit()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def get_auth_header(app, user_id):
    with app.app_context():
        token = create_access_token(identity=str(user_id), additional_claims={'is_admin': True})
        return {'Authorization': f'Bearer {token}'}


def test_product_crud(client, app):
    # create admin token
    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        headers = get_auth_header(app, admin.id)

    # Create product - image_file is dump_only (server-managed), so
    # creation goes through multipart/form-data with a real uploaded file,
    # not a JSON string path.
    form = {
        'name': 'Test Product',
        'price': '9.99',
        'category': 'men sunglasses',
        'colors': 'Black',
        'stock_quantity': '10',
    }
    data = {**form, 'image': (io.BytesIO(PNG_BYTES), 'img.png')}
    r = client.post('/api/products', data=data, headers=headers, content_type='multipart/form-data')
    assert r.status_code == 201, r.get_data(as_text=True)
    body = r.get_json()
    assert body['success'] is True
    pid = body['data']['id']

    # Get product
    r = client.get(f'/api/products/{pid}')
    assert r.status_code == 200
    body = r.get_json()
    assert body['data']['name'] == 'Test Product'

    # Update product
    r = client.put(f'/api/products/{pid}', json={'price': 12.5}, headers=headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body['data']['price'] == 12.5

    # List products
    r = client.get('/api/products')
    assert r.status_code == 200
    body = r.get_json()
    assert body['data']['total'] == 1

    # Delete product
    r = client.delete(f'/api/products/{pid}', headers=headers)
    assert r.status_code == 200

    # Ensure deleted
    r = client.get(f'/api/products/{pid}')
    assert r.status_code == 404


# =======================================================================
# Best sellers - ranked by real order history, never fabricated
# =======================================================================

def test_best_sellers_empty_when_nothing_sold(client, app):
    r = client.get('/api/products/best-sellers')
    assert r.status_code == 200
    assert r.get_json()['data'] == []


def test_best_sellers_ranked_by_real_quantity_sold(client, app):
    from app.models.models import ShippingAddress, Order, OrderItem

    with app.app_context():
        user = User(username='u1', email='u1@example.com', password_hash='x')
        db.session.add(user)
        db.session.commit()
        addr = ShippingAddress(user_id=user.id, city='C', full_address='a', phone_number='1')
        db.session.add(addr)

        popular = Product(name='Popular', price=100.0, category='men sunglasses',
                           image_file='i.png', colors='black', stock_quantity=50)
        unpopular = Product(name='Unpopular', price=100.0, category='men sunglasses',
                             image_file='i.png', colors='black', stock_quantity=50)
        db.session.add_all([popular, unpopular])
        db.session.commit()

        order = Order(user_id=user.id, address_id=addr.id, total_amount=500.0, status='delivered')
        db.session.add(order)
        db.session.commit()

        db.session.add(OrderItem(order_id=order.id, product_id=popular.id, lens_type='', quantity=5, item_price=100.0))
        db.session.add(OrderItem(order_id=order.id, product_id=unpopular.id, lens_type='', quantity=1, item_price=100.0))
        db.session.commit()

    r = client.get('/api/products/best-sellers')
    names = [p['name'] for p in r.get_json()['data']]
    assert names[0] == 'Popular'
    assert 'Unpopular' in names  # still ranked, just lower


def test_best_sellers_excludes_cancelled_orders(client, app):
    """A cancelled order isn't a real sale - it must not inflate a
    product's ranking."""
    from app.models.models import ShippingAddress, Order, OrderItem

    with app.app_context():
        user = User(username='u1', email='u1@example.com', password_hash='x')
        db.session.add(user)
        db.session.commit()
        addr = ShippingAddress(user_id=user.id, city='C', full_address='a', phone_number='1')
        product = Product(name='OnlyCancelled', price=100.0, category='men sunglasses',
                           image_file='i.png', colors='black', stock_quantity=50)
        db.session.add_all([addr, product])
        db.session.commit()

        order = Order(user_id=user.id, address_id=addr.id, total_amount=100.0, status='cancelled')
        db.session.add(order)
        db.session.commit()
        db.session.add(OrderItem(order_id=order.id, product_id=product.id, lens_type='', quantity=10, item_price=100.0))
        db.session.commit()

    r = client.get('/api/products/best-sellers')
    names = [p['name'] for p in r.get_json()['data']]
    assert 'OnlyCancelled' not in names


def test_best_sellers_respects_limit_param(client, app):
    r = client.get('/api/products/best-sellers?limit=3')
    assert r.status_code == 200
    assert len(r.get_json()['data']) <= 3


# Grouped categories - "All Sunglasses", "Men's (All)" etc.
# =======================================================================

def _seed_categories(app):
    with app.app_context():
        for name, cat in [
            ('MenSun', 'men sunglasses'),
            ('WomenSun', 'womens sunglasses'),
            ('MenMed', 'men medical fraims'),
            ('WomenMed', 'womens medical fraims'),
        ]:
            db.session.add(Product(name=name, price=100.0, category=cat,
                                   image_file='i.png', colors='black', stock_quantity=5))
        db.session.commit()


def _names(response):
    data = response.get_json()['data']
    items = data['items'] if isinstance(data, dict) else data
    return {p['name'] for p in items}


def test_category_filter_single_exact_match(client, app):
    _seed_categories(app)
    r = client.get('/api/products?category=men%20sunglasses')
    assert r.status_code == 200
    assert _names(r) == {'MenSun'}


def test_category_filter_comma_separated_matches_any(client, app):
    _seed_categories(app)
    r = client.get('/api/products?category=men%20sunglasses,womens%20sunglasses')
    assert _names(r) == {'MenSun', 'WomenSun'}


def test_category_filter_gender_grouping(client, app):
    _seed_categories(app)
    r = client.get('/api/products?category=womens%20sunglasses,womens%20medical%20fraims')
    assert _names(r) == {'WomenSun', 'WomenMed'}


def test_category_filter_ignores_stray_spaces_and_empty_entries(client, app):
    _seed_categories(app)
    r = client.get('/api/products?category=men%20sunglasses%20,,%20womens%20sunglasses,')
    assert _names(r) == {'MenSun', 'WomenSun'}
