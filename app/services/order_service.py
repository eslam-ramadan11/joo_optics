"""Order service for handling all order operations."""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from decimal import Decimal
from flask import current_app

from app.extensions import db
from app.models.models import Order, OrderItem, Product, ShippingAddress, Prescription
from app.services import lens_pricing, coupon_service


class OrderService:
    """Service layer for order management and processing."""

    @staticmethod
    def _lock_and_validate_items(items: List[Dict[str, Any]]) -> Dict[int, Product]:
        """Lock the relevant product rows and validate stock availability.

        SECURITY / CORRECTNESS: uses SELECT ... FOR UPDATE (via with_for_update)
        so two concurrent orders for the same product can't both read the same
        stock_quantity and oversell it (TOCTOU race condition).

        Returns:
            Mapping of product_id -> locked Product row.

        Raises:
            ValueError: If a product doesn't exist or has insufficient stock.
        """
        product_ids = {int(it['product_id']) for it in items}
        # Order the ids to lock rows in a consistent order across concurrent
        # transactions and avoid deadlocks.
        locked = {
            p.id: p
            for p in Product.query.filter(Product.id.in_(product_ids))
            .order_by(Product.id.asc())
            .with_for_update()
            .all()
        }

        needed: Dict[int, int] = {}
        for it in items:
            pid = int(it['product_id'])
            qty = int(it.get('quantity', 1))
            if qty < 1:
                raise ValueError('quantity must be at least 1')
            needed[pid] = needed.get(pid, 0) + qty

        for pid, qty in needed.items():
            product = locked.get(pid)
            if not product:
                raise ValueError(f'product {pid} not found')
            if product.stock_quantity < qty:
                raise ValueError(f'insufficient stock for product {pid}')

        return locked

    @staticmethod
    def _validate_ownership(user_id: int, address_id: int, items: List[Dict[str, Any]]) -> Dict[int, Prescription]:
        """Verify the shipping address and every prescription referenced
        actually belong to the requesting user.

        SECURITY: without this check a user could place an order using
        another user's shipping address or prescription (IDOR).

        Returns:
            Mapping of prescription_id -> Prescription, for the tier-based
            lens pricing lookup in create_order.

        Raises:
            ValueError: If the address or any prescription doesn't belong to the user.
        """
        address = ShippingAddress.query.filter_by(id=address_id, user_id=user_id).first()
        if not address:
            raise ValueError('shipping address not found')

        prescription_ids = {int(it['prescription_id']) for it in items if it.get('prescription_id') is not None}
        prescriptions: Dict[int, Prescription] = {}
        if prescription_ids:
            owned = Prescription.query.filter(
                Prescription.id.in_(prescription_ids),
                Prescription.user_id == user_id,
            ).all()
            prescriptions = {p.id: p for p in owned}
            if len(prescriptions) != len(prescription_ids):
                raise ValueError('one or more prescriptions not found')
        return prescriptions

    @staticmethod
    def create_order(
        user_id: int,
        address_id: int,
        items: List[Dict[str, Any]],
        coupon_code: Optional[str] = None,
        attribution: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        idempotency_fingerprint: Optional[str] = None,
    ) -> Order:
        """Create a new order with automatic stock reservation and server-computed pricing.

        Args:
            user_id: The user ID placing the order.
            address_id: The shipping address ID (must belong to user_id).
            items: List of items with product_id, prescription_id, quantity.
                Any item_price supplied by the caller is ignored — the price
                is always the current Product.price at order time.
            coupon_code: Optional discount code. Re-validated here from
                scratch (never trusts a discount amount from the client) -
                this is the point where a coupon's use actually counts
                against its usage limits, since it's tied to a real created
                order (see coupon_service for how "uses" are counted).
            attribution: Optional dict of marketing attribution fields
                (utm_source, utm_medium, utm_campaign, utm_content, utm_term,
                fbp, fbc, ga4_client_id) - stored as-is on the order for
                later reporting (see tracking_service.py). Never affects
                pricing, validation, or any other order-creation behavior;
                purely informational.

        Returns:
            The created Order object.

        Raises:
            ValueError: If validation fails (ownership, stock, missing product,
                invalid/expired/exhausted coupon, etc).
        """
        if not items:
            raise ValueError('at least one item required')

        try:
            if idempotency_key:
                existing = Order.query.filter_by(idempotency_key=idempotency_key).first()
                if existing:
                    if existing.user_id != user_id:
                        raise ValueError('idempotency key already belongs to another user')
                    if existing.idempotency_fingerprint != idempotency_fingerprint:
                        raise ValueError('idempotency key was already used with different order data')
                    return existing

            owned_prescriptions = OrderService._validate_ownership(user_id, address_id, items)
            locked_products = OrderService._lock_and_validate_items(items)

            total = Decimal('0.00')
            order_items_data = []
            priced_items = []  # for coupon eligibility calculation only - see below
            for it in items:
                pid = int(it['product_id'])
                qty = int(it.get('quantity', 1))
                product = locked_products[pid]
                lens_type = (it.get('lens_type') or '').strip()
                prescription_id = it.get('prescription_id')
                prescription_id = int(prescription_id) if prescription_id is not None else None

                # Business rule: ordering an actual lens type means you're
                # getting prescription lenses fitted, which requires a
                # prescription on file. An item with no lens_type (plain
                # frames/sunglasses as-is) does not.
                if lens_type and prescription_id is None:
                    raise ValueError(f'a prescription is required to order "{lens_type}" lenses')

                lens_price = Decimal('0.00')
                if lens_type:
                    prescription = owned_prescriptions[prescription_id]
                    tier = lens_pricing.calculate_tier(
                        prescription.sph_r, prescription.cyl_r,
                        prescription.sph_l, prescription.cyl_l,
                    )
                    price = lens_pricing.get_price(lens_type, tier)
                    if price is None:
                        # Either the prescription is out of the standard
                        # pricing range, or this specific lens/tier
                        # combination isn't offered - either way, this
                        # can't be auto-priced. Direct the customer to
                        # WhatsApp instead of guessing a number.
                        raise ValueError(
                            f'"{lens_type}" cannot be priced automatically for this prescription - '
                            f'please contact us on WhatsApp ({lens_pricing.WHATSAPP_NUMBER}) for a manual quote'
                        )
                    lens_price = Decimal(str(price))

                # SECURITY: price always comes from the server-side Product
                # record and the server-side lens price table, never from
                # client input. BUG FIX: the lens price used to be dropped
                # entirely - the customer was only ever charged for the
                # frame, regardless of which lens type they picked.
                unit_price = Decimal(str(product.price)) + lens_price
                total += unit_price * qty
                product.stock_quantity -= qty
                db.session.add(product)
                order_items_data.append({
                    'product_id': pid,
                    'prescription_id': prescription_id,
                    # lens_type is nullable=False on the model (an empty
                    # string means "no lens/not applicable"), but the
                    # schema allows None, so normalize None -> '' here.
                    'lens_type': lens_type,
                    'quantity': qty,
                    'item_price': float(unit_price),
                })
                # Additive only - for coupon eligibility math, doesn't
                # affect lens_price/unit_price/total above in any way.
                priced_items.append({
                    'product_id': pid,
                    'category': product.category,
                    'quantity': qty,
                    'frame_price': float(product.price),
                    'lens_price': float(lens_price),
                })

            discount_amount = Decimal('0.00')
            coupon_id = None
            if coupon_code:
                coupon, discount, error = coupon_service.validate_and_calculate(
                    coupon_code, user_id, priced_items, lock=True
                )
                if error:
                    raise ValueError(error)
                discount_amount = Decimal(str(discount))
                coupon_id = coupon.id
                total -= discount_amount

            attribution = attribution or {}
            attribution_fields = {
                key: attribution.get(key)
                for key in ('utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'fbp', 'fbc', 'ga4_client_id')
            }

            order = Order(
                user_id=user_id,
                idempotency_key=idempotency_key,
                idempotency_fingerprint=idempotency_fingerprint,
                address_id=address_id,
                total_amount=float(total),
                coupon_id=coupon_id,
                discount_amount=float(discount_amount),
                stock_reserved_until=datetime.utcnow() + timedelta(
                    minutes=current_app.config.get('STOCK_RESERVATION_MINUTES', 30)
                ),
                **attribution_fields,
            )
            db.session.add(order)
            db.session.flush()

            for oi_data in order_items_data:
                db.session.add(OrderItem(order_id=order.id, **oi_data))

            db.session.commit()
            return order
        except Exception:
            db.session.rollback()
            raise

    @staticmethod
    def list_orders(user_id: Optional[int] = None) -> List[Order]:
        """List orders, optionally filtered by user."""
        q = Order.query
        if user_id:
            q = q.filter(Order.user_id == user_id)
        return q.order_by(Order.date_posted.desc()).all()

    @staticmethod
    def release_expired_reservations() -> int:
        """Release stock held by unpaid orders past their reservation window.

        This method is intentionally explicit so it can be called from a
        scheduler, cron job, or a one-shot maintenance command.
        """
        now = datetime.utcnow()
        orders = Order.query.filter(
            Order.status == 'pending',
            Order.stock_reserved_until.is_not(None),
            Order.stock_reserved_until <= now,
            Order.stock_released_at.is_(None),
        ).with_for_update().all()
        released = 0
        for order in orders:
            if order.payment and order.payment.payment_status == 'completed':
                continue
            for item in order.order_items:
                product = Product.query.filter_by(id=item.product_id).with_for_update().first()
                if product:
                    product.stock_quantity += item.quantity
                    db.session.add(product)
            order.stock_released_at = now
            order.status = 'cancelled'
            if order.payment and order.payment.payment_status in ('pending', 'failed'):
                order.payment.payment_status = 'cancelled'
                db.session.add(order.payment)
            db.session.add(order)
            released += 1
        db.session.commit()
        return released

    @staticmethod
    def get_order(order_id: int) -> Optional[Order]:
        """Retrieve an order by ID."""
        return Order.query.get(order_id)

    @staticmethod
    def update_order_status(order: Order, status: str) -> Order:
        """Update order status.

        If the order is being cancelled and it has a payment that never
        went through (still pending, or already failed), that payment is
        cancelled too - otherwise it's left dangling in a state that no
        longer matches reality. A payment that's already completed is
        never touched here: the order can still be marked cancelled (e.g.
        the customer no longer wants a paid item), but reversing a
        completed payment means issuing an actual refund, not just
        flipping a status flag.
        """
        previous_status = order.status
        order.status = status
        db.session.add(order)

        if status == 'cancelled' and order.payment and order.payment.payment_status in ('pending', 'failed'):
            order.payment.payment_status = 'cancelled'
            db.session.add(order.payment)
        if status == 'cancelled' and previous_status != 'cancelled' and order.stock_released_at is None:
            for item in order.order_items:
                product = Product.query.filter_by(id=item.product_id).with_for_update().first()
                if product:
                    product.stock_quantity += item.quantity
                    db.session.add(product)
            order.stock_released_at = datetime.utcnow()
            db.session.add(order)

        db.session.commit()
        return order

    @staticmethod
    def delete_order(order: Order) -> None:
        """Delete an order and restore stock quantities."""
        try:
            if order.stock_released_at is None:
                for item in order.order_items:
                    product = Product.query.filter_by(id=item.product_id).with_for_update().first()
                    if product:
                        product.stock_quantity += item.quantity
                        db.session.add(product)
                order.stock_released_at = datetime.utcnow()
                db.session.add(order)
            db.session.delete(order)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
