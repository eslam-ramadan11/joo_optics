import pytest

from app import create_app
from app.extensions import db
from app.models.models import User, Product, ShippingAddress, Prescription
from flask_jwt_extended import create_access_token


@pytest.fixture
def reset_db():
    """Shadow conftest.py's autouse `reset_db(app)`.

    That fixture also depends on something named `app`, and pytest resolves
    it to THIS file's own `app` fixture below - meaning it was running
    db.drop_all()+create_all() right after this fixture seeds its data, but
    before the test body runs, wiping every seeded row. This file already
    creates and seeds its own fully isolated per-test database, so the
    global reset is a no-op here.
    """
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
        user = User(username='o_user', email='o@example.com', password_hash='x')
        db.session.add(user)
        db.session.commit()
        p1 = Product(name='P1', price=10.0, category='c', image_file='i.png', colors='black', stock_quantity=5)
        p2 = Product(name='P2', price=20.0, category='c', image_file='i2.png', colors='white', stock_quantity=1)
        db.session.add_all([p1, p2])
        addr = ShippingAddress(user_id=user.id, city='C', full_address='addr', phone_number='123')
        db.session.add(addr)
        # NOTE: OrderItem.prescription_id is a NOT-NULL foreign key, and
        # OrderService now verifies the prescription actually belongs to the
        # ordering user (fixes an IDOR where any prescription_id was
        # accepted). A real, owned Prescription is required here instead of
        # the old placeholder id=0.
        presc = Prescription(
            user_id=user.id, image_file='presc.png',
            sph_r=-1.0, cyl_r=-0.5, axis_r=90,
            sph_l=-1.0, cyl_l=-0.5, axis_l=90,
        )
        db.session.add(presc)
        db.session.commit()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def get_auth_header(app, user_id):
    with app.app_context():
        token = create_access_token(identity=str(user_id), additional_claims={'is_admin': False})
        return {'Authorization': f'Bearer {token}'}


def test_create_order_and_stock_adjustment(client, app):
    with app.app_context():
        user = User.query.filter_by(username='o_user').first()
        headers = get_auth_header(app, user.id)
        addr = ShippingAddress.query.filter_by(user_id=user.id).first()
        p1 = Product.query.filter_by(name='P1').first()
        presc = Prescription.query.filter_by(user_id=user.id).first()

    payload = {
        'address_id': addr.id,
        'items': [
            {'product_id': p1.id, 'prescription_id': presc.id, 'quantity': 2}
        ]
    }
    rv = client.post('/api/orders', json=payload, headers=headers)
    assert rv.status_code == 201, rv.get_data(as_text=True)
    body = rv.get_json()
    assert body['success'] is True

    # check stock decreased
    with app.app_context():
        p1 = Product.query.get(p1.id)
        assert p1.stock_quantity == 3
