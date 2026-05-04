from datetime import date
from unittest.mock import MagicMock

import pytest

from coupon_checker import (
    PromoCode,
    extract_onsite_codes,
    lookup,
    parse_couponfollow,
    parse_dealspotr,
)


FROZEN_TODAY = date(2025, 1, 1)


def test_parses_couponfollow_active_codes(read_fixture):
    html = read_fixture("couponfollow_active.html")

    codes = parse_couponfollow(html, today=FROZEN_TODAY)

    assert len(codes) == 2  # expired one filtered out
    codes_by_string = {c.code: c for c in codes}
    assert "SAVE20" in codes_by_string
    assert "FREESHIP" in codes_by_string
    assert "OLD10" not in codes_by_string
    assert codes_by_string["SAVE20"].description == "20% off your order"


def test_couponfollow_empty_returns_empty_list(read_fixture):
    html = read_fixture("couponfollow_empty.html")
    assert parse_couponfollow(html, today=FROZEN_TODAY) == []


def test_dealspotr_parser(read_fixture):
    html = read_fixture("dealspotr_active.html")

    codes = parse_dealspotr(html, today=FROZEN_TODAY)

    assert len(codes) == 1
    assert codes[0].code == "SPOTR15"


def test_lookup_uses_couponfollow_first(mocker, read_fixture):
    """When CouponFollow returns codes, DealsPotr is not called."""
    session = MagicMock()
    cf_resp = MagicMock()
    cf_resp.status_code = 200
    cf_resp.text = read_fixture("couponfollow_active.html")
    session.get.side_effect = [cf_resp]
    mocker.patch("coupon_checker.time.sleep")

    codes = lookup(
        "shop.example.com",
        session=session,
        error_log=MagicMock(),
        today=FROZEN_TODAY,
    )

    assert {c.code for c in codes} == {"SAVE20", "FREESHIP"}
    assert session.get.call_count == 1
    assert "couponfollow.com" in session.get.call_args_list[0].args[0]


def test_lookup_falls_back_to_dealspotr_when_cf_empty(mocker, read_fixture):
    """CouponFollow 200 with no codes -> try DealsPotr."""
    session = MagicMock()
    empty_resp = MagicMock()
    empty_resp.status_code = 200
    empty_resp.text = read_fixture("couponfollow_empty.html")
    ds_resp = MagicMock()
    ds_resp.status_code = 200
    ds_resp.text = read_fixture("dealspotr_active.html")
    session.get.side_effect = [empty_resp, ds_resp]
    mocker.patch("coupon_checker.time.sleep")

    codes = lookup(
        "store.example.net",
        session=session,
        error_log=MagicMock(),
        today=FROZEN_TODAY,
    )

    assert {c.code for c in codes} == {"SPOTR15"}
    assert session.get.call_count == 2
    urls = [c.args[0] for c in session.get.call_args_list]
    assert "couponfollow.com" in urls[0]
    assert "dealspotr.com" in urls[1]


def test_lookup_falls_back_to_dealspotr_on_couponfollow_404(mocker, read_fixture):
    session = MagicMock()
    not_found = MagicMock()
    not_found.status_code = 404
    not_found.text = "not found"
    ds_resp = MagicMock()
    ds_resp.status_code = 200
    ds_resp.text = read_fixture("dealspotr_active.html")
    session.get.side_effect = [not_found, ds_resp]
    mocker.patch("coupon_checker.time.sleep")

    codes = lookup(
        "store.example.net",
        session=session,
        error_log=MagicMock(),
        today=FROZEN_TODAY,
    )

    assert {c.code for c in codes} == {"SPOTR15"}
    assert session.get.call_count == 2


def test_lookup_returns_empty_when_both_sources_empty(mocker, read_fixture):
    session = MagicMock()
    empty = MagicMock()
    empty.status_code = 200
    empty.text = read_fixture("couponfollow_empty.html")
    session.get.side_effect = [empty, empty]
    mocker.patch("coupon_checker.time.sleep")

    codes = lookup(
        "store.example.net",
        session=session,
        error_log=MagicMock(),
        today=FROZEN_TODAY,
    )

    assert codes == []
    assert session.get.call_count == 2


