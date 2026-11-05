"""Server-side conversion tracking: Meta Conversions API (CAPI) and GA4
Measurement Protocol, used specifically for the Purchase event.

Design principles (see also FINAL PAYMENT-READINESS FIXES thread):
- Tracking must NEVER break or delay the actual order/payment flow. Every
  outbound call here is wrapped so a network failure, missing config, or
  bad response is logged and swallowed, never raised to the caller.
- Purchase is reported exactly once per order, server-side, guarded by
  Order.purchase_tracked_at - set atomically (row-locked) the first time
  a payment is confirmed, from whichever of the two paths gets there
  first (see report_purchase_if_new, called from PaymentService).
- All other events (PageView, ViewContent, AddToCart, etc.) are handled
  entirely client-side (see front j/tracking.js) - they carry no
  trust/security requirement, so there's no backend involvement for them.
"""
from datetime import datetime
from typing import Optional

import requests
from flask import current_app

from app.extensions import db
from app.models.models import Order

META_CAPI_URL_TEMPLATE = 'https://graph.facebook.com/v19.0/{pixel_id}/events'
GA4_MP_URL_TEMPLATE = 'https://www.google-analytics.com/mp/collect?measurement_id={measurement_id}&api_secret={api_secret}'
HTTP_TIMEOUT_SECONDS = 5


def _purchase_event_id(order_id: int) -> str:
    """Deterministic event_id shared between the server-side CAPI call and
    the client-side Pixel fire (see tracking.js) - lets Meta deduplicate
    the two into a single conversion if both arrive, without requiring
    any coordination beyond both sides computing the same order-derived id.
    """
    return f'purchase_{order_id}'


def _send_meta_purchase(order: Order) -> None:
    pixel_id = current_app.config.get('META_PIXEL_ID')
    access_token = current_app.config.get('META_ACCESS_TOKEN')
    if not pixel_id or not access_token:
        current_app.logger.info(f'Meta CAPI not configured - skipping Purchase event for order {order.id}')
        return

    user_data = {}
    if order.fbp:
        user_data['fbp'] = order.fbp
    if order.fbc:
        user_data['fbc'] = order.fbc

    payload = {
        'data': [{
            'event_name': 'Purchase',
            'event_time': int(datetime.utcnow().timestamp()),
            'event_id': _purchase_event_id(order.id),
            'action_source': 'website',
            'user_data': user_data,
            'custom_data': {
                'currency': 'EGP',
                'value': float(order.total_amount),
                'order_id': str(order.id),
            },
        }],
    }
    test_event_code = current_app.config.get('META_TEST_EVENT_CODE')
    if test_event_code:
        payload['test_event_code'] = test_event_code

    try:
        response = requests.post(
            META_CAPI_URL_TEMPLATE.format(pixel_id=pixel_id),
            params={'access_token': access_token},
            json=payload,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            current_app.logger.error(
                f'Meta CAPI Purchase event failed for order {order.id}: '
                f'{response.status_code} {response.text[:500]}'
            )
    except Exception as e:
        # Deliberately broad: this must never propagate and disrupt the
        # payment flow that triggered it, regardless of failure mode.
        current_app.logger.error(f'Meta CAPI Purchase event errored for order {order.id}: {e}')


def _send_ga4_purchase(order: Order) -> None:
    measurement_id = current_app.config.get('GA4_MEASUREMENT_ID')
    api_secret = current_app.config.get('GA4_API_SECRET')
    if not measurement_id or not api_secret:
        current_app.logger.info(f'GA4 Measurement Protocol not configured - skipping Purchase event for order {order.id}')
        return

    # GA4 requires SOME client_id. If the browser never supplied one (e.g.
    # ad blocker, GA4 not loaded), fall back to an order-derived id so the
    # event is still recorded - it just won't be linked to the customer's
    # earlier on-site session in GA4's own reporting.
    client_id = order.ga4_client_id or f'order-{order.id}'

    payload = {
        'client_id': client_id,
        'events': [{
            'name': 'purchase',
            'params': {
                'transaction_id': str(order.id),
                'currency': 'EGP',
                'value': float(order.total_amount),
            },
        }],
    }

    try:
        response = requests.post(
            GA4_MP_URL_TEMPLATE.format(measurement_id=measurement_id, api_secret=api_secret),
            json=payload,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            current_app.logger.error(
                f'GA4 Measurement Protocol Purchase event failed for order {order.id}: '
                f'{response.status_code} {response.text[:500]}'
            )
    except Exception as e:
        current_app.logger.error(f'GA4 Measurement Protocol Purchase event errored for order {order.id}: {e}')


def report_purchase_if_new(order_id: int) -> bool:
    """Report the Purchase event server-side (Meta CAPI + GA4 MP), exactly
    once per order, no matter how many times or from which trigger point
    this is called.

    Call this from any code path that has just confirmed a real purchase
    (a completed Paymob payment, a recorded cash-on-delivery payment) -
    it is always safe to call, including redundantly; only the first
    call for a given order actually sends anything.

    Returns True if this call was the one that fired the events (i.e. it
    was genuinely new), False if it was already reported earlier.
    """
    order = Order.query.filter_by(id=order_id).with_for_update().first()
    if not order:
        return False

    if order.purchase_tracked_at is not None:
        return False

    order.purchase_tracked_at = datetime.utcnow()
    db.session.add(order)
    db.session.commit()

    # Fired after the flag is committed, not before: if the outbound call
    # itself fails partway, we still don't want a retry/duplicate webhook
    # to re-attempt and double-report - a single best-effort attempt per
    # order is the deliberate tradeoff (see module docstring).
    _send_meta_purchase(order)
    _send_ga4_purchase(order)

    return True


def mark_client_purchase_notified(order_id: int, user_id: int) -> Optional[dict]:
    """Check (and atomically claim) whether the customer's browser should
    fire its own client-side Purchase event (Pixel + gtag) for this order.

    This is deliberately separate from purchase_tracked_at (the
    server-side CAPI/GA4-MP guard above) - the two are checked by
    different parties at different times, and a page refresh must not
    cause a second client-side fire even though the server-side report
    may have already happened via the webhook, independent of any page
    ever loading.

    Returns None if the order doesn't exist or doesn't belong to this
    user. Otherwise returns a dict with:
        - paid (bool): whether the order has a confirmed payment
        - should_fire (bool): True only the first time this is called for
          a paid order - the frontend should fire its client-side
          Purchase event if and only if this is True.
        - total_amount, event_id: data needed for that client-side fire.
    """
    order = Order.query.filter_by(id=order_id).with_for_update().first()
    if not order or order.user_id != user_id:
        return None

    payment = order.payment
    is_paid = payment is not None and (
        payment.payment_status == 'completed'
        or (payment.payment_method == 'cash' and payment.payment_status == 'pending')
    )

    if not is_paid:
        return {'paid': False, 'should_fire': False, 'total_amount': order.total_amount, 'event_id': None}

    if order.purchase_client_notified_at is not None:
        return {'paid': True, 'should_fire': False, 'total_amount': order.total_amount, 'event_id': None}

    order.purchase_client_notified_at = datetime.utcnow()
    db.session.add(order)
    db.session.commit()

    return {
        'paid': True,
        'should_fire': True,
        'total_amount': order.total_amount,
        'event_id': _purchase_event_id(order.id),
    }
