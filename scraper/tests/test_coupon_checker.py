from datetime import date
from unittest.mock import MagicMock

import pytest

from coupon_checker import (
    PromoCode,
    extract_onsite_codes,
    lookup,
    parse_couponfollow,
    parse_dealspotr,
    parse_retailmenot,
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


def test_lookup_returns_empty_when_all_sources_empty(mocker, read_fixture):
    session = MagicMock()
    empty = MagicMock()
    empty.status_code = 200
    empty.text = read_fixture("couponfollow_empty.html")
    session.get.side_effect = [empty, empty, empty]
    mocker.patch("coupon_checker.time.sleep")

    codes = lookup(
        "store.example.net",
        session=session,
        error_log=MagicMock(),
        today=FROZEN_TODAY,
    )

    assert codes == []
    assert session.get.call_count == 3


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


# --- description cleanup ----------------------------------------------------


def test_couponfollow_prefers_title_element_over_description():
    """When a card has both a title element and a description, use the title.

    Real CouponFollow cards put the human-friendly headline (e.g. "20% Off
    Sitewide") in a title element and the long fine-print in description.
    """
    html_doc = """
    <html><body><ul class="offers">
      <li class="offer" data-code="ASOS25">
        <h3 class="coupon-title">25% Off Everything</h3>
        <span class="description">
          Promotional period totaling over $200 online or in stores and enter
          the promo code ASOS25 in cart during checkout will receive a discount
        </span>
      </li>
    </ul></body></html>
    """
    codes = parse_couponfollow(html_doc, today=FROZEN_TODAY)
    assert len(codes) == 1
    assert codes[0].description == "25% Off Everything"


def test_couponfollow_truncates_long_description_at_sentence():
    """No title element — use first sentence of description."""
    html_doc = """
    <html><body><ul class="offers">
      <li class="offer" data-code="MOM20">
        <span class="description">
          20% Off Sitewide at Movado. Valid through end of month. Excludes some items.
        </span>
      </li>
    </ul></body></html>
    """
    codes = parse_couponfollow(html_doc, today=FROZEN_TODAY)
    assert len(codes) == 1
    assert codes[0].description == "20% Off Sitewide at Movado"


def test_couponfollow_truncates_long_description_at_word_boundary():
    """No sentence boundary in first 80 chars — word-cap with ellipsis."""
    long_desc = (
        "period totaling over $500 online or in stores and enter the promo code "
        "FREEGIFT in cart during checkout will receive a pair of earrings"
    )
    html_doc = f"""
    <html><body><ul class="offers">
      <li class="offer" data-code="FREEGIFT">
        <span class="description">{long_desc}</span>
      </li>
    </ul></body></html>
    """
    codes = parse_couponfollow(html_doc, today=FROZEN_TODAY)
    assert len(codes) == 1
    desc = codes[0].description
    assert len(desc) <= 81  # 80 + ellipsis
    assert desc.endswith("…")
    # No mid-word cut: must end on whitespace then ellipsis
    assert " " in desc
    assert not desc[-2].isalnum() or desc[-2:].endswith("…")


def test_couponfollow_parses_click_to_reveal_clipboard_attribute():
    """Real CouponFollow cards omit data-code; the code lives in
    data-clipboard-text on a reveal button."""
    html_doc = """
    <html><body><ul class="offers">
      <li class="offer">
        <h3 class="offer-title">35% Off App Orders</h3>
        <button class="reveal" data-clipboard-text="WELCOMEAPP">Get Code</button>
      </li>
      <li class="offer">
        <h3 class="offer-title">Free Shipping</h3>
        <button class="reveal" data-clipboard-text="BJDDM">Get Code</button>
      </li>
    </ul></body></html>
    """
    codes = parse_couponfollow(html_doc, today=FROZEN_TODAY)
    code_set = {c.code for c in codes}
    assert {"WELCOMEAPP", "BJDDM"} <= code_set


def test_couponfollow_parses_inline_json_codes():
    """Some CouponFollow pages ship offers as JSON in a script tag.

    The aggregator wraps the offer list in a JSON blob inside <script>;
    parsing the static DOM alone misses those codes.
    """
    html_doc = """
    <html><body>
      <ul class="offers"></ul>
      <script type="application/json" id="offers-data">
        [{"code":"WELCOME35","title":"35% off your first order"},
         {"code":"BJDDM","title":"20% off select items"}]
      </script>
    </body></html>
    """
    codes = parse_couponfollow(html_doc, today=FROZEN_TODAY)
    code_set = {c.code for c in codes}
    assert {"WELCOME35", "BJDDM"} <= code_set


def test_couponfollow_aria_label_get_code_pattern():
    """Reveal buttons sometimes carry the code in aria-label rather than
    data-clipboard-text — e.g., aria-label="Get Code WELCOME35"."""
    html_doc = """
    <html><body><ul class="offers">
      <li class="offer">
        <h3 class="offer-title">Welcome offer</h3>
        <button class="reveal" aria-label="Get Code WELCOME35">Reveal</button>
      </li>
    </ul></body></html>
    """
    codes = parse_couponfollow(html_doc, today=FROZEN_TODAY)
    assert any(c.code == "WELCOME35" for c in codes)


def test_retailmenot_parser_basic():
    html_doc = """
    <html><body>
      <div class="offer" data-code="RMN15">
        <h3 class="offer-title">15% off select items</h3>
      </div>
      <div class="offer">
        <h3 class="offer-title">Free shipping</h3>
        <button data-clipboard-text="SHIPFREE">Show Code</button>
      </div>
    </body></html>
    """
    codes = parse_retailmenot(html_doc, today=FROZEN_TODAY)
    code_set = {c.code for c in codes}
    assert {"RMN15", "SHIPFREE"} <= code_set


def test_lookup_falls_through_to_retailmenot_when_cf_and_ds_empty(mocker, read_fixture):
    """CouponFollow + DealsPotr both empty → try RetailMeNot."""
    session = MagicMock()
    empty_cf = MagicMock()
    empty_cf.status_code = 200
    empty_cf.text = read_fixture("couponfollow_empty.html")
    empty_ds = MagicMock()
    empty_ds.status_code = 200
    empty_ds.text = "<html><body></body></html>"
    rmn_resp = MagicMock()
    rmn_resp.status_code = 200
    rmn_resp.text = """
    <html><body>
      <div class="offer" data-code="RMNCODE">
        <h3 class="offer-title">25% off</h3>
      </div>
    </body></html>
    """
    session.get.side_effect = [empty_cf, empty_ds, rmn_resp]
    mocker.patch("coupon_checker.time.sleep")

    codes = lookup(
        "asos.com",
        session=session,
        error_log=MagicMock(),
        today=FROZEN_TODAY,
    )

    assert {c.code for c in codes} == {"RMNCODE"}
    assert session.get.call_count == 3
    urls = [c.args[0] for c in session.get.call_args_list]
    assert "couponfollow.com" in urls[0]
    assert "dealspotr.com" in urls[1]
    assert "retailmenot.com" in urls[2]


def test_onsite_snippet_trimmed_to_clean_sentence():
    """Onsite extraction snippets should not cut off mid-word and should
    prefer a sentence boundary if one is nearby."""
    long_text = (
        "Welcome bonus! Sign up today and use code WELCOME35 at checkout. "
        "Some restrictions apply, see site for full terms and conditions."
    )
    html_doc = f"<html><body><p>{long_text}</p></body></html>"
    codes = extract_onsite_codes(html_doc)
    code_by_str = {c.code: c for c in codes}
    assert "WELCOME35" in code_by_str
    desc = code_by_str["WELCOME35"].description
    assert len(desc) <= 121  # snippet window + ellipsis grace
    # Description must not end in a partial word
    assert desc[-1] in (".", "!", "?", "…") or desc[-1].isalnum()
