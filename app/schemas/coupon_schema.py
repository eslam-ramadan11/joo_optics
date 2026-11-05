"""Schema for admin coupon create/edit payloads."""
from marshmallow import Schema, fields, validate, ValidationError, validates_schema, post_load

from app.services.coupon_service import VALID_APPLY_TO, VALID_DISCOUNT_TYPES


class CouponSchema(Schema):
    id = fields.Int(dump_only=True)
    code = fields.Str(required=True, validate=validate.Length(min=2, max=50))
    discount_type = fields.Str(required=True, validate=validate.OneOf(sorted(VALID_DISCOUNT_TYPES)))
    discount_value = fields.Float(required=True, validate=validate.Range(min=0.01))

    start_date = fields.DateTime(allow_none=True, load_default=None)
    end_date = fields.DateTime(allow_none=True, load_default=None)
    is_active = fields.Bool(load_default=True)

    max_total_uses = fields.Int(allow_none=True, load_default=None, validate=validate.Range(min=1))
    max_uses_per_customer = fields.Int(allow_none=True, load_default=None, validate=validate.Range(min=1))

    apply_to = fields.Str(load_default='all', validate=validate.OneOf(sorted(VALID_APPLY_TO)))
    apply_to_value = fields.Str(allow_none=True, load_default=None, validate=validate.Length(max=500))

    min_order_amount = fields.Float(allow_none=True, load_default=None, validate=validate.Range(min=0))
    max_discount_amount = fields.Float(allow_none=True, load_default=None, validate=validate.Range(min=0))

    created_at = fields.DateTime(dump_only=True)

    @validates_schema
    def validate_business_rules(self, data, **kwargs):
        if data.get('discount_type') == 'percentage' and data.get('discount_value') is not None:
            if data['discount_value'] > 100:
                raise ValidationError('percentage discount_value cannot exceed 100', field_name='discount_value')

        start = data.get('start_date')
        end = data.get('end_date')
        if start and end and start >= end:
            raise ValidationError('end_date must be after start_date', field_name='end_date')

        apply_to = data.get('apply_to')
        if apply_to in ('specific_products', 'category') and not data.get('apply_to_value'):
            raise ValidationError(
                f'apply_to_value is required when apply_to is "{apply_to}"', field_name='apply_to_value'
            )

    @post_load
    def normalize(self, data, **kwargs):
        if 'code' in data:
            data['code'] = data['code'].strip().upper()
        return data
