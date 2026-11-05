"""Paymob payment gateway integration (Accept API).

Flow (see https://docs.paymob.com):
  1. Authenticate with the API key -> short-lived auth token.
  2. Register an order with Paymob -> get Paymob's own order id.
  3. Request a payment key for that order -> get a payment_token.
  4. Send the customer to the hosted iframe with that payment_token.
  5. Paymob calls our webhook (server-to-server, HMAC-signed) when the
     transaction is processed - this is the ONLY source of truth for
     whether a payment succeeded. The browser redirect back to our site
     (the "transaction response callback") is for UX only and must never be
     trusted to mark something as paid, since its query params are visible
     to and could be replayed/edited by the customer.

All requests use a short timeout and raise PaymobError on any failure so
the caller can turn it into a clean 502-style API response instead of a
bare exception.
"""
import hashlib
import hmac
from typing import Any, Dict, Optional

import requests
from flask import current_app


class PaymobError(Exception):
    """Raised when a Paymob API call fails or returns something unexpected."""


# Paymob payment tokens are valid for this many seconds after being
# issued (passed as 'expiration' below). Defined once here and imported
# by payment_service.py, which uses it to decide whether a cached
# iframe_url/token is still usable for a retried/duplicate initiate
# request, rather than hardcoding the same number in two places.
PAYMOB_TOKEN_LIFETIME_SECONDS = 3600


def _config(key: str) -> str:
    value = current_app.config.get(key)
    if not value:
        raise PaymobError(f'{key} is not configured')
    return value


