from datetime import date
from unittest.mock import MagicMock

import pytest

from coupon_checker import PromoCode, lookup, parse_couponfollow, parse_dealspotr


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
    session = MagicMock()
    cf_resp = MagicMock()
    cf_resp.status_code = 200
    cf_resp.text = read_fixture("couponfollow_active.html")
    ds_resp = MagicMock()
    ds_resp.status_code = 200
    ds_resp.text = read_fixture("dealspotr_active.html")
    session.get.side_effect = [cf_resp, ds_resp]
    mocker.patch("coupon_checker.time.sleep")

    codes = lookup(
        "shop.example.com",
        session=session,
        error_log=MagicMock(),
        today=FROZEN_TODAY,
    )

    assert {c.code for c in codes} == {"SAVE20", "FREESHIP"}
    # Only CouponFollow hit; fallback not used
    assert session.get.call_count == 1


def test_lookup_returns_empty_when_cf_empty_and_does_not_call_dealspotr(
    mocker, read_fixture
):
    session = MagicMock()
    empty_resp = MagicMock()
    empty_resp.status_code = 200
    empty_resp.text = read_fixture("couponfollow_empty.html")
    session.get.side_effect = [empty_resp]
    mocker.patch("coupon_checker.time.sleep")

    codes = lookup(
        "store.example.net",
        session=session,
        error_log=MagicMock(),
        today=FROZEN_TODAY,
    )

    assert codes == []
    # Only CouponFollow should be hit; DealsPotr fallback removed
    assert session.get.call_count == 1
    called_url = session.get.call_args_list[0].args[0]
    assert "couponfollow.com" in called_url


def test_lookup_returns_empty_on_couponfollow_404(mocker):
    session = MagicMock()
    not_found = MagicMock()
    not_found.status_code = 404
    not_found.text = "not found"
    session.get.side_effect = [not_found]
    mocker.patch("coupon_checker.time.sleep")

    codes = lookup(
        "store.example.net",
        session=session,
        error_log=MagicMock(),
        today=FROZEN_TODAY,
    )

    assert codes == []
    assert session.get.call_count == 1


def test_lookup_returns_empty_on_couponfollow_406(mocker):
    session = MagicMock()
    not_acceptable = MagicMock()
    not_acceptable.status_code = 406
    not_acceptable.text = ""
    session.get.side_effect = [not_acceptable]
    mocker.patch("coupon_checker.time.sleep")

    codes = lookup(
        "store.example.net",
        session=session,
        error_log=MagicMock(),
        today=FROZEN_TODAY,
    )

    assert codes == []
    assert session.get.call_count == 1


def test_lookup_returns_empty_when_cf_blocked_no_dealspotr(mocker):
    session = MagicMock()
    blocked = MagicMock()
    blocked.status_code = 403
    blocked.text = "forbidden"
    session.get.side_effect = [blocked]
    mocker.patch("coupon_checker.time.sleep")

    codes = lookup(
        "store.example.net",
        session=session,
        error_log=MagicMock(),
        today=FROZEN_TODAY,
    )

    assert codes == []
    assert session.get.call_count == 1


def test_lookup_never_calls_dealspotr(mocker):
    session = MagicMock()
    ok = MagicMock()
    ok.status_code = 200
    ok.text = "<html></html>"
    session.get.side_effect = [ok]
    mocker.patch("coupon_checker.time.sleep")

    lookup(
        "store.example.net",
        session=session,
        error_log=MagicMock(),
        today=FROZEN_TODAY,
    )
    for call in session.get.call_args_list:
        url = call.args[0]
        assert "dealspotr" not in url
