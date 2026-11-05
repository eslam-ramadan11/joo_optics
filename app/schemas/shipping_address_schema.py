"""Schema for shipping address validation."""
from marshmallow import Schema, fields, post_load, validate


class ShippingAddressSchema(Schema):
    """Validate shipping address payloads."""

    id = fields.Int(dump_only=True)
    user_id = fields.Int(dump_only=True)
    city = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    full_address = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    phone_number = fields.Str(required=True, validate=validate.Length(min=4, max=20))
    is_default = fields.Bool(load_default=False)

    @post_load
    def make_dict(self, data, **kwargs):
        return data