def get_auth_token() -> str:
    """Step 1: exchange the API key for a short-lived auth token."""
    base_url = current_app.config.get('PAYMOB_BASE_URL', 'https://accept.paymob.com')
    try:
        resp = requests.post(
            f'{base_url}/api/auth/tokens',
            json={'api_key': _config('PAYMOB_API_KEY')},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise PaymobError(f'Paymob auth request failed: {e}') from e

    token = resp.json().get('token')
    if not token:
        raise PaymobError('Paymob auth response did not include a token')
    return token


def register_order(auth_token: str, order) -> str:
    """Step 2: register the order with Paymob.

    `order.id` is passed as merchant_order_id so the webhook can be matched
    back to our own Order without any ambiguity.

    Returns Paymob's own order id (a different id from ours) - this MUST be
    stored locally (Payment.paymob_order_id) so the webhook, which reports
    this id, can be matched back to the right local Payment record.
    """
    base_url = current_app.config.get('PAYMOB_BASE_URL', 'https://accept.paymob.com')
    amount_cents = int(round(order.total_amount * 100))

    try:
        resp = requests.post(
            f'{base_url}/api/ecommerce/orders',
            json={
                'auth_token': auth_token,
                'delivery_needed': False,
                'amount_cents': amount_cents,
                'currency': 'EGP',
                'merchant_order_id': str(order.id),
                'items': [],
            },
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise PaymobError(f'Paymob order registration failed: {e}') from e

    paymob_order_id = resp.json().get('id')
    if not paymob_order_id:
        raise PaymobError('Paymob order response did not include an id')
    return str(paymob_order_id)


def get_payment_key(
    auth_token: str,
    paymob_order_id: str,
    amount_cents: int,
    billing_data: Dict[str, str],
) -> str:
    """Step 3: request the payment key used to open the iframe."""
    base_url = current_app.config.get('PAYMOB_BASE_URL', 'https://accept.paymob.com')

    try:
        resp = requests.post(
            f'{base_url}/api/acceptance/payment_keys',
            json={
                'auth_token': auth_token,
                'amount_cents': amount_cents,
                'expiration': PAYMOB_TOKEN_LIFETIME_SECONDS,
                'order_id': paymob_order_id,
                'billing_data': billing_data,
                'currency': 'EGP',
                'integration_id': _config('PAYMOB_INTEGRATION_ID'),
            },
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise PaymobError(f'Paymob payment key request failed: {e}') from e

    payment_token = resp.json().get('token')
    if not payment_token:
        raise PaymobError('Paymob payment key response did not include a token')
    return payment_token


def build_iframe_url(payment_token: str) -> str:
    """Build the hosted iframe URL the customer's browser is sent to."""
    base_url = current_app.config.get('PAYMOB_BASE_URL', 'https://accept.paymob.com')
    iframe_id = _config('PAYMOB_IFRAME_ID')
    return f'{base_url}/api/acceptance/iframes/{iframe_id}?payment_token={payment_token}'


# Exact field order Paymob documents for the transaction-processed webhook's
# HMAC calculation. Order matters - this is NOT alphabetical, it's the
# literal sequence Paymob specifies. Source:
# https://developers.paymob.com/guides/manage-callback/hmac
_HMAC_FIELDS = [
    'amount_cents',
    'created_at',
    'currency',
    'error_occured',
    'has_parent_transaction',
    'id',
    'integration_id',
    'is_3d_secure',
    'is_auth',
    'is_capture',
    'is_refunded',
    'is_standalone_payment',
    'is_voided',
    'order.id',
    'owner',
    'pending',
    'source_data.pan',
    'source_data.sub_type',
    'source_data.type',
    'success',
]


def _get_nested(data: Dict[str, Any], dotted_key: str) -> Any:
    value = data
    for part in dotted_key.split('.'):
        if not isinstance(value, dict) or part not in value:
            return ''
        value = value[part]
    return value


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if value is None:
        return 'None'
    return str(value)


def verify_hmac(transaction_obj: Dict[str, Any], received_hmac: str) -> bool:
    """Verify a Paymob transaction-processed webhook's HMAC signature.

    `transaction_obj` is the `obj` dict from the webhook's JSON body.
    `received_hmac` is the `hmac` query-string parameter Paymob sends
    alongside the POST. Returns True only if the signature is valid -
    callers must reject the webhook entirely (do not update any payment
    state) when this returns False.
    """
    if not received_hmac:
        return False

    secret = current_app.config.get('PAYMOB_HMAC_SECRET')
    if not secret:
        # Fail closed: if we don't have a secret configured, we cannot
        # verify anything, so never trust the webhook.
        current_app.logger.error('PAYMOB_HMAC_SECRET is not configured - rejecting webhook')
        return False

    concatenated = ''.join(_stringify(_get_nested(transaction_obj, key)) for key in _HMAC_FIELDS)
    computed = hmac.new(secret.encode('utf-8'), concatenated.encode('utf-8'), hashlib.sha512).hexdigest()

    return hmac.compare_digest(computed, received_hmac.lower())


def initiate_payment(order, user) -> Dict[str, str]:
    """Run the full initiate flow (steps 1-4) for a given order.

    Returns {'iframe_url': ..., 'paymob_order_id': ...}. Raises PaymobError
    on any failure - the caller is responsible for turning that into a
    clean API error response rather than a 500 with a stack trace.
    """
    auth_token = get_auth_token()
    paymob_order_id = register_order(auth_token, order)

    amount_cents = int(round(order.total_amount * 100))
    # The Order model's relationship is called `shipping_address` (an
    # attribute named plain `address` does not exist); using the wrong name
    # raised AttributeError and made every card payment return a 500 after
    # the Paymob order had already been created.
    shipping = order.shipping_address
    billing_data = {
        'first_name': (user.username or 'Customer')[:40],
        'last_name': 'N/A',
        'email': user.email or 'customer@example.com',
        'phone_number': getattr(shipping, 'phone_number', None) or '+201000000000',
        'city': getattr(shipping, 'city', None) or 'Cairo',
        'country': 'EG',
        'street': getattr(shipping, 'full_address', None) or 'N/A',
        'building': 'N/A',
        'floor': 'N/A',
        'apartment': 'N/A',
        'state': 'N/A',
    }
    payment_token = get_payment_key(auth_token, paymob_order_id, amount_cents, billing_data)

    return {
        'iframe_url': build_iframe_url(payment_token),
        'paymob_order_id': paymob_order_id,
    }
