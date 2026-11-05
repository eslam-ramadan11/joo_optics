from marshmallow import Schema, fields, validate, ValidationError, post_load

# Fixed, canonical list of colors an admin can pick from when adding a
# product. Having a closed list (checkboxes in the admin UI) instead of
# free-typed text avoids the class of bug where "Black" vs "black" vs
# "Black " never match a ProductImage's color tag on the product page.
PRODUCT_COLORS = [
    'Black', 'Brown', 'Tortoise', 'Gold', 'Silver', 'Gunmetal',
    'Blue', 'Navy', 'Red', 'Green', 'Gray', 'Clear',
    'Rose Gold', 'Pink', 'Purple', 'White',
]

# Fixed, canonical list of product categories - was previously free text
# (only Length(1,80) validated), with the same list hand-copied into 6
# separate places across admin.html/shop.html and no server-side check
# that a typo in one of them wouldn't silently drift from the others.
# Same fix as PRODUCT_COLORS above: one source of truth, enforced here.
PRODUCT_CATEGORIES = [
    'men sunglasses', 'womens sunglasses',
    'men medical fraims', 'womens medical fraims',
    'kids glasses',
]


def valid_colors(value):
    chosen = [c.strip() for c in (value or '').split(',') if c.strip()]
    if not chosen:
        raise ValidationError('At least one color is required')
    unknown = [c for c in chosen if c not in PRODUCT_COLORS]
    if unknown:
        raise ValidationError(f'Unknown color(s): {", ".join(unknown)}. Must be one of {PRODUCT_COLORS}')


def non_negative(n):
    try:
        if n is None:
            return True
        if float(n) < 0:
            raise ValidationError('Must be non-negative')
    except ValueError:
        raise ValidationError('Invalid number')


class ProductImageSchema(Schema):
    """Read-only representation of a product gallery image - these are
    managed through their own dedicated endpoints, never through the
    product create/update payload."""
    id = fields.Int(dump_only=True)
    color = fields.Str(dump_only=True, allow_none=True)
    image_file = fields.Str(dump_only=True)
    sort_order = fields.Int(dump_only=True)


class ProductSchema(Schema):
    id = fields.Int(dump_only=True)
    name = fields.Str(required=True, validate=validate.Length(min=1, max=150))
    price = fields.Float(required=True, validate=non_negative)
    old_price = fields.Float(allow_none=True, validate=non_negative)
    category = fields.Str(required=True, validate=validate.OneOf(PRODUCT_CATEGORIES))
    image_file = fields.Str(dump_only=True) # Image file is handled by the service
    discount_badge = fields.Str(allow_none=True, validate=validate.Length(max=50))
    colors = fields.Str(required=True, validate=[validate.Length(min=1, max=500), valid_colors])
    stock_quantity = fields.Int(required=True, validate=validate.Range(min=0))
    images = fields.List(fields.Nested(ProductImageSchema), dump_only=True)

    @post_load
    def make_dict(self, data, **kwargs):
        return data
