from datetime import datetime

from app.extensions import db


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    token_version = db.Column(db.Integer, nullable=False, default=0)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    # Nullable at the DB level so existing accounts created before this
    # column existed aren't broken - but the registration endpoint now
    # requires it for every new signup going forward.
    date_of_birth = db.Column(db.Date, nullable=True)

    shipping_addresses = db.relationship(
        'ShippingAddress',
        backref='user',
        lazy=True,
        cascade='all, delete-orphan',
    )
    prescriptions = db.relationship(
        'Prescription',
        backref='user',
        lazy=True,
        cascade='all, delete-orphan',
    )
    orders = db.relationship(
        'Order',
        backref='user',
        lazy=True,
        cascade='all, delete-orphan',
    )

    def __repr__(self):
        return f'<User {self.id} {self.username!r}>'


class ShippingAddress(db.Model):
    __tablename__ = 'shipping_addresses'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    city = db.Column(db.String(100), nullable=False)
    full_address = db.Column(db.String(255), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    is_default = db.Column(db.Boolean, default=False, nullable=False)

    def __repr__(self):
        return f'<ShippingAddress {self.id} user_id={self.user_id} city={self.city!r}>'


class Prescription(db.Model):
    __tablename__ = 'prescriptions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    image_file = db.Column(db.String(255), nullable=False)
    sph_r = db.Column(db.Float, nullable=False)
    cyl_r = db.Column(db.Float, nullable=False)
    axis_r = db.Column(db.Integer, nullable=False)
    sph_l = db.Column(db.Float, nullable=False)
    cyl_l = db.Column(db.Float, nullable=False)
    axis_l = db.Column(db.Integer, nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    order_items = db.relationship('OrderItem', backref='prescription', lazy=True)

    def __repr__(self):
        return f'<Prescription {self.id} user_id={self.user_id}>'


class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    price = db.Column(db.Float, nullable=False)
    old_price = db.Column(db.Float, nullable=True)
    category = db.Column(db.String(80), nullable=False)
    image_file = db.Column(db.String(255), nullable=False)
    discount_badge = db.Column(db.String(50), nullable=True)
    colors = db.Column(db.String(500), nullable=False)
    stock_quantity = db.Column(db.Integer, nullable=False, default=0)

    order_items = db.relationship('OrderItem', backref='product', lazy=True)
    images = db.relationship(
        'ProductImage', backref='product', lazy=True,
        order_by='ProductImage.sort_order', cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<Product {self.id} {self.name!r}>'


class ProductImage(db.Model):
    """Extra images for a product's detail page gallery.

    `color` is nullable: rows with color=None are general/default images
    (shown regardless of which color, if any, is selected). Rows with a
    color set are only shown when that specific color swatch is active.
    Product.image_file (the single required image on the model above)
    remains the one used for grid/listing cards - this table is additive,
    purely for the detail page gallery.
    """
    __tablename__ = 'product_images'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    color = db.Column(db.String(50), nullable=True)
    image_file = db.Column(db.String(255), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    def __repr__(self):
        return f'<ProductImage {self.id} product_id={self.product_id} color={self.color!r}>'


class DailyDeal(db.Model):
    """A product curated by the admin for the homepage 'Today's Deals'
    section. Deliberately separate from Product itself: which products
    are featured here is a day-to-day merchandising decision, not a
    product attribute, and this table can be cleared/repopulated daily
    without touching product rows at all. sort_order controls the
    display order (lower shows first) and is fully admin-controlled.
    """
    __tablename__ = 'daily_deals'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, unique=True, index=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    added_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    product = db.relationship('Product')

    def __repr__(self):
        return f'<DailyDeal {self.id} product_id={self.product_id}>'


class DealsCountdown(db.Model):
    """A single, admin-controlled end time for the homepage 'Today's
    Deals' session (see DailyDeal above). Deliberately a singleton (the
    app always reads/writes the one row with the lowest id, creating it
    on first use) rather than per-deal expiration - the admin runs one
    flash-sale countdown for the whole section at a time, not a
    different timer per product.

    ends_at = None means no countdown is active - the deals section
    shows indefinitely (until the admin removes the products themselves
    via DailyDeal). Once ends_at passes, the public /api/deals endpoint
    stops returning any products (see app/routes/deals.py) even though
    the DailyDeal rows themselves are left untouched, so the admin can
    start a new countdown later and get the same curated list back
    without re-adding every product.
    """
    __tablename__ = 'deals_countdown'

    id = db.Column(db.Integer, primary_key=True)
    ends_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<DealsCountdown ends_at={self.ends_at}>'


class Coupon(db.Model):
    """A discount coupon, created and managed from the admin panel.

    code is stored uppercase so comparisons are case-insensitive without
    needing a separate normalized column - always uppercase the code
    before querying (CouponService.normalize_code does this).

    apply_to controls which part of an order is eligible for the discount:
    'all'/'cart' - the whole order; 'specific_products' - only the products
    listed in apply_to_value (comma-separated product ids); 'category' -
    only products whose category matches apply_to_value; 'lenses_only' /
    'frames_only' - only the lens or frame portion of eligible items'
    prices (the lens portion is computed via app.services.lens_pricing,
    never modified by this feature).
    """
    __tablename__ = 'coupons'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    discount_type = db.Column(db.String(20), nullable=False)  # 'percentage' | 'fixed'
    discount_value = db.Column(db.Float, nullable=False)

    start_date = db.Column(db.DateTime, nullable=True)  # null = active immediately
    end_date = db.Column(db.DateTime, nullable=True)     # null = never expires
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    max_total_uses = db.Column(db.Integer, nullable=True)         # null = unlimited
    max_uses_per_customer = db.Column(db.Integer, nullable=True)  # null = unlimited

    apply_to = db.Column(db.String(30), nullable=False, default='all')
    apply_to_value = db.Column(db.String(500), nullable=True)

    min_order_amount = db.Column(db.Float, nullable=True)
    max_discount_amount = db.Column(db.Float, nullable=True)  # only meaningful for 'percentage'

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    orders = db.relationship('Order', backref='coupon', lazy=True)

    def __repr__(self):
        return f'<Coupon {self.id} {self.code!r}>'


class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    idempotency_key = db.Column(db.String(128), nullable=True, unique=True, index=True)
    idempotency_fingerprint = db.Column(db.String(64), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    address_id = db.Column(
        db.Integer,
        db.ForeignKey('shipping_addresses.id'),
        nullable=False,
        index=True,
    )
    status = db.Column(db.String(50), nullable=False, default='pending')
    total_amount = db.Column(db.Float, nullable=False)
    # Coupon fields: nullable, so every existing order (and any order with
    # no coupon applied) is unaffected. coupon_id is kept even if the
    # coupon is later deleted from possible reuse (SET NULL, not CASCADE)
    # so order history stays intact - discount_amount is preserved either
    # way as the historical record of what was actually discounted.
    coupon_id = db.Column(db.Integer, db.ForeignKey('coupons.id', ondelete='SET NULL'), nullable=True, index=True)
    discount_amount = db.Column(db.Float, nullable=False, default=0.0)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # --- Marketing attribution (all nullable - captured client-side at
    # checkout time if present, never required, never blocks order
    # creation if missing or malformed). See app/services/tracking_service.py
    # for how these are used.
    utm_source = db.Column(db.String(255), nullable=True)
    utm_medium = db.Column(db.String(255), nullable=True)
    utm_campaign = db.Column(db.String(255), nullable=True)
    utm_content = db.Column(db.String(255), nullable=True)
    utm_term = db.Column(db.String(255), nullable=True)
    # Meta's own browser-id / click-id cookies (fbp/fbc) - standard
    # Conversions API parameters that improve match quality without
    # containing any personal data themselves.
    fbp = db.Column(db.String(255), nullable=True)
    fbc = db.Column(db.String(255), nullable=True)
    # GA4's client_id, so a server-side Measurement Protocol event can be
    # attributed to the same GA4 session as the customer's on-site journey.
    ga4_client_id = db.Column(db.String(255), nullable=True)

    # --- Purchase-tracking idempotency (see tracking_service.py) ---
    # Set once, atomically, the first time the backend confirms this order
    # is genuinely paid and reports it server-side to Meta CAPI / GA4
    # Measurement Protocol. Never re-fired after this is set, regardless
    # of duplicate webhooks or repeated confirmation checks.
    purchase_tracked_at = db.Column(db.DateTime, nullable=True)
    # Set once, atomically, the first time the frontend is told "yes, fire
    # your client-side Pixel/gtag Purchase event for this order" - separate
    # from purchase_tracked_at because the two are asked at different times
    # by different parties (server-side event triggers vs. the customer's
    # browser polling the result page), but both need their own one-time
    # guard so a page refresh can never cause a second client-side fire.
    purchase_client_notified_at = db.Column(db.DateTime, nullable=True)
    stock_released_at = db.Column(db.DateTime, nullable=True)
    stock_reserved_until = db.Column(db.DateTime, nullable=True, index=True)

    shipping_address = db.relationship('ShippingAddress', backref='orders')
    order_items = db.relationship(
        'OrderItem',
        backref='order',
        lazy=True,
        cascade='all, delete-orphan',
    )
    payment = db.relationship(
        'Payment',
        backref='order',
        uselist=False,
        cascade='all, delete-orphan',
    )
    payment_attempts = db.relationship(
        'PaymentAttempt',
        backref='order',
        lazy=True,
        cascade='all, delete-orphan',
    )

    def __repr__(self):
        return f'<Order {self.id} user_id={self.user_id} status={self.status!r}>'


class OrderItem(db.Model):
    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    # FIX: was nullable=False, forcing every single order item - even a
    # plain pair of sunglasses with no prescription lenses - to have a
    # prescription attached. Now optional: an item only needs one when the
    # customer is actually ordering prescription lenses for it.
    prescription_id = db.Column(
        db.Integer,
        db.ForeignKey('prescriptions.id'),
        nullable=True,
        index=True,
    )
    lens_type = db.Column(db.String(80), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    item_price = db.Column(db.Float, nullable=False)

    def __repr__(self):
        return (
            f'<OrderItem {self.id} order_id={self.order_id} '
            f'product_id={self.product_id} prescription_id={self.prescription_id}>'
        )


class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer,
        db.ForeignKey('orders.id'),
        nullable=False,
        unique=True,
        index=True,
    )
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    payment_status = db.Column(db.String(50), nullable=False, default='pending')
    transaction_id = db.Column(db.String(100), unique=True, nullable=True)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    # Paymob's own order id, returned from their order-registration API.
    # Stored so the webhook (which reports Paymob's order.id) can be matched
    # back to our order without trusting anything else from the callback.
    paymob_order_id = db.Column(db.String(50), nullable=True, index=True, unique=True)
    # Cached iframe_url + when it was issued, for idempotency: a
    # double-click or concurrent retry within the token's lifetime reuses
    # this instead of registering a brand new order with Paymob (see
    # PaymentService.initiate_paymob_payment / PAYMOB_TOKEN_LIFETIME_SECONDS).
    paymob_iframe_url = db.Column(db.Text, nullable=True)
    paymob_token_issued_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f'<Payment {self.id} order_id={self.order_id} status={self.payment_status!r}>'


class PaymentAttempt(db.Model):
    """Immutable Paymob attempt metadata used to reconcile late webhooks."""

    __tablename__ = 'payment_attempts'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False, index=True)
    payment_id = db.Column(db.Integer, db.ForeignKey('payments.id'), nullable=False, index=True)
    paymob_order_id = db.Column(db.String(50), nullable=False, unique=True, index=True)
    transaction_id = db.Column(db.String(100), nullable=True, unique=True)
    status = db.Column(db.String(50), nullable=False, default='pending')
    amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    processed_at = db.Column(db.DateTime, nullable=True)

    payment = db.relationship('Payment', backref='attempts')

    def __repr__(self):
        return f'<PaymentAttempt {self.id} paymob_order_id={self.paymob_order_id!r} status={self.status!r}>'
