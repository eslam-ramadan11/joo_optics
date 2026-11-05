"""Product management routes for CRUD operations."""
from typing import Tuple
from flask import Blueprint, request, current_app
from marshmallow import ValidationError

from app.services.product_service import ProductService, ProductHasOrdersError
from app.schemas.product_schema import ProductSchema, PRODUCT_COLORS, PRODUCT_CATEGORIES
from app.utils.response import api_response
from app.utils.limiter import limiter
from app.middleware.auth import admin_required

bp = Blueprint('products', __name__)
product_schema = ProductSchema()
products_schema = ProductSchema(many=True)


@bp.route('/colors', methods=['GET'])
@limiter.limit('100 per minute')
def list_available_colors() -> Tuple[dict, int]:
    """Return the fixed list of colors a product can be tagged with.

    Public (no auth) since the customer-facing product page could use this
    too, e.g. to render a consistent color swatch order. The admin
    create/edit product forms use this to render checkboxes instead of a
    free-text field, so a typo can never create a color that doesn't match
    any uploaded image's color tag.
    """
    return api_response(True, PRODUCT_COLORS)


@bp.route('/categories', methods=['GET'])
@limiter.limit('100 per minute')
def list_available_categories() -> Tuple[dict, int]:
    """Return the fixed list of product categories.

    Public, same reasoning as /colors above - and same fix: this used to
    be hand-copied into 6 separate places across admin.html/shop.html
    with no server-side check that they stayed in sync. Now there's one
    source of truth (PRODUCT_CATEGORIES) that both the schema validates
    against and every form on the frontend renders from.
    """
    return api_response(True, PRODUCT_CATEGORIES)


@bp.route('/best-sellers', methods=['GET'])
@limiter.limit('100 per minute')
def list_best_sellers() -> Tuple[dict, int]:
    """Products ranked by real total quantity sold (see
    ProductService.list_best_sellers) - never a fabricated ranking.
    Public, same as the main product listing.
    """
    limit = request.args.get('limit', 8, type=int)
    limit = max(1, min(limit, 20))
    products = ProductService.list_best_sellers(limit=limit)
    return api_response(True, products_schema.dump(products))


@bp.route('', methods=['GET'])
@limiter.limit('100 per minute')
def list_products() -> Tuple[dict, int]:
    """List all products with filtering, search, sorting, and pagination."""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
    except ValueError:
        return api_response(False, {}, 'page and per_page must be integers', 400)

    if page < 1 or per_page < 1 or per_page > 100:
        return api_response(False, {}, 'page must be >= 1 and per_page between 1 and 100', 400)

    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', 'id').strip()
    sort_dir = request.args.get('sort_dir', 'asc').lower()
    category = request.args.get('category', '').strip()

    if sort_dir not in ['asc', 'desc']:
        return api_response(False, {}, 'sort_dir must be asc or desc', 400)

    items, total = ProductService.list_products(
        page=page,
        per_page=per_page,
        search=search or None,
        sort_by=sort_by,
        sort_dir=sort_dir,
        category=category or None
    )
    return api_response(True, {
        'items': products_schema.dump(items),
        'total': total,
        'page': page,
        'per_page': per_page,
    })


@bp.route('/<int:product_id>', methods=['GET'])
@limiter.limit('100 per minute')
def get_product(product_id: int) -> Tuple[dict, int]:
    """Retrieve a single product by ID."""
    p = ProductService.get_product(product_id)
    if not p:
        return api_response(False, {}, 'Product not found', 404)
    return api_response(True, product_schema.dump(p))


@bp.route('', methods=['POST'])
@admin_required
@limiter.limit('50 per minute')
def create_product() -> Tuple[dict, int]:
    """Create a new product (admin only). Handles multipart/form-data for image uploads."""
    if 'image' not in request.files:
        return api_response(False, {}, 'Product image is required', 400)

    file = request.files['image']

    try:
        data = product_schema.load(request.form.to_dict())
        p = ProductService.create_product_with_image(data, file)
        return api_response(True, product_schema.dump(p), status_code=201)
    except ValidationError as e:
        return api_response(False, {}, e.messages, 400)
    except (ValueError, FileNotFoundError) as e:
        return api_response(False, {}, str(e), 400)
    except Exception as e:
        current_app.logger.error(f"Error creating product: {e}")
        return api_response(False, {}, "An error occurred while creating the product.", 500)


@bp.route('/<int:product_id>', methods=['PUT'])
@admin_required
@limiter.limit('50 per minute')
def update_product(product_id: int) -> Tuple[dict, int]:
    """Update a product (admin only)."""
    p = ProductService.get_product(product_id)
    if not p:
        return api_response(False, {}, 'Product not found', 404)

    json_data = request.get_json() or {}
    try:
        data = product_schema.load(json_data, partial=True)
    except ValidationError as e:
        return api_response(False, {}, e.messages, 400)

    try:
        p = ProductService.update_product(p, data)
        return api_response(True, product_schema.dump(p))
    except Exception as e:
        current_app.logger.error(f"Error updating product {product_id}: {e}")
        return api_response(False, {}, "An error occurred while updating the product.", 500)


@bp.route('/<int:product_id>', methods=['DELETE'])
@admin_required
@limiter.limit('50 per minute')
def delete_product(product_id: int) -> Tuple[dict, int]:
    """Delete a product (admin only)."""
    p = ProductService.get_product(product_id)
    if not p:
        return api_response(False, {}, 'Product not found', 404)

    try:
        ProductService.delete_product(p)
        return api_response(True, {}, 'Product deleted')
    except ProductHasOrdersError:
        # Past orders still point at this product, so deleting it would break
        # order history. Tell the admin what to do instead of a vague 500.
        return api_response(
            False, {},
            'This product is on existing orders and cannot be deleted. '
            'Set its stock quantity to 0 instead so it can no longer be bought.',
            409,
        )
    except Exception as e:
        current_app.logger.error(f"Error deleting product {product_id}: {e}")
        return api_response(False, {}, "An error occurred while deleting the product.", 500)


@bp.route('/<int:product_id>/images', methods=['POST'])
@admin_required
@limiter.limit('30 per minute')
def add_product_image(product_id: int) -> Tuple[dict, int]:
    """Add a gallery image to a product, optionally tagged with a color (admin only)."""
    p = ProductService.get_product(product_id)
    if not p:
        return api_response(False, {}, 'Product not found', 404)

    if 'image' not in request.files:
        return api_response(False, {}, 'image file is required', 400)

    color = request.form.get('color', '').strip() or None

    try:
        image = ProductService.add_product_image(p, request.files['image'], color)
        return api_response(True, {
            'id': image.id,
            'color': image.color,
            'image_file': image.image_file,
            'sort_order': image.sort_order,
        }, status_code=201)
    except ValueError as e:
        return api_response(False, {}, str(e), 400)
    except Exception as e:
        current_app.logger.error(f"Error adding image to product {product_id}: {e}")
        return api_response(False, {}, "An error occurred while uploading the image.", 500)


@bp.route('/<int:product_id>/images/<int:image_id>', methods=['DELETE'])
@admin_required
@limiter.limit('30 per minute')
def delete_product_image(product_id: int, image_id: int) -> Tuple[dict, int]:
    """Remove a gallery image from a product (admin only)."""
    p = ProductService.get_product(product_id)
    if not p:
        return api_response(False, {}, 'Product not found', 404)

    deleted = ProductService.delete_product_image(p, image_id)
    if not deleted:
        return api_response(False, {}, 'Image not found on this product', 404)

    return api_response(True, {}, 'Image deleted')
