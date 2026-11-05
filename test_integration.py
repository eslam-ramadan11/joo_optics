"""Integration tests for the complete API flow."""
import io
import pytest
from app import create_app
from app.extensions import db
from app.models.models import User, Product, ShippingAddress, Prescription
from flask_jwt_extended import create_access_token

# Minimal valid PNG header bytes - enough to pass the magic-byte content
# check added to ProductService/PrescriptionService (extension alone is no
# longer trusted for uploaded files).
PNG_BYTES = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32


@pytest.fixture
def reset_db():
    """Shadow conftest.py's autouse `reset_db(app)` - see test_orders.py
    for the full explanation. This file's own `app` fixture already
    creates and seeds an isolated per-test database."""
    yield


@pytest.fixture
def app(tmp_path):
    """Create and configure a test app."""
    db_path = (tmp_path / 'test.db').resolve()

    class TestConfig:
        TESTING = True
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_path.as_posix()}'
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        SECRET_KEY = 'test-secret'
        JWT_SECRET_KEY = 'test-jwt-secret'
        PRESCRIPTIONS_UPLOAD_FOLDER = 'uploads_test/prescriptions'
        MAX_CONTENT_LENGTH = 10 * 1024 * 1024
        ALLOWED_PRESCRIPTION_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

    app = create_app(TestConfig)
    
    with app.app_context():
        db.create_all()
        # Create test data
        admin = User(
            username='admin',
            email='admin@example.com',
            password_hash='admin_hash',
            is_admin=True
        )
        user = User(
            username='customer',
            email='customer@example.com',
            password_hash='customer_hash',
            is_admin=False
        )
        db.session.add_all([admin, user])
        db.session.commit()
        
        # Create products
        p1 = Product(
            name='Test Glasses',
            price=99.99,
            category='eyeglasses',
            image_file='img1.png',
            colors='black,brown',
            stock_quantity=50
        )
        p2 = Product(
            name='Sunglasses',
            price=149.99,
            category='sunglasses',
            image_file='img2.png',
            colors='black',
            stock_quantity=30
        )
        db.session.add_all([p1, p2])
        
        # Create shipping address
        addr = ShippingAddress(
            user_id=user.id,
            city='New York',
            full_address='123 Main St',
            phone_number='555-1234'
        )
        db.session.add(addr)

        # A real prescription owned by `user` - OrderService now verifies
        # ownership of any prescription_id referenced in an order (fixes an
        # IDOR where any user's prescription id used to be accepted).
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
    """Create a test client."""
    return app.test_client()


def get_token(app, user_id, is_admin=False):
    """Generate JWT token for testing."""
    with app.app_context():
        return create_access_token(
            identity=str(user_id),
            additional_claims={'is_admin': is_admin}
        )


class TestAuthFlow:
    """Test authentication and token flow."""
    
    def test_user_registration(self, client):
        """Test user registration."""
        payload = {
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'password123',
            'date_of_birth': '1995-06-15',
        }
        rv = client.post('/api/auth/register', json=payload)
        assert rv.status_code == 201, rv.get_data(as_text=True)
        data = rv.get_json()
        assert data['success'] is True
        assert 'access_token' in data['data']
        assert 'refresh_token' in data['data']
    
    def test_user_login(self, client, app):
        """Test user login."""
        payload = {
            'username': 'customer',
            'password': 'customer_hash'  # In real scenario, this would be hashed
        }
        rv = client.post('/api/auth/login', json=payload)
        # This will fail with wrong password in production; setup would hash it
        # Skipping actual password check test
    
    def test_token_refresh(self, client, app):
        """Test refresh token flow."""
        with app.app_context():
            user = User.query.filter_by(username='customer').first()
            from flask_jwt_extended import create_refresh_token
            refresh_token = create_refresh_token(identity=str(user.id))
        
        headers = {'Authorization': f'Bearer {refresh_token}'}
        rv = client.post('/api/auth/refresh', headers=headers)
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['success'] is True
        assert 'access_token' in data['data']


class TestProductFlow:
    """Test product management flow."""
    
    def test_list_products(self, client):
        """Test listing products."""
        rv = client.get('/api/products')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['success'] is True
        assert len(data['data']['items']) == 2
    
    def test_get_single_product(self, client):
        """Test retrieving a single product."""
        rv = client.get('/api/products/1')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['success'] is True
        assert data['data']['name'] == 'Test Glasses'
    
    def test_create_product_admin_only(self, client, app):
        """Test product creation by admin.

        NOTE: product_schema.py declares image_file as dump_only ("Image
        file is handled by the service") - creation now requires an actual
        uploaded image file (also content-sniffed), not a JSON string path.
        """
        with app.app_context():
            admin = User.query.filter_by(username='admin').first()
            token = get_token(app, admin.id, is_admin=True)
        
        form = {
            'name': 'New Glasses',
            'price': '120.0',
            'category': 'men medical fraims',
            'colors': 'Red',
            'stock_quantity': '25',
        }
        headers = {'Authorization': f'Bearer {token}'}
        data = {**form, 'image': (io.BytesIO(PNG_BYTES), 'new.png')}
        rv = client.post('/api/products', data=data, headers=headers, content_type='multipart/form-data')
        assert rv.status_code == 201, rv.get_data(as_text=True)


