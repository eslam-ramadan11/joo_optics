"""Pytest configuration and fixtures for test suite."""
import os

# Must happen before any create_app() call (including from fixtures below) -
# the app factory's insecure-secret-key guard now fails closed by default
# (see app/__init__.py) and needs this to recognize a test run as safe,
# since app.config['TESTING'] = True in the app fixture below is set AFTER
# create_app() has already returned, too late for the guard check inside it.
os.environ.setdefault('FLASK_ENV', 'testing')

import pytest
from app import create_app
from app.extensions import db
from app.models.models import User
from app.services.auth_service import AuthService


@pytest.fixture
def app(tmp_path):
    """Create and configure a new app instance for each test."""
    db_path = (tmp_path / 'test.db').resolve()
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path.as_posix()}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """A test client for the app.
    
    Allows making HTTP requests to test endpoints.
    """
    return app.test_client()


@pytest.fixture
def runner(app):
    """A test CLI runner for the app.
    
    Allows testing CLI commands.
    """
    return app.test_cli_runner()


@pytest.fixture
def db_session(app):
    """Provide database session for tests."""
    with app.app_context():
        yield db.session


@pytest.fixture
def test_user(app):
    """Create a test user for authentication tests.
    
    Returns:
        User object with username='testuser' and email='test@example.com'
    """
    with app.app_context():
        user = AuthService.register_user(
            username='testuser',
            email='test@example.com',
            password='testpassword123'
        )
        return user


@pytest.fixture
def test_admin_user(app):
    """Create a test admin user for admin operation tests.
    
    Returns:
        User object with is_admin=True
    """
    with app.app_context():
        user = AuthService.register_user(
            username='testadmin',
            email='admin@example.com',
            password='adminpass123'
        )
        user.is_admin = True
        db.session.add(user)
        db.session.commit()
        return user


@pytest.fixture
def auth_headers(app, test_user):
    """Generate JWT authorization headers for a test user.
    
    Returns:
        Dictionary with Authorization header containing JWT token
    """
    from flask_jwt_extended import create_access_token
    
    with app.app_context():
        access_token = create_access_token(
            identity=test_user.id,
            additional_claims={'is_admin': False}
        )
        return {'Authorization': f'Bearer {access_token}'}


@pytest.fixture
def admin_auth_headers(app, test_admin_user):
    """Generate JWT authorization headers for a test admin user.
    
    Returns:
        Dictionary with Authorization header containing JWT token
    """
    from flask_jwt_extended import create_access_token
    
    with app.app_context():
        access_token = create_access_token(
            identity=test_admin_user.id,
            additional_claims={'is_admin': True}
        )
        return {'Authorization': f'Bearer {access_token}'}


@pytest.fixture
def test_product(app, test_user):
    """Create a test product.
    
    Returns:
        Product object with standard test data
    """
    from app.models.models import Product
    
    with app.app_context():
        product = Product(
            name='Test Glasses',
            price=99.99,
            category='glasses',
            image_file='test.jpg',
            colors='black,white',
            stock_quantity=50
        )
        db.session.add(product)
        db.session.commit()
        return product


@pytest.fixture
def test_order(app, test_user, test_product):
    """Create a test order.
    
    Returns:
        Order object with standard test data
    """
    from app.models.models import Order, ShippingAddress
    
    with app.app_context():
        # FIX: this used to pass address/state/zip_code, but the real
        # ShippingAddress model only has city/full_address/phone_number/
        # is_default - the old fixture would raise a TypeError immediately.
        address = ShippingAddress(
            user_id=test_user.id,
            city='Test City',
            full_address='123 Test St, Test City',
            phone_number='01000000000',
            is_default=True
        )
        db.session.add(address)
        db.session.flush()
        
        order = Order(
            user_id=test_user.id,
            address_id=address.id,
            total_amount=99.99
        )
        db.session.add(order)
        db.session.commit()
        return order


@pytest.fixture
def test_prescription(app, test_user):
    """Create a test prescription.
    
    Returns:
        Prescription object with standard test data
    """
    from app.models.models import Prescription
    
    with app.app_context():
        prescription = Prescription(
            user_id=test_user.id,
            image_file='test_prescription.jpg',
            sph_r=-1.0,
            cyl_r=-0.5,
            axis_r=90,
            sph_l=-1.5,
            cyl_l=-0.5,
            axis_l=180
        )
        db.session.add(prescription)
        db.session.commit()
        return prescription


@pytest.fixture
def test_payment(app, test_user, test_order):
    """Create a test payment.
    
    Returns:
        Payment object with standard test data
    """
    from app.models.models import Payment
    
    with app.app_context():
        payment = Payment(
            order_id=test_order.id,
            amount=99.99,
            payment_method='credit_card',
            payment_status='pending',
            transaction_id='test-transaction-id-123'
        )
        db.session.add(payment)
        db.session.commit()
        return payment


@pytest.fixture(autouse=True)
def reset_db(app):
    """Automatically reset database before each test.
    
    This ensures test isolation and prevents data leakage between tests.
    """
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield
        db.session.remove()


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "unit: mark test as a unit test")
    config.addinivalue_line("markers", "slow: mark test as slow")
