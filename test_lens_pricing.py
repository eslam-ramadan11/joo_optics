"""Tests for app.services.lens_pricing - the tier calculation and price
lookup logic that drives the lens calculator (see checkout.js/index.html).

This module has no database or Flask app dependency, so these tests import
it directly rather than going through the Flask test client - matching how
the module itself is written (pure functions over prescription numbers).

These boundary values come directly from the original pricing spec and were
manually re-verified against the live module during a full production audit
(see PRODUCTION_CHECKLIST.md) before being locked in here as regression tests.
"""
from app.services import lens_pricing


# ---------------------------------------------------------------------
# Tier boundaries - SPH axis
# ---------------------------------------------------------------------

def test_tier_boundaries_sph():
    cases = [
        (0, 1), (3.75, 1),      # tier 1: 0 to 3.75 inclusive
        (3.76, 2), (4, 2), (7.75, 2),  # tier 2: 3.76 to 7.75 inclusive
        (7.76, 3), (8, 3), (11.75, 3),  # tier 3: 7.76 to 11.75 inclusive
        (11.76, None), (12, None), (12.25, None),  # out of range
    ]
    for value, expected_tier in cases:
        got = lens_pricing.calculate_tier(value, 0, value, 0)
        assert got == expected_tier, f'SPH={value} expected tier {expected_tier}, got {got}'


def test_tier_boundaries_negative_sph_same_as_positive():
    """Sign is ignored - only magnitude determines the tier."""
    for value in [3.75, 3.76, 8, 11.75, 11.76]:
        pos = lens_pricing.calculate_tier(value, 0, value, 0)
        neg = lens_pricing.calculate_tier(-value, 0, -value, 0)
        assert pos == neg, f'SPH={value} vs {-value}: tier differs ({pos} vs {neg})'


def test_tier_between_boundaries():
    assert lens_pricing.calculate_tier(1.5, 0, 1.5, 0) == 1
    assert lens_pricing.calculate_tier(5.9, 0, 5.9, 0) == 2
    assert lens_pricing.calculate_tier(10.1, 0, 10.1, 0) == 3


# ---------------------------------------------------------------------
# Tier boundaries - CYL axis (different thresholds than SPH)
# ---------------------------------------------------------------------

def test_tier_boundaries_cyl():
    cases = [
        (0, 1), (1.75, 1),
        (1.76, 2), (2, 2), (3.75, 2),
        (3.76, 3), (4, 3), (5.75, 3),
        (5.76, None), (6, None),
    ]
    for value, expected_tier in cases:
        got = lens_pricing.calculate_tier(0, value, 0, value)
        assert got == expected_tier, f'CYL={value} expected tier {expected_tier}, got {got}'


# ---------------------------------------------------------------------
# R/L asymmetry - whichever eye/axis is worse determines the tier
# ---------------------------------------------------------------------

def test_bigger_eye_wins_right():
    # Right eye is in tier-3 range, left eye is tier-1 - overall must be 3.
    assert lens_pricing.calculate_tier(sph_r=9, cyl_r=1, sph_l=1, cyl_l=1) == 3


def test_bigger_eye_wins_left():
    assert lens_pricing.calculate_tier(sph_r=1, cyl_r=1, sph_l=9, cyl_l=1) == 3


def test_cyl_can_drive_tier_higher_than_sph():
    # SPH alone would be tier 1, but CYL=5 pushes it to tier 3.
    assert lens_pricing.calculate_tier(sph_r=1, cyl_r=5, sph_l=1, cyl_l=1) == 3


def test_any_single_out_of_range_value_makes_whole_prescription_unpriceable():
    # One eye within range, the other beyond 11.75/5.75 - overall is None,
    # not just "downgraded" to the in-range eye's tier.
    assert lens_pricing.calculate_tier(sph_r=1, cyl_r=1, sph_l=15, cyl_l=1) is None


# ---------------------------------------------------------------------
# Basic lens catalog prices - every basic type x 3 tiers, from the owner's spec
# ---------------------------------------------------------------------

EXPECTED_BASIC_PRICES = {
    'standard': {1: 300, 2: 350, 3: 450},
    'pg': {1: 350, 2: 400, 3: 500},
    'blue-cut': {1: 500, 2: 550, 3: 750},
    'photogray': {1: 500, 2: 550, 3: 750},
    'photobrown': {1: 500, 2: 550, 3: 750},
    'multifocal': {1: 1500, 2: 1700, 3: 1800},
    'night-drive': {1: 750, 2: 1200, 3: None},  # tier 3 is the known open gap
    'anti-break-pg': {1: 650, 2: 850, 3: 1350},
    'photogray-bluecut': {1: 900, 2: 1200, 3: 1850},
    'bluecut-antibreak': {1: 800, 2: 950, 3: 1200},
    'photogray-bluecut-antibreak': {1: 2000, 2: 2400, 3: 2800},
    'photogray-bluecut-night-drive': {1: 1500, 2: 1800, 3: 2200},
}


def test_full_basic_price_table_matches_spec():
    for lens_type, tiers in EXPECTED_BASIC_PRICES.items():
        for tier, expected_price in tiers.items():
            actual = lens_pricing.get_price(lens_type, tier)
            assert actual == expected_price, (
                f'{lens_type} tier {tier}: expected {expected_price}, got {actual}'
            )


def test_night_drive_tier_3_is_the_known_unfilled_gap():
    """Documents the one open item from the audit: this price was never
    supplied, so it must stay None (-> WhatsApp fallback) rather than
    silently defaulting to some guessed number. If this test starts
    failing because the value is no longer None, update
    EXPECTED_BASIC_PRICES above with the real number - don't just delete
    this test."""
    assert lens_pricing.TIER_3_NIGHT_DRIVE_BASE is None
    assert lens_pricing.get_price('night-drive', 3) is None


