import io
import pytest

from app import create_app
from app.extensions import db
from app.models.models import User
from flask_jwt_extended import create_access_token


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
        PRESCRIPTIONS_UPLOAD_FOLDER = 'uploads_test/prescriptions'
        MAX_CONTENT_LENGTH = 1024 * 1024
        ALLOWED_PRESCRIPTION_EXTENSIONS = set(['png','jpg','jpeg'])

    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        u = User(username='u1', email='u1@example.com', password_hash='x')
        db.session.add(u)
        db.session.commit()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def get_auth_header(app, user_id):
    with app.app_context():
        token = create_access_token(identity=str(user_id), additional_claims={'is_admin': False})
        return {'Authorization': f'Bearer {token}'}


def test_upload_and_list_prescription(client, app):
    with app.app_context():
        user = User.query.filter_by(username='u1').first()
        headers = get_auth_header(app, user.id)

    data = {
        'sph_r': '1.0',
        'cyl_r': '0.5',
        'axis_r': '90',
        'sph_l': '1.25',
        'cyl_l': '0.0',
        'axis_l': '0'
    }
    # NOTE: PrescriptionService now verifies file content via magic bytes,
    # not just the .png extension, so the fixture needs real PNG header
    # bytes rather than arbitrary text.
    file_data = (io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'testimage'), 'presc.png')
    rv = client.post('/api/prescriptions', data={**data, 'file': file_data}, headers=headers, content_type='multipart/form-data')
    assert rv.status_code == 201
    body = rv.get_json()
    assert body['success'] is True

    # list
    rv = client.get('/api/prescriptions', headers=headers)
    assert rv.status_code == 200
    body = rv.get_json()
    assert body['success'] is True
    assert isinstance(body['data'], list)


# =======================================================================
# Value validation (axis 0-180, generous SPH/CYL bounds, no NaN/Infinity)
# =======================================================================

def _upload_payload(**overrides):
    data = {
        'sph_r': '1.0', 'cyl_r': '0.5', 'axis_r': '90',
        'sph_l': '1.25', 'cyl_l': '0.0', 'axis_l': '0',
    }
    data.update(overrides)
    return data


def _png_file():
    return (io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'testimage'), 'presc.png')


def test_axis_180_is_the_valid_upper_boundary(client, app):
    """180 degrees is a real, valid axis value - must not be rejected."""
    with app.app_context():
        user = User.query.filter_by(username='u1').first()
        headers = get_auth_header(app, user.id)

    data = _upload_payload(axis_r='180', axis_l='180')
    rv = client.post('/api/prescriptions', data={**data, 'file': _png_file()},
                      headers=headers, content_type='multipart/form-data')
    assert rv.status_code == 201, rv.get_data(as_text=True)


def test_axis_above_180_is_rejected(client, app):
    with app.app_context():
        user = User.query.filter_by(username='u1').first()
        headers = get_auth_header(app, user.id)

    data = _upload_payload(axis_r='181')
    rv = client.post('/api/prescriptions', data={**data, 'file': _png_file()},
                      headers=headers, content_type='multipart/form-data')
    assert rv.status_code == 400


def test_negative_axis_is_rejected(client, app):
    with app.app_context():
        user = User.query.filter_by(username='u1').first()
        headers = get_auth_header(app, user.id)

    data = _upload_payload(axis_l='-1')
    rv = client.post('/api/prescriptions', data={**data, 'file': _png_file()},
                      headers=headers, content_type='multipart/form-data')
    assert rv.status_code == 400


def test_extreme_sph_is_rejected(client, app):
    """Far beyond any real prescription - the wide margin (-30 to 30)
    still catches obviously-impossible input."""
    with app.app_context():
        user = User.query.filter_by(username='u1').first()
        headers = get_auth_header(app, user.id)

    data = _upload_payload(sph_r='999')
    rv = client.post('/api/prescriptions', data={**data, 'file': _png_file()},
                      headers=headers, content_type='multipart/form-data')
    assert rv.status_code == 400


def test_realistic_extreme_prescription_is_still_accepted(client, app):
    """A genuinely severe but real prescription must not be caught by
    the new bounds - they're deliberately generous."""
    with app.app_context():
        user = User.query.filter_by(username='u1').first()
        headers = get_auth_header(app, user.id)

    data = _upload_payload(sph_r='-18.0', cyl_r='-6.0', sph_l='-17.5', cyl_l='-5.75')
    rv = client.post('/api/prescriptions', data={**data, 'file': _png_file()},
                      headers=headers, content_type='multipart/form-data')
    assert rv.status_code == 201, rv.get_data(as_text=True)


def test_nan_sph_is_rejected(client, app):
    """A NaN value would otherwise silently corrupt lens-tier pricing
    (see lens_pricing.py) rather than being caught here explicitly."""
    with app.app_context():
        user = User.query.filter_by(username='u1').first()
        headers = get_auth_header(app, user.id)

    data = _upload_payload(sph_r='nan')
    rv = client.post('/api/prescriptions', data={**data, 'file': _png_file()},
                      headers=headers, content_type='multipart/form-data')
    assert rv.status_code == 400


# =======================================================================
# Error responses never leak raw exception text (server errors only -
# ordinary validation errors correctly keep their specific messages)
# =======================================================================

