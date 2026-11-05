"""Regression tests for the production hardening changes."""
from app.extensions import db
from app.models.models import Product, ShippingAddress, User
from app.services.order_service import OrderService


def test_health_endpoint_reports_database(client):
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.get_json()['database'] == 'ok'


def test_order_idempotency_reuses_order_and_stock_once(app, test_user, test_product):
    with app.app_context():
        user = User.query.filter_by(email='test@example.com').first()
        product = Product.query.filter_by(name='Test Glasses').first()
        address = ShippingAddress(
            user_id=user.id,
            city='Cairo',
            full_address='1 Test Street',
            phone_number='01000000000',
        )
        db.session.add(address)
        db.session.commit()
        payload = [{
            'product_id': product.id,
            'quantity': 1,
            'prescription_id': None,
            'lens_type': '',
        }]

        first = OrderService.create_order(
            user.id, address.id, payload,
            idempotency_key='hardening-key',
            idempotency_fingerprint='fingerprint-a',
        )
        second = OrderService.create_order(
            user.id, address.id, payload,
            idempotency_key='hardening-key',
            idempotency_fingerprint='fingerprint-a',
        )

        assert first.id == second.id
        assert product.stock_quantity == 49


def test_cancelled_order_releases_stock_once(app, test_user, test_product):
    with app.app_context():
        user = User.query.filter_by(email='test@example.com').first()
        product = Product.query.filter_by(name='Test Glasses').first()
        address = ShippingAddress(
            user_id=user.id,
            city='Cairo',
            full_address='1 Test Street',
            phone_number='01000000000',
        )
        db.session.add(address)
        db.session.commit()
        order = OrderService.create_order(
            user.id,
            address.id,
            [{'product_id': product.id, 'quantity': 1, 'lens_type': ''}],
        )
        assert product.stock_quantity == 49

        OrderService.update_order_status(order, 'cancelled')
        OrderService.update_order_status(order, 'cancelled')
        db.session.refresh(product)
        assert product.stock_quantity == 50
