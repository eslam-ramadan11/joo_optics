from marshmallow import Schema, fields, validate, post_load


class OrderItemSchema(Schema):
    """Input schema for a single order line item.

    SECURITY FIX: item_price used to be accepted here as required client
    input, meaning a caller could set any price they wanted. It has been
    removed entirely - OrderService now always looks up the current
    Product.price server-side and ignores anything the client sends for
    pricing.

    prescription_id is optional: a plain pair of frames/sunglasses with no
    prescription lenses doesn't need one. When lens_type IS one of the real
    lens options, OrderService requires a prescription_id to go with it -
    that cross-field rule lives in the service layer, not here, since it
    depends on the lens price table.
    """
    product_id = fields.Int(required=True)
    prescription_id = fields.Int(required=False, allow_none=True)
    lens_type = fields.Str(required=False, allow_none=True)
    quantity = fields.Int(required=True, validate=validate.Range(min=1))


class OrderSchema(Schema):
    id = fields.Int(dump_only=True)
    user_id = fields.Int(dump_only=True)
    address_id = fields.Int(required=True)
    status = fields.Str(dump_only=True)
    total_amount = fields.Float(dump_only=True)
    discount_amount = fields.Float(dump_only=True)
    date_posted = fields.DateTime(dump_only=True)
    items = fields.Nested(OrderItemSchema, many=True, required=True)
    coupon_code = fields.Str(required=False, allow_none=True, load_default=None)

    # Marketing attribution - all optional. Captured client-side (see
    # tracking.js) and passed through as-is; never validated against a
    # fixed list since ad platforms generate arbitrary campaign/content
    # values we don't control.
    utm_source = fields.Str(required=False, allow_none=True, load_default=None, validate=validate.Length(max=255))
    utm_medium = fields.Str(required=False, allow_none=True, load_default=None, validate=validate.Length(max=255))
    utm_campaign = fields.Str(required=False, allow_none=True, load_default=None, validate=validate.Length(max=255))
    utm_content = fields.Str(required=False, allow_none=True, load_default=None, validate=validate.Length(max=255))
    utm_term = fields.Str(required=False, allow_none=True, load_default=None, validate=validate.Length(max=255))
    fbp = fields.Str(required=False, allow_none=True, load_default=None, validate=validate.Length(max=255))
    fbc = fields.Str(required=False, allow_none=True, load_default=None, validate=validate.Length(max=255))
    ga4_client_id = fields.Str(required=False, allow_none=True, load_default=None, validate=validate.Length(max=255))

    @post_load
    def make_dict(self, data, **kwargs):
        return data
