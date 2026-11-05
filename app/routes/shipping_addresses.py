"""Shipping address management routes."""
from typing import Tuple

from flask import Blueprint, current_app, g, request
from marshmallow import ValidationError

from app.middleware.auth import login_required
from app.models.models import Order
from app.schemas.shipping_address_schema import ShippingAddressSchema
from app.services.shipping_service import ShippingService
from app.utils.limiter import limiter
from app.utils.response import api_response

bp = Blueprint('shipping_addresses', __name__)
shipping_address_schema = ShippingAddressSchema()


@bp.route('', methods=['GET'])
@login_required
@limiter.limit('30 per minute')
def list_shipping_addresses() -> Tuple[dict, int]:
    """List shipping addresses for the current user."""
    addresses = ShippingService.list_addresses(g.current_user.id)
    return api_response(True, [shipping_address_schema.dump(address) for address in addresses])


@bp.route('', methods=['POST'])
@login_required
@limiter.limit('20 per minute')
def create_shipping_address() -> Tuple[dict, int]:
    """Create a shipping address for the current user."""
    json_data = request.get_json() or {}
    try:
        data = shipping_address_schema.load(json_data)
    except ValidationError as exc:
        return api_response(False, {}, exc.messages, 400)

    try:
        address = ShippingService.create_address(g.current_user.id, data)
    except Exception as exc:
        current_app.logger.error(f'Error creating shipping address: {exc}')
        return api_response(False, {}, 'An error occurred while saving the address.', 500)

    return api_response(True, shipping_address_schema.dump(address), status_code=201)


@bp.route('/<int:address_id>', methods=['PUT'])
@login_required
@limiter.limit('20 per minute')
def update_shipping_address(address_id: int) -> Tuple[dict, int]:
    """Update a shipping address owned by the current user."""
    address = ShippingService.get_address(address_id, g.current_user.id)
    if not address:
        return api_response(False, {}, 'Shipping address not found', 404)

    json_data = request.get_json() or {}
    try:
        data = shipping_address_schema.load(json_data, partial=True)
    except ValidationError as exc:
        return api_response(False, {}, exc.messages, 400)

    try:
        address = ShippingService.update_address(address, data)
    except Exception as exc:
        current_app.logger.error(f'Error updating shipping address {address_id}: {exc}')
        return api_response(False, {}, 'An error occurred while saving the address.', 500)

    return api_response(True, shipping_address_schema.dump(address))


@bp.route('/<int:address_id>', methods=['DELETE'])
@login_required
@limiter.limit('20 per minute')
def delete_shipping_address(address_id: int) -> Tuple[dict, int]:
    """Delete a shipping address owned by the current user."""
    address = ShippingService.get_address(address_id, g.current_user.id)
    if not address:
        return api_response(False, {}, 'Shipping address not found', 404)

    # An address that an order was shipped to must be kept (orders.address_id
    # is NOT NULL) - say so clearly instead of failing with a database error.
    if Order.query.filter_by(address_id=address.id).first():
        return api_response(
            False, {},
            'This address is used by an existing order and cannot be deleted. You can edit it instead.',
            409,
        )

    try:
        ShippingService.delete_address(address)
    except Exception as exc:
        current_app.logger.error(f'Error deleting shipping address {address_id}: {exc}')
        return api_response(False, {}, 'An error occurred while deleting the address.', 500)

    return api_response(True, {}, 'Shipping address deleted')
