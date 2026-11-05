"""Lens pricing catalog and tier calculation.

Single source of truth for lens prices. Both the checkout flow (real
charges) and the lens-calculator UI (price preview) read from this same
module, so the price a customer previews is guaranteed to match what
they're actually charged - no duplicated price table to drift out of sync.

Pricing tiers are based on prescription strength (SPH/CYL), not on which
frame is chosen. Sign doesn't matter (a customer said as much) - only
magnitude does. When left/right eyes differ, the stronger eye sets the
tier (also confirmed by the customer).

NOTE ON GAPS: a few combinations were not given a price by the business
owner (see comments below - most notably "night-drive" has no tier-3 base
price, and several advanced/combo categories only have prices at some
tiers). Rather than invent a number, get_price() returns None for anything
not explicitly priced here, and callers treat that as "not available -
direct the customer to WhatsApp" - the same way an out-of-range
prescription is handled. Fill in TIER_3_NIGHT_DRIVE_BASE (currently None)
once you have the real number.
"""
from typing import Dict, Optional, Tuple

WHATSAPP_NUMBER = '201287178261'  # 01287178261 in international format (Egypt)

# --- Tier boundaries -------------------------------------------------------
# Tiers are 1/2/3. None (via calculate_tier) means "out of range - special
# case, direct to WhatsApp". Boundaries are inclusive; values are compared
# as absolute value (sign doesn't affect pricing).
_SPH_TIER_MAX = {1: 3.75, 2: 7.75, 3: 11.75}  # tier 3 special cutoff is 12
_CYL_TIER_MAX = {1: 1.75, 2: 3.75, 3: 5.75}   # tier 3 special cutoff is 6


def _single_axis_tier(value: float, tier_max: Dict[int, float]) -> Optional[int]:
    value = abs(value or 0)
    for tier in (1, 2, 3):
        if value <= tier_max[tier]:
            return tier
    return None  # out of range


def calculate_tier(sph_r: float, cyl_r: float, sph_l: float, cyl_l: float) -> Optional[int]:
    """Return the pricing tier (1, 2, or 3) for a prescription, or None if
    it's out of range for standard pricing (should be quoted manually).

    Takes the stronger eye and the stronger of SPH/CYL within that -
    whichever pushes the tier highest wins, matching "price is based on
    the bigger eye's numbers" and the tier table's SPH-or-CYL phrasing.
    """
    sph_tier_r = _single_axis_tier(sph_r, _SPH_TIER_MAX)
    sph_tier_l = _single_axis_tier(sph_l, _SPH_TIER_MAX)
    cyl_tier_r = _single_axis_tier(cyl_r, _CYL_TIER_MAX)
    cyl_tier_l = _single_axis_tier(cyl_l, _CYL_TIER_MAX)

    tiers = [sph_tier_r, sph_tier_l, cyl_tier_r, cyl_tier_l]
    if any(t is None for t in tiers):
        return None
    return max(tiers)


# --- Basic lens catalog (12 types) ------------------------------------------
# key -> {label_ar, tiers: {1: price, 2: price, 3: price or None}}
TIER_3_NIGHT_DRIVE_BASE = None  # GAP: not provided - fill in the real price

LENS_CATALOG: Dict[str, dict] = {
    'standard': {'label_ar': 'عدسات أبيض نظر عادية', 'tiers': {1: 300, 2: 350, 3: 450}},
    'pg': {'label_ar': 'PG - حماية 50% من الأشعة الضارة', 'tiers': {1: 350, 2: 400, 3: 500}},
    'blue-cut': {'label_ar': 'Blue Cut - حماية 100% من الأشعة الضارة', 'tiers': {1: 500, 2: 550, 3: 750}},
    'photogray': {'label_ar': 'Photogray - يتغير لونها للأسود في الشمس', 'tiers': {1: 500, 2: 550, 3: 750}},
    'photobrown': {'label_ar': 'Photobrown - يتغير لونها للبني في الشمس', 'tiers': {1: 500, 2: 550, 3: 750}},
    'multifocal': {'label_ar': 'Multifocal - للمشي والقراءة معًا', 'tiers': {1: 1500, 2: 1700, 3: 1800}},
    'night-drive': {'label_ar': 'Night Drive - للرؤية والقيادة الليلية', 'tiers': {1: 750, 2: 1200, 3: TIER_3_NIGHT_DRIVE_BASE}},
    'anti-break-pg': {'label_ar': 'ضد الكسر مع طبقة حماية PG', 'tiers': {1: 650, 2: 850, 3: 1350}},
    'photogray-bluecut': {'label_ar': 'Photogray - Blue Cut', 'tiers': {1: 900, 2: 1200, 3: 1850}},
    'bluecut-antibreak': {'label_ar': 'Blue Cut ضد الكسر', 'tiers': {1: 800, 2: 950, 3: 1200}},
    # Added later at the owner's request. Same tier boundaries as every other
    # lens (SPH 0-3.75 or CYL 0-1.75 = tier 1; SPH 4-7.75 or CYL 2-3.75 =
    # tier 2; SPH 8-11.75 or CYL 4-5.75 = tier 3 - see calculate_tier above).
    'photogray-bluecut-antibreak': {'label_ar': 'Photogray Blue Cut ضد الكسر', 'tiers': {1: 2000, 2: 2400, 3: 2800}},
    'photogray-bluecut-night-drive': {'label_ar': 'Photogray Blue Cut Night Drive', 'tiers': {1: 1500, 2: 1800, 3: 2200}},
}