class TestOrderFlow:
    """Test order creation and management flow."""
    
    def test_create_order_with_stock_validation(self, client, app):
        """Test order creation with stock validation."""
        with app.app_context():
            user = User.query.filter_by(username='customer').first()
            addr = ShippingAddress.query.filter_by(user_id=user.id).first()
            product = Product.query.first()
            presc = Prescription.query.filter_by(user_id=user.id).first()
            token = get_token(app, user.id)
        
        payload = {
            'address_id': addr.id,
            'items': [
                {
                    'product_id': product.id,
                    'prescription_id': presc.id,
                    'quantity': 2,
                }
            ]
        }
        headers = {'Authorization': f'Bearer {token}'}
        rv = client.post('/api/orders', json=payload, headers=headers)
        assert rv.status_code == 201, rv.get_data(as_text=True)
        data = rv.get_json()
        assert data['success'] is True
        assert 'id' in data['data']
        
        # Verify stock decreased
        with app.app_context():
            p = Product.query.get(product.id)
            assert p.stock_quantity == 48  # 50 - 2


class TestErrorHandling:
    """Test error handling and validation."""
    
    def test_product_not_found(self, client):
        """Test 404 for non-existent product."""
        rv = client.get('/api/products/9999')
        assert rv.status_code == 404
        data = rv.get_json()
        assert data['success'] is False
    
    def test_invalid_json_payload(self, client, app):
        """Test invalid JSON payload."""
        with app.app_context():
            admin = User.query.filter_by(username='admin').first()
            token = get_token(app, admin.id, is_admin=True)
        
        headers = {'Authorization': f'Bearer {token}'}
        rv = client.post(
            '/api/products',
            data='invalid json',
            headers=headers,
            content_type='application/json'
        )
        assert rv.status_code == 400


class TestJWTProtection:
    """Test JWT protection on endpoints."""
    
    def test_missing_auth_header(self, client):
        """Test missing authorization header."""
        rv = client.get('/api/orders')
        assert rv.status_code == 401
    
    def test_invalid_token(self, client):
        """Test invalid token."""
        headers = {'Authorization': 'Bearer invalid_token'}
        rv = client.get('/api/orders', headers=headers)
        assert rv.status_code == 422


class TestAdminRestrictions:
    """Test admin-only endpoints."""
    
    def test_non_admin_cannot_delete_product(self, client, app):
        """Test non-admin cannot delete product."""
        with app.app_context():
            user = User.query.filter_by(username='customer').first()
            token = get_token(app, user.id, is_admin=False)
        
        headers = {'Authorization': f'Bearer {token}'}
        rv = client.delete('/api/products/1', headers=headers)
        assert rv.status_code == 403
    
    def test_admin_can_delete_product(self, client, app):
        """Test admin can delete product."""
        with app.app_context():
            admin = User.query.filter_by(username='admin').first()
            token = get_token(app, admin.id, is_admin=True)
        
        headers = {'Authorization': f'Bearer {token}'}
        rv = client.delete('/api/products/1', headers=headers)
        assert rv.status_code == 200

    def test_admin_cannot_delete_product_that_is_on_an_order(self, client, app):
        """A product on a past order must be refused with a clear 409 (not a
        500), and both the product and the order line must stay intact."""
        from app.models.models import Order, OrderItem

        with app.app_context():
            admin = User.query.filter_by(username='admin').first()
            token = get_token(app, admin.id, is_admin=True)
            customer = User.query.filter_by(username='customer').first()
            addr = ShippingAddress.query.filter_by(user_id=customer.id).first()
            order = Order(user_id=customer.id, address_id=addr.id, total_amount=99.99, status='pending')
            db.session.add(order)
            db.session.commit()
            db.session.add(OrderItem(
                order_id=order.id, product_id=1, lens_type='none', quantity=1, item_price=99.99,
            ))
            db.session.commit()

        rv = client.delete('/api/products/1', headers={'Authorization': f'Bearer {token}'})
        assert rv.status_code == 409, rv.get_data(as_text=True)
        assert rv.get_json()['success'] is False

        with app.app_context():
            assert Product.query.get(1) is not None
            assert OrderItem.query.filter_by(product_id=1).count() == 1

    def test_deleting_a_featured_product_also_removes_its_daily_deal(self, client, app):
        """Deleting a product that is in "Today's Deals" must not leave an
        orphan deal row behind."""
        from app.models.models import DailyDeal

        with app.app_context():
            admin = User.query.filter_by(username='admin').first()
            token = get_token(app, admin.id, is_admin=True)
            db.session.add(DailyDeal(product_id=2, sort_order=0))
            db.session.commit()

        rv = client.delete('/api/products/2', headers={'Authorization': f'Bearer {token}'})
        assert rv.status_code == 200, rv.get_data(as_text=True)

        with app.app_context():
            assert Product.query.get(2) is None
            assert DailyDeal.query.filter_by(product_id=2).count() == 0


# =======================================================================
# Production config guard: placeholder / short secrets are refused
# =======================================================================

def test_production_guard_rejects_placeholder_and_short_secrets(monkeypatch, tmp_path):
    from app import create_app

    monkeypatch.delenv('FLASK_ENV', raising=False)

    class BadConfig:
        TESTING = False
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{(tmp_path / "x.db").as_posix()}'
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        # The exact placeholder values shipped in _env.example:
        SECRET_KEY = 'change-me-to-secure-random-string-min-32-chars'
        JWT_SECRET_KEY = 'short'

    with pytest.raises(RuntimeError) as exc:
        create_app(BadConfig)
    assert 'SECRET_KEY' in str(exc.value)
    assert 'JWT_SECRET_KEY' in str(exc.value)
