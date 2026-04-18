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


def test_lookup_falls_back_to_dealspotr_when_cf_empty(mocker, read_fixture):
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

    assert len(codes) == 1
    assert codes[0].code == "SPOTR15"
    assert session.get.call_count == 2


def test_lookup_falls_back_when_cf_blocked(mocker, read_fixture):
    session = MagicMock()
    blocked_resp = MagicMock()
    blocked_resp.status_code = 403
    blocked_resp.text = "forbidden"
    ds_resp = MagicMock()
    ds_resp.status_code = 200
    ds_resp.text = read_fixture("dealspotr_active.html")
    session.get.side_effect = [blocked_resp, ds_resp]
    mocker.patch("coupon_checker.time.sleep")
    log = MagicMock()

    codes = lookup(
        "store.example.net",
        session=session,
        error_log=log,
        today=FROZEN_TODAY,
    )

    assert len(codes) == 1
    assert codes[0].code == "SPOTR15"
    log.error.assert_called()


def test_lookup_returns_empty_when_both_fail(mocker):
    session = MagicMock()
    blocked = MagicMock()
    blocked.status_code = 403
    blocked.text = ""
    session.get.side_effect = [blocked, blocked]
    mocker.patch("coupon_checker.time.sleep")

    codes = lookup(
        "flaky.example.com",
        session=session,
        error_log=MagicMock(),
        today=FROZEN_TODAY,
    )

    assert codes == []