# --- Usage-based ("help me choose") recommendations -------------------------
# Keyed by a sorted tuple of 1-2 usage codes. Each maps to a recommended
# lens family with up to 3 quality levels (economic/best/premium) per tier -
# fewer than 3 at a given tier means that quality isn't offered there (per
# the business owner - not all combos scale down to an economic option at
# high prescriptions), not a missing number.
USAGE_LABELS = {
    'computer': 'للكمبيوتر والشاشات',
    'sun': 'للشمس والخروج',
    'night': 'للقيادة الليلية',
    'antibreak': 'ضد الكسر',
}

QUALITY_LABELS = {
    'economic': 'اقتصادية 💪',
    'best': 'الأفضل ✨',
    'premium': 'Premium 👑',
}

USAGE_RECOMMENDATIONS: Dict[Tuple[str, ...], dict] = {
    ('computer',): {
        'label_ar': 'Blue Cut',
        'tiers': {
            1: {'economic': 500, 'best': 950, 'premium': 1200},
            2: {'economic': 550, 'best': 1000, 'premium': 1350},
            3: {'economic': 700, 'best': 1050, 'premium': 1450},
        },
    },
    ('sun',): {
        'label_ar': 'Photogray',
        'tiers': {
            1: {'economic': 500, 'best': 800, 'premium': 1800},
            2: {'economic': 750, 'best': 1200, 'premium': 2200},
            3: {'premium': 1200},  # only one price given at this tier
        },
    },
    ('night',): {
        'label_ar': 'Night Drive',
        'tiers': {
            1: {'economic': 750, 'best': 1400, 'premium': 1800},
            2: {'best': 1200, 'premium': 2000},  # no economic at this tier
            3: {'best': 1250, 'premium': 2050},  # no economic at this tier
        },
    },
    ('antibreak',): {
        'label_ar': 'ضد الكسر',
        'tiers': {
            1: {'economic': 550, 'best': 800, 'premium': 1900},
            2: {'economic': 800, 'best': 950, 'premium': 1300},
            3: {'premium': 1400},  # only one price given at this tier
        },
    },
    ('computer', 'sun'): {
        'label_ar': 'Photogray - Blue Cut',
        'tiers': {
            1: {'economic': 900, 'best': 1100, 'premium': 2000},
            2: {'economic': 1200, 'best': 2300, 'premium': 2600},
            3: {'premium': 1850},  # only one price given at this tier
        },
    },
    ('antibreak', 'computer'): {
        'label_ar': 'Blue Cut ضد الكسر',
        'tiers': {
            1: {'economic': 800, 'best': 1250, 'premium': 2700},
            2: {'economic': 950, 'premium': 1150},  # no "best" at this tier
            3: {'premium': 1200},  # only one price given at this tier
        },
    },
    # Any other pair (sun+night, sun+antibreak, night+antibreak,
    # computer+night) was not given a product/price by the business owner -
    # intentionally absent, so lookups fall through to "contact us".
}


def get_basic_price(lens_type: str, tier: int) -> Optional[float]:
    """Price for one of the basic lens types at a given tier, or None if
    unavailable (unknown type, or a gap like night-drive tier 3)."""
    entry = LENS_CATALOG.get(lens_type)
    if not entry:
        return None
    return entry['tiers'].get(tier)


def get_usage_price(usages: Tuple[str, ...], tier: int, quality: str) -> Optional[float]:
    """Price for a usage-based recommendation (1-2 usages) at a given tier
    and quality level, or None if that combination isn't offered."""
    key = tuple(sorted(usages))
    entry = USAGE_RECOMMENDATIONS.get(key)
    if not entry:
        return None
    return entry['tiers'].get(tier, {}).get(quality)


def get_price(lens_type: str, tier: Optional[int]) -> Optional[float]:
    """Resolve the price for any lens_type string used on an order item.

    lens_type is either a basic catalog key (e.g. 'blue-cut') or an
    advanced usage-based key in the form '<usage1>[-<usage2>]-<quality>'
    (e.g. 'computer-economic', 'computer-sun-best'). Returns None if tier
    is None (out-of-range prescription) or the combination has no defined
    price - both cases mean "can't auto-price this, contact the customer".
    """
    if tier is None or not lens_type:
        return None

    if lens_type in LENS_CATALOG:
        return get_basic_price(lens_type, tier)

    parts = lens_type.split('-')
    if len(parts) >= 2 and parts[-1] in QUALITY_LABELS:
        quality = parts[-1]
        usages = tuple(parts[:-1])
        return get_usage_price(usages, tier, quality)

    return None