# ---------------------------------------------------------------------
# Unpriceable combinations always resolve to None -> WhatsApp fallback,
# never to a fabricated number.
# ---------------------------------------------------------------------

def test_out_of_range_tier_returns_no_price_for_any_lens_type():
    assert lens_pricing.get_price('standard', None) is None
    assert lens_pricing.get_price('blue-cut', None) is None


def test_unknown_lens_type_returns_no_price():
    assert lens_pricing.get_price('not-a-real-lens-type', 1) is None


def test_empty_lens_type_returns_no_price():
    assert lens_pricing.get_price('', 1) is None


def test_whatsapp_number_is_defined_once_and_reused():
    """Regression guard for the WhatsApp fallback contact - this is the
    single source of truth referenced everywhere else (routes, frontend
    API responses); it should never need a second hardcoded copy."""
    assert lens_pricing.WHATSAPP_NUMBER == '201287178261'


# ---------------------------------------------------------------------
# Advanced usage-based pricing (computer/sun/night/antibreak combos)
# ---------------------------------------------------------------------

def test_usage_price_parses_single_usage_key():
    # 'computer-economic' -> usages=('computer',), quality='economic' -> 500 at tier 1
    assert lens_pricing.get_price('computer-economic', 1) == 500
    assert lens_pricing.get_price('computer-best', 2) == 1000


def test_usage_price_parses_paired_usage_key_regardless_of_order():
    # 'computer-sun-best' -> usages=('computer','sun'), quality='best' -> 1100 at tier 1
    assert lens_pricing.get_price('computer-sun-best', 1) == 1100
    # Order in the key shouldn't matter - lookup sorts before matching.
    assert lens_pricing.get_price('sun-computer-best', 1) == 1100


def test_usage_price_missing_quality_at_a_tier_returns_none():
    # 'sun' alone, tier 3, only has 'premium' defined - no 'economic'/'best'.
    assert lens_pricing.get_price('sun-economic', 3) is None
    assert lens_pricing.get_price('sun-premium', 3) == 1200


def test_undefined_usage_pair_falls_back_to_none_not_an_error():
    """4 of the 6 possible usage-pair combinations are intentionally
    undefined per spec (sun+night, sun+antibreak, night+antibreak,
    computer+night) - these must resolve to None (-> WhatsApp), never
    raise an exception that would break checkout."""
    assert lens_pricing.get_price('night-antibreak-premium', 2) is None
    assert lens_pricing.get_price('sun-night-best', 1) is None
    assert lens_pricing.get_price('computer-night-economic', 1) is None


# ---------------------------------------------------------------------
# Photogray Blue Cut + anti-break / + Night Drive: price follows the tier
# produced by the real prescription boundaries (SPH OR CYL, stronger eye).
# ---------------------------------------------------------------------

def _price_for_rx(lens_type, sph_r, cyl_r, sph_l, cyl_l):
    tier = lens_pricing.calculate_tier(sph_r, cyl_r, sph_l, cyl_l)
    return lens_pricing.get_price(lens_type, tier)


def test_new_photogray_bluecut_lenses_tier_1_by_sph_or_cyl():
    # SPH 0-3.75 and CYL 0-1.75 -> tier 1
    assert _price_for_rx('photogray-bluecut-antibreak', -3.75, 0, -3.75, 0) == 2000
    assert _price_for_rx('photogray-bluecut-night-drive', 0, -1.75, 0, -1.75) == 1500


def test_new_photogray_bluecut_lenses_tier_2_by_sph_or_cyl():
    # SPH 4-7.75 OR CYL 2-3.75 -> tier 2 (either axis is enough)
    assert _price_for_rx('photogray-bluecut-antibreak', -4, 0, -1, 0) == 2400
    assert _price_for_rx('photogray-bluecut-night-drive', -1, -2, -1, 0) == 1800
    assert _price_for_rx('photogray-bluecut-antibreak', -7.75, -3.75, -7.75, -3.75) == 2400


def test_new_photogray_bluecut_lenses_tier_3_by_sph_or_cyl():
    # SPH 8-11.75 OR CYL 4-5.75 -> tier 3
    assert _price_for_rx('photogray-bluecut-antibreak', -8, 0, 0, 0) == 2800
    assert _price_for_rx('photogray-bluecut-night-drive', 0, -4, 0, 0) == 2200
    assert _price_for_rx('photogray-bluecut-night-drive', -11.75, -5.75, -11.75, -5.75) == 2200


def test_new_photogray_bluecut_lenses_stronger_eye_wins_and_sign_ignored():
    assert _price_for_rx('photogray-bluecut-antibreak', -1, 0, 8.25 - 0.25, 0) == 2800
    assert _price_for_rx('photogray-bluecut-night-drive', 2, 0, -5, 0) == 1800


def test_new_photogray_bluecut_lenses_out_of_range_has_no_price():
    assert _price_for_rx('photogray-bluecut-antibreak', -12, 0, 0, 0) is None
    assert _price_for_rx('photogray-bluecut-night-drive', 0, -6, 0, 0) is None


def test_new_photogray_bluecut_lenses_are_not_mistaken_for_usage_keys():
    # 'photogray-bluecut-night-drive' must resolve as a basic catalog key,
    # never be parsed as an advanced "<usage>-<quality>" key.
    assert 'photogray-bluecut-night-drive' in lens_pricing.LENS_CATALOG
    assert 'photogray-bluecut-antibreak' in lens_pricing.LENS_CATALOG
