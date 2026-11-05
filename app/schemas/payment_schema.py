"""Payment schemas for request/response validation."""
from marshmallow import Schema, fields, validate, post_load


class PaymentSchema(Schema):
    """Schema for payment creation.

    SECURITY FIX: 'amount' used to be accepted here as required client
    input, meaning a caller could record any payment amount they wanted,
    regardless of what the order actually costs. It has been removed
    entirely - PaymentService now always charges order.total_amount,
    computed server-side when the order was created.
    """

    id = fields.Int(dump_only=True)
    order_id = fields.Int(required=True)
    payment_method = fields.Str(
        required=True,
        validate=validate.OneOf(['cash'])  # card payments go through /payments/paymob/initiate
    )
    amount = fields.Float(dump_only=True)
    payment_status = fields.Str(dump_only=True)
    transaction_id = fields.Str(dump_only=True)
    payment_date = fields.DateTime(dump_only=True)

    @post_load
    def make_dict(self, data, **kwargs):
        return data


class PaymentUpdateSchema(Schema):
    """Schema for updating payment status.

    manual_refund_required is set automatically (see
    PaymentService.process_paymob_webhook) when a success webhook arrives
    for a payment whose order was already cancelled - it's listed here so
    admins can also transition a payment into or out of it explicitly
    (e.g. after actually issuing the refund, moving it to 'cancelled').
    """

    payment_status = fields.Str(
        required=True,
        validate=validate.OneOf(['pending', 'completed', 'failed', 'cancelled', 'manual_refund_required'])
    )
