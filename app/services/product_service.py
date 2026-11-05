"""Product service for handling all product operations."""
import os
import uuid
from typing import Dict, Any, Tuple, Optional, List

from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.models import Product, ProductImage
from app.schemas.product_schema import PRODUCT_COLORS

class ProductHasOrdersError(Exception):
    """Raised when an admin tries to delete a product that is on past orders."""

    def __init__(self, product_id: int):
        super().__init__(f'product {product_id} appears on existing orders')
        self.product_id = product_id


# SECURITY: whitelist of columns that may be written via create/update.
# Prevents mass-assignment onto `id` or any future sensitive column even if
# a caller forgets to route data through ProductSchema first.
_WRITABLE_FIELDS = {
    'name', 'price', 'old_price', 'category', 'discount_badge', 'colors', 'stock_quantity', 'image_file'
}

# SECURITY: whitelist of columns that may be used for sorting. Prevents
# sorting on arbitrary/relationship attributes discovered via getattr.
_SORTABLE_FIELDS = {'id', 'name', 'price', 'category', 'stock_quantity'}

_ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
_MAX_IMAGE_BYTES = 5 * 1024 * 1024

# Magic-byte signatures for the image types we accept, so a renamed
# executable/script can't slip through just because it has a .png extension.
_IMAGE_SIGNATURES = {
    b'\xff\xd8\xff': 'jpg',
    b'\x89PNG\r\n\x1a\n': 'png',
    b'GIF87a': 'gif',
    b'GIF89a': 'gif',
}


def _sniff_image_type(file_storage: FileStorage) -> Optional[str]:
    """Return a detected image type based on magic bytes, or None if it doesn't look like an image."""
    header = file_storage.stream.read(16)
    file_storage.stream.seek(0)
    for signature, kind in _IMAGE_SIGNATURES.items():
        if header.startswith(signature):
            return kind
    return None


def _save_validated_image(image_file: FileStorage) -> str:
    """Validate (extension + magic bytes + size) and save an uploaded image.

    Shared by the main product image and the extra gallery images, so both
    get the exact same security checks.

    Returns the relative path to store in the DB (e.g. 'uploads/products/xyz.png').

    Raises:
        ValueError: on any validation failure.
    """
    if not image_file or image_file.filename == '':
        raise ValueError("Image file is required.")

    filename = secure_filename(image_file.filename)
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if ext not in _ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Invalid image file extension. Allowed: png, jpg, jpeg, gif")

    detected = _sniff_image_type(image_file)
    if detected is None:
        raise ValueError("File content does not match an allowed image type.")

    image_file.stream.seek(0, os.SEEK_END)
    size = image_file.stream.tell()
    image_file.stream.seek(0)
    if size > _MAX_IMAGE_BYTES:
        raise ValueError(f"Image exceeds max size of {_MAX_IMAGE_BYTES} bytes.")

    upload_folder = os.path.join(current_app.static_folder, 'uploads', 'products')
    os.makedirs(upload_folder, exist_ok=True)

    unique_filename = f"{uuid.uuid4().hex}.{ext}"
    image_path = os.path.join(upload_folder, unique_filename)
    image_file.save(image_path)

    return f'uploads/products/{unique_filename}'


