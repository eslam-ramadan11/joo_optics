"""Service layer for shipping address management."""
from typing import Any, Dict, List, Optional

from app.extensions import db
from app.models.models import ShippingAddress

# SECURITY: user_id/id are never writable through this whitelist, so an
# address can't be reassigned to another user's account via mass assignment.
_WRITABLE_FIELDS = {'city', 'full_address', 'phone_number', 'is_default'}


class ShippingService:
    """Handle CRUD operations for shipping addresses."""

    @staticmethod
    def _filtered(data: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in data.items() if k in _WRITABLE_FIELDS}

    @staticmethod
    def list_addresses(user_id: int) -> List[ShippingAddress]:
        """Return all shipping addresses for a user."""
        return (
            ShippingAddress.query.filter_by(user_id=user_id)
            .order_by(ShippingAddress.id.desc())
            .all()
        )

    @staticmethod
    def get_address(address_id: int, user_id: int) -> Optional[ShippingAddress]:
        """Return a user's shipping address by id."""
        return ShippingAddress.query.filter_by(id=address_id, user_id=user_id).first()

    @staticmethod
    def create_address(user_id: int, data: Dict[str, Any]) -> ShippingAddress:
        """Create a new shipping address and optionally set it as default."""
        data = ShippingService._filtered(data)
        if data.get('is_default'):
            ShippingAddress.query.filter_by(user_id=user_id).update({'is_default': False})

        address = ShippingAddress(user_id=user_id, **data)
        db.session.add(address)
        db.session.commit()
        return address

    @staticmethod
    def update_address(address: ShippingAddress, data: Dict[str, Any]) -> ShippingAddress:
        """Update an address and optionally change the default address."""
        data = ShippingService._filtered(data)
        for key, value in data.items():
            setattr(address, key, value)

        if data.get('is_default'):
            ShippingAddress.query.filter_by(user_id=address.user_id).filter(ShippingAddress.id != address.id).update({'is_default': False})

        db.session.add(address)
        db.session.commit()
        return address

    @staticmethod
    def delete_address(address: ShippingAddress) -> None:
        """Delete an address."""
        db.session.delete(address)
        db.session.commit()
