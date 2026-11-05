from marshmallow import Schema, fields, validate, ValidationError, post_load


def validate_file_field(filename: str):
    if not filename:
        raise ValidationError('file is required')
    return filename


# Generous bounds - wide enough that no genuine prescription would ever be
# rejected, but they block NaN/Infinity/garbage values (which would
# otherwise silently corrupt lens-tier pricing - see lens_pricing.py) and
# obviously-impossible numbers from a malformed or malicious request.
_SPH_RANGE = validate.Range(min=-30, max=30)
_CYL_RANGE = validate.Range(min=-12, max=12)
# Axis is a true constraint, not a judgment call: it's an angle in
# degrees, and 0-180 is the entire range that has any optical meaning.
_AXIS_RANGE = validate.Range(min=0, max=180)


class PrescriptionSchema(Schema):
    id = fields.Int(dump_only=True)
    user_id = fields.Int(dump_only=True)
    image_file = fields.Str(dump_only=True)
    sph_r = fields.Float(required=True, allow_nan=False, validate=_SPH_RANGE)
    cyl_r = fields.Float(required=True, allow_nan=False, validate=_CYL_RANGE)
    axis_r = fields.Int(required=True, validate=_AXIS_RANGE)
    sph_l = fields.Float(required=True, allow_nan=False, validate=_SPH_RANGE)
    cyl_l = fields.Float(required=True, allow_nan=False, validate=_CYL_RANGE)
    axis_l = fields.Int(required=True, validate=_AXIS_RANGE)
    uploaded_at = fields.DateTime(dump_only=True)

    @post_load
    def make_dict(self, data, **kwargs):
        return data
