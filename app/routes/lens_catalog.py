"""Lens catalog routes: expose the pricing catalog and resolve price quotes
from prescription numbers, so the frontend never has to duplicate the
pricing table (see app/services/lens_pricing.py for the source of truth).
"""
from itertools import combinations
from typing import Tuple

from flask import Blueprint, request

from app.services import lens_pricing
from app.utils.response import api_response
from app.utils.limiter import limiter

bp = Blueprint('lens_catalog', __name__)

_WHATSAPP_LINK = f'https://wa.me/{lens_pricing.WHATSAPP_NUMBER}'
_ALL_USAGE_COMBOS = [(u,) for u in lens_pricing.USAGE_LABELS] + list(combinations(sorted(lens_pricing.USAGE_LABELS), 2))


@bp.route('', methods=['GET'])
@limiter.limit('60 per minute')
def get_catalog() -> Tuple[dict, int]:
    """Static reference data: labels and lens type keys, no pricing (use
    /quote for actual prices, which depend on the prescription's tier)."""
    return api_response(True, {
        'basic_types': [
            {'lens_type': key, 'label_ar': entry['label_ar']}
            for key, entry in lens_pricing.LENS_CATALOG.items()
        ],
        'usage_labels': lens_pricing.USAGE_LABELS,
        'quality_labels': lens_pricing.QUALITY_LABELS,
        'whatsapp_number': lens_pricing.WHATSAPP_NUMBER,
        'whatsapp_link': _WHATSAPP_LINK,
    })


@bp.route('/quote', methods=['POST'])
@limiter.limit('60 per minute')
def get_quote() -> Tuple[dict, int]:
    """Resolve a full price quote from prescription numbers: the tier, every
    priced basic lens option, and every priced usage-based recommendation.

    Request JSON: sph_r, cyl_r, sph_l, cyl_l (all numbers).
    """
    data = request.get_json() or {}
    try:
        sph_r = float(data.get('sph_r', 0))
        cyl_r = float(data.get('cyl_r', 0))
        sph_l = float(data.get('sph_l', 0))
        cyl_l = float(data.get('cyl_l', 0))
    except (TypeError, ValueError):
        return api_response(False, {}, 'sph_r, cyl_r, sph_l, cyl_l must be numbers', 400)

    tier = lens_pricing.calculate_tier(sph_r, cyl_r, sph_l, cyl_l)

    if tier is None:
        return api_response(True, {
            'tier': None,
            'is_special': True,
            'whatsapp_number': lens_pricing.WHATSAPP_NUMBER,
            'whatsapp_link': _WHATSAPP_LINK,
            'basic_options': [],
            'usage_options': {},
        })

    basic_options = []
    for lens_type, entry in lens_pricing.LENS_CATALOG.items():
        price = lens_pricing.get_basic_price(lens_type, tier)
        if price is not None:
            basic_options.append({'lens_type': lens_type, 'label_ar': entry['label_ar'], 'price': price})

    usage_options = {}
    for combo in _ALL_USAGE_COMBOS:
        entry = lens_pricing.USAGE_RECOMMENDATIONS.get(combo)
        if not entry:
            continue
        qualities = entry['tiers'].get(tier, {})
        if not qualities:
            continue
        usage_options['+'.join(combo)] = {
            'usages': list(combo),
            'label_ar': entry['label_ar'],
            'qualities': [
                {
                    'quality': q,
                    'label_ar': lens_pricing.QUALITY_LABELS[q],
                    'price': price,
                    'lens_type': '-'.join(combo) + f'-{q}',
                }
                for q, price in qualities.items()
            ],
        }

    return api_response(True, {
        'tier': tier,
        'is_special': False,
        'whatsapp_number': lens_pricing.WHATSAPP_NUMBER,
        'whatsapp_link': _WHATSAPP_LINK,
        'basic_options': basic_options,
        'usage_options': usage_options,
    })