def test_lookup_strips_www_prefix(mocker, read_fixture):
    """www.asos.com must become asos.com in the CouponFollow URL."""
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.text = read_fixture("couponfollow_active.html")
    session.get.side_effect = [resp]
    mocker.patch("coupon_checker.time.sleep")

    lookup(
        "www.asos.com",
        session=session,
        error_log=MagicMock(),
        today=FROZEN_TODAY,
    )

    called_url = session.get.call_args_list[0].args[0]
    assert called_url == "https://couponfollow.com/site/asos.com"


def test_lookup_merges_onsite_codes_with_aggregator(mocker, read_fixture):
    session = MagicMock()
    cf_resp = MagicMock()
    cf_resp.status_code = 200
    cf_resp.text = read_fixture("couponfollow_active.html")
    session.get.side_effect = [cf_resp]
    mocker.patch("coupon_checker.time.sleep")

    onsite_html = (
        '<html><body><div class="banner">'
        "Subscribe and get 35% off — use code: WELCOME35"
        "</div></body></html>"
    )

    codes = lookup(
        "shop.example.com",
        session=session,
        error_log=MagicMock(),
        today=FROZEN_TODAY,
        onsite_html=onsite_html,
    )

    assert {c.code for c in codes} == {"SAVE20", "FREESHIP", "WELCOME35"}


def test_lookup_dedupes_when_onsite_and_aggregator_share_a_code(mocker, read_fixture):
    session = MagicMock()
    cf_resp = MagicMock()
    cf_resp.status_code = 200
    cf_resp.text = read_fixture("couponfollow_active.html")
    session.get.side_effect = [cf_resp]
    mocker.patch("coupon_checker.time.sleep")

    onsite_html = "<html><body>Use code: SAVE20 today only.</body></html>"

    codes = lookup(
        "shop.example.com",
        session=session,
        error_log=MagicMock(),
        today=FROZEN_TODAY,
        onsite_html=onsite_html,
    )

    code_strings = [c.code for c in codes]
    assert code_strings.count("SAVE20") == 1


# --- extract_onsite_codes ----------------------------------------------------


def test_extract_onsite_codes_basic():
    html = (
        '<html><body><div>20% off using essentials. '
        "Use code: BJDDM</div></body></html>"
    )
    codes = extract_onsite_codes(html)
    assert [c.code for c in codes] == ["BJDDM"]


def test_extract_onsite_codes_multiple_in_one_page():
    html = (
        "<html><body>"
        "<p>New here? 35% off when you subscribe. Use code: WELCOME35.</p>"
        "<p>Download the app for 35% off using WELCOMEAPP.</p>"
        "<p>Get 20% off — use code: BJDDM</p>"
        "</body></html>"
    )
    codes = extract_onsite_codes(html)
    found = {c.code for c in codes}
    assert {"WELCOME35", "BJDDM"} <= found


def test_extract_onsite_codes_ignores_script_and_style():
    html = (
        "<html><head>"
        "<script>var msg = 'use code: SECRET99';</script>"
        "<style>.x{content:'use code: STYLECSS'}</style>"
        "</head><body><p>nothing here</p></body></html>"
    )
    codes = extract_onsite_codes(html)
    assert codes == []


def test_extract_onsite_codes_filters_trigger_word_only_matches():
    """Phrases like 'use code:' followed by no real code shouldn't yield CODE/PROMO."""
    html = "<html><body>Enter code at checkout for 10% off.</body></html>"
    codes = extract_onsite_codes(html)
    code_set = {c.code for c in codes}
    assert "CHECKOUT" not in code_set


def test_extract_onsite_codes_dedupes_across_repeats():
    html = (
        "<html><body>"
        "<p>Use code: SAVE20 today.</p>"
        "<p>Don't forget: use code SAVE20</p>"
        "</body></html>"
    )
    codes = extract_onsite_codes(html)
    assert [c.code for c in codes] == ["SAVE20"]


def test_extract_onsite_codes_handles_empty_html():
    assert extract_onsite_codes("") == []
    assert extract_onsite_codes(None) == []