def test_unexpected_error_response_never_contains_raw_exception_text(client, app, monkeypatch):
    """Simulates a genuine unexpected failure (e.g. a DB error) during
    prescription creation - the response must show a safe, generic
    message, never the raw exception string."""
    with app.app_context():
        user = User.query.filter_by(username='u1').first()
        headers = get_auth_header(app, user.id)

    from app.services.prescription_service import PrescriptionService

    def boom(*args, **kwargs):
        raise RuntimeError('SECRET_INTERNAL_DETAIL: table prescriptions has no column x')

    monkeypatch.setattr(PrescriptionService, 'create_prescription', boom)

    data = _upload_payload()
    rv = client.post('/api/prescriptions', data={**data, 'file': _png_file()},
                      headers=headers, content_type='multipart/form-data')
    assert rv.status_code == 500
    body = rv.get_json()
    assert 'SECRET_INTERNAL_DETAIL' not in body['message']


def test_deleting_a_prescription_attached_to_an_order_is_refused_with_409(client, app):
    from app.models.models import (Prescription, ShippingAddress, Order, OrderItem, Product)

    with app.app_context():
        user = User.query.filter_by(username='u1').first()
        headers = get_auth_header(app, user.id)
        rx = Prescription(user_id=user.id, image_file='x.png', sph_r=1.0, cyl_r=0.0, axis_r=0,
                          sph_l=1.0, cyl_l=0.0, axis_l=0)
        addr = ShippingAddress(user_id=user.id, city='C', full_address='a', phone_number='1')
        prod = Product(name='P', price=100.0, category='men sunglasses', image_file='i.png',
                       colors='black', stock_quantity=5)
        db.session.add_all([rx, addr, prod])
        db.session.commit()
        order = Order(user_id=user.id, address_id=addr.id, total_amount=100.0)
        db.session.add(order)
        db.session.commit()
        db.session.add(OrderItem(order_id=order.id, product_id=prod.id, prescription_id=rx.id,
                                 quantity=1, item_price=100.0, lens_type='standard'))
        db.session.commit()
        rx_id = rx.id

    resp = client.delete(f'/api/prescriptions/{rx_id}', headers=headers)
    assert resp.status_code == 409

    with app.app_context():
        assert Prescription.query.get(rx_id) is not None


def _upload_png(client, headers):
    data = {'sph_r': '1.0', 'cyl_r': '0.5', 'axis_r': '90', 'sph_l': '1.25', 'cyl_l': '0.0', 'axis_l': '0'}
    file_data = (io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'testimage'), 'presc.png')
    rv = client.post('/api/prescriptions', data={**data, 'file': file_data}, headers=headers,
                     content_type='multipart/form-data')
    assert rv.status_code == 201, rv.get_data(as_text=True)
    return rv.get_json()['data']['id']


def test_owner_can_open_their_uploaded_prescription_file(client, app):
    """The /file endpoint was never tested: with a relative upload folder
    (as in .env) send_file() looked in the wrong directory and every
    download failed."""
    with app.app_context():
        user = User.query.filter_by(username='u1').first()
        headers = get_auth_header(app, user.id)
    rx_id = _upload_png(client, headers)

    rv = client.get(f'/api/prescriptions/{rx_id}/file', headers=headers)
    assert rv.status_code == 200, rv.get_data(as_text=True)
    assert rv.data.startswith(b'\x89PNG')


def test_admin_can_open_a_customers_prescription_file_and_stranger_cannot(client, app):
    with app.app_context():
        owner = User.query.filter_by(username='u1').first()
        admin = User(username='adm', email='adm@example.com', password_hash='x', is_admin=True)
        stranger = User(username='str', email='str@example.com', password_hash='x')
        db.session.add_all([admin, stranger])
        db.session.commit()
        owner_headers = get_auth_header(app, owner.id)
        admin_headers = get_auth_header(app, admin.id)
        stranger_headers = get_auth_header(app, stranger.id)
    rx_id = _upload_png(client, owner_headers)

    ok = client.get(f'/api/prescriptions/{rx_id}/file', headers=admin_headers)
    assert ok.status_code == 200
    assert ok.data.startswith(b'\x89PNG')

    denied = client.get(f'/api/prescriptions/{rx_id}/file', headers=stranger_headers)
    assert denied.status_code == 403


def test_file_stored_with_a_relative_path_from_an_older_upload_still_opens(client, app, tmp_path, monkeypatch):
    from app.models.models import Prescription

    monkeypatch.chdir(tmp_path)
    (tmp_path / 'uploads' / 'prescriptions').mkdir(parents=True)
    (tmp_path / 'uploads' / 'prescriptions' / 'old.png').write_bytes(b'\x89PNG\r\n\x1a\n' + b'old')
    with app.app_context():
        user = User.query.filter_by(username='u1').first()
        headers = get_auth_header(app, user.id)
        rx = Prescription(user_id=user.id, image_file='uploads/prescriptions/old.png',
                          sph_r=1.0, cyl_r=0.0, axis_r=0, sph_l=1.0, cyl_l=0.0, axis_l=0)
        db.session.add(rx)
        db.session.commit()
        rx_id = rx.id

    rv = client.get(f'/api/prescriptions/{rx_id}/file', headers=headers)
    assert rv.status_code == 200
    assert rv.data.startswith(b'\x89PNG')
