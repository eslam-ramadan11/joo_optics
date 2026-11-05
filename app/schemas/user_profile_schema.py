"""Schema for user profile validation."""
from datetime import date

from marshmallow import Schema, fields, post_load, validate, validates, ValidationError


class UserProfileSchema(Schema):
    """Validate user profile payloads."""

    id = fields.Int(dump_only=True)
    username = fields.Str(validate=validate.Length(min=3, max=80))
    email = fields.Email()
    date_of_birth = fields.Date(allow_none=True)
    is_admin = fields.Bool(dump_only=True)
    created_at = fields.DateTime(dump_only=True)

    @validates('date_of_birth')
    def validate_date_of_birth(self, value, **kwargs):
        if value is None:
            return
        today = date.today()
        if value > today:
            raise ValidationError('date_of_birth cannot be in the future')
        if value.year < today.year - 120:
            raise ValidationError('date_of_birth is not valid')

    @post_load
    def make_dict(self, data, **kwargs):
        return data