class ProductService:
    """Service layer for product management operations."""

    @staticmethod
    def list_products(
        page: int = 1,
        per_page: int = 20,
        search: Optional[str] = None,
        sort_by: str = 'id',
        sort_dir: str = 'asc',
        category: Optional[str] = None
    ) -> Tuple[List[Product], int]:
        """List all products with filtering, searching, and sorting."""
        q = Product.query

        if search:
            term = f"%{search}%"
            q = q.filter(Product.name.ilike(term))

        if category:
            # Accepts one category or a comma-separated group
            # ("men sunglasses,womens sunglasses") so the storefront can
            # offer "All Sunglasses" / "Men's (All)" without new endpoints.
            categories = [c.strip() for c in category.split(',') if c.strip()]
            if len(categories) == 1:
                q = q.filter(Product.category == categories[0])
            elif categories:
                q = q.filter(Product.category.in_(categories))

        # SECURITY: only allow sorting on a fixed whitelist of columns.
        sort_by = sort_by if sort_by in _SORTABLE_FIELDS else 'id'
        col = getattr(Product, sort_by)
        col = col.desc() if sort_dir == 'desc' else col.asc()
        q = q.order_by(col)

        pagination = q.paginate(page=page, per_page=per_page, error_out=False)
        return pagination.items, pagination.total

    @staticmethod
    def get_product(product_id: int) -> Optional[Product]:
        """Retrieve a product by ID."""
        return Product.query.get(product_id)

    @staticmethod
    def _filtered(data: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in data.items() if k in _WRITABLE_FIELDS}

    @staticmethod
    def create_product(data: Dict[str, Any]) -> Product:
        """Create a new product."""
        product = Product(**ProductService._filtered(data))
        db.session.add(product)
        db.session.commit()
        return product

    @staticmethod
    def create_product_with_image(data: Dict[str, Any], image_file: FileStorage) -> Product:
        """Create a new product and handle image upload.

        Raises:
            ValueError: If the file extension/content is not an allowed image type,
                or the file exceeds the max allowed size.
        """
        relative_path = _save_validated_image(image_file)

        data = dict(data)
        data['image_file'] = relative_path

        product = Product(**ProductService._filtered(data))
        db.session.add(product)
        db.session.commit()
        return product

    @staticmethod
    def add_product_image(product: Product, image_file: FileStorage, color: Optional[str] = None) -> ProductImage:
        """Add an extra gallery image to a product, optionally tagged with a color.

        FIX: this used to save the image with a color tag but never touched
        Product.colors. The customer-facing product page only ever renders
        a color swatch button for colors listed in Product.colors, so a
        newly-tagged color had no swatch to trigger it - the photo was
        saved but permanently unreachable, and it looked like "only one
        image ever shows up". Now the color is added to the product's
        color list automatically (case-insensitive dedup) whenever it's new.

        Raises:
            ValueError: on any image validation failure (same rules as the
                main product image - extension, magic bytes, size).
        """
        relative_path = _save_validated_image(image_file)

        if color:
            if color not in PRODUCT_COLORS:
                raise ValueError(f'Unknown color "{color}". Must be one of {PRODUCT_COLORS}')

            existing_colors = [c.strip() for c in (product.colors or '').split(',') if c.strip()]
            if color not in existing_colors:
                existing_colors.append(color)
                product.colors = ','.join(existing_colors)
                db.session.add(product)

        max_order = db.session.query(db.func.max(ProductImage.sort_order)).filter_by(product_id=product.id).scalar()
        next_order = (max_order or 0) + 1

        image = ProductImage(
            product_id=product.id,
            color=(color or None),
            image_file=relative_path,
            sort_order=next_order,
        )
        db.session.add(image)
        db.session.commit()
        return image

    @staticmethod
    def delete_product_image(product: Product, image_id: int) -> bool:
        """Delete one gallery image belonging to a product.

        Returns False if no such image exists on this product (so the route
        can return 404 rather than silently succeeding on a foreign id).
        """
        image = ProductImage.query.filter_by(id=image_id, product_id=product.id).first()
        if not image:
            return False

        try:
            # image_file is stored as 'uploads/products/xyz.png' relative to
            # the static folder - build the real filesystem path from that.
            full_path = os.path.join(current_app.static_folder, *image.image_file.split('/'))
            if os.path.exists(full_path):
                os.remove(full_path)
        except OSError:
            current_app.logger.warning('failed to remove product image file %s', image.image_file)

        db.session.delete(image)
        db.session.commit()
        return True

    @staticmethod
    def update_product(product: Product, data: Dict[str, Any]) -> Product:
        """Update an existing product. Only whitelisted fields are applied."""
        for k, v in ProductService._filtered(data).items():
            setattr(product, k, v)
        db.session.add(product)
        db.session.commit()
        return product

    @staticmethod
    def delete_product(product: Product) -> None:
        """Delete a product.

        A product that already appears on any order can NOT be deleted:
        order history (and the customer's receipt) must keep pointing at the
        real product row. In that case ProductHasOrdersError is raised and the
        route turns it into a clear 409 for the admin instead of a database
        error. If the product is only featured in "Today's Deals", that
        featuring is removed first so the delete doesn't hit a foreign key.
        """
        from app.models.models import DailyDeal, OrderItem  # local import avoids a circular import at module load time

        if db.session.query(OrderItem.id).filter(OrderItem.product_id == product.id).first() is not None:
            raise ProductHasOrdersError(product.id)

        try:
            DailyDeal.query.filter_by(product_id=product.id).delete(synchronize_session=False)
            db.session.delete(product)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    @staticmethod
    def list_best_sellers(limit: int = 8) -> List[Product]:
        """Products ranked by real total quantity sold, from actual order
        history - never a fabricated or guessed ranking.

        Counts every order except cancelled ones: a 'pending' cash-on-
        delivery order still represents genuine purchase intent, so it's
        included the same as 'delivered'. Products with zero sales are
        naturally excluded (there's nothing to rank them by), so this can
        return fewer than `limit` results, or none, for a brand-new store.
        """
        from app.models.models import Order, OrderItem  # local import avoids a circular import at module load time

        rows = (
            db.session.query(Product, db.func.sum(OrderItem.quantity).label('total_sold'))
            .join(OrderItem, OrderItem.product_id == Product.id)
            .join(Order, Order.id == OrderItem.order_id)
            .filter(Order.status != 'cancelled')
            .group_by(Product.id)
            .order_by(db.desc('total_sold'))
            .limit(limit)
            .all()
        )
        return [product for product, _total_sold in rows]
