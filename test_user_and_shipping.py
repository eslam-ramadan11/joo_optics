import os
import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db
from app.models.models import User


@pytest.fixture
def test_app(tmp_path):
    db_path = (tmp_path / 'test.db').resolve()

    class TestConfig:
        TESTING = True
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_path.as_posix()}'
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        SECRET_KEY = 'test-secret'
        JWT_SECRET_KEY = 'test-jwt-secret'

    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        user = User(username='customer', email='customer@example.com', password_hash='hash', is_admin=False)
        db.session.add(user)
        db.session.commit()
        app.config['TEST_USER_ID'] = user.id
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(test_app):
    return test_app.test_client()


def get_auth_headers(app, user_id):
    with app.app_context():
        token = create_access_token(identity=str(user_id), additional_claims={'is_admin': False})
    return {'Authorization': f'Bearer {token}'}


def test_profile_and_shipping_endpoints(client, test_app):
    headers = get_auth_headers(test_app, test_app.config['TEST_USER_ID'])

    profile_resp = client.get('/api/user/profile', headers=headers)
    assert profile_resp.status_code == 200, profile_resp.get_data(as_text=True)
    body = profile_resp.get_json()
    assert body['success'] is True
    assert body['data']['username'] == 'customer'

    update_resp = client.put('/api/user/profile', json={'email': 'new@example.com'}, headers=headers)
    assert update_resp.status_code == 200
    assert update_resp.get_json()['data']['email'] == 'new@example.com'

    create_addr_resp = client.post(
        '/api/shipping-addresses',
        json={
            'city': 'Cairo',
            'full_address': '123 Street',
            'phone_number': '01000000000',
            'is_default': True,
        },
        headers=headers,
    )
    assert create_addr_resp.status_code == 201
    addr_id = create_addr_resp.get_json()['data']['id']

    list_resp = client.get('/api/shipping-addresses', headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.get_json()['data']) == 1

    delete_resp = client.delete(f'/api/shipping-addresses/{addr_id}', headers=headers)
    assert delete_resp.status_code == 200


def test_deleting_an_address_used_by_an_order_is_refused_with_409(client, test_app):
    from app.models.models import ShippingAddress, Order

    headers = get_auth_headers(test_app, test_app.config['TEST_USER_ID'])
    with test_app.app_context():
        addr = ShippingAddress(user_id=test_app.config['TEST_USER_ID'], city='C', full_address='a', phone_number='1')
        db.session.add(addr)
        db.session.commit()
        db.session.add(Order(user_id=test_app.config['TEST_USER_ID'], address_id=addr.id, total_amount=10.0))
        db.session.commit()
        addr_id = addr.id

    resp = client.delete(f'/api/shipping-addresses/{addr_id}', headers=headers)
    assert resp.status_code == 409
    assert 'order' in resp.get_json()['message'].lower()

    with test_app.app_context():
        assert ShippingAddress.query.get(addr_id) is not None  # still there


def test_deleting_an_unused_address_still_works(client, test_app):
    from app.models.models import ShippingAddress

    headers = get_auth_headers(test_app, test_app.config['TEST_USER_ID'])
    with test_app.app_context():
        addr = ShippingAddress(user_id=test_app.config['TEST_USER_ID'], city='C', full_address='a', phone_number='1')
        db.session.add(addr)
        db.session.commit()
        addr_id = addr.id

    resp = client.delete(f'/api/shipping-addresses/{addr_id}', headers=headers)
    assert resp.status_code == 200
