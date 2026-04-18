from unittest.mock import MagicMock

import pytest

from price_checker import (
    PriceResult,
    USER_AGENTS,
    check_price,
    detect_sale,
    extract_price,
)


def test_extracts_jsonld_price(read_fixture):
    html = read_fixture("retailer_jsonld.html")
    assert extract_price(html) == 149.00


def test_extracts_meta_price(read_fixture):
    html = read_fixture("retailer_meta.html")
    assert extract_price(html) == 229.99


def test_extracts_css_class_price(read_fixture):
    html = read_fixture("retailer_cssclass.html")
    assert extract_price(html) == 119.50


def test_extraction_priority_jsonld_wins(read_fixture):
    html = read_fixture("retailer_all_three.html")
    # JSON-LD = 10, meta = 50, css = 99 -> JSON-LD wins
    assert extract_price(html) == 10.00


def test_no_price_returns_none():
    assert extract_price("<html><body>nothing</body></html>") is None


def test_detects_sale_indicators(read_fixture):
    html = read_fixture("retailer_sale.html")
    assert detect_sale(html) is True


def test_no_sale_returns_false(read_fixture):
    html = read_fixture("retailer_no_sale.html")
    assert detect_sale(html) is False


def test_sale_detection_is_case_insensitive():
    assert detect_sale("<html><body><p>LIMITED TIME offer</p></body></html>") is True
    assert detect_sale("<html><body><p>sale</p></body></html>") is True
    assert detect_sale("<html><body><p>50% OFF</p></body></html>") is True


def test_check_price_handles_403(mocker, tmp_path):
    log = mocker.MagicMock()
    response = MagicMock()
    response.status_code = 403
    response.text = "forbidden"
    session = MagicMock()
    session.get.return_value = response
    mocker.patch("price_checker.time.sleep")

    result = check_price(
        "https://blocked.example.com/x", session=session, error_log=log
    )

    assert result.unavailable is True
    assert result.reason == "blocked"
    log.error.assert_called_once()


def test_check_price_returns_price_and_sale_on_success(mocker, read_fixture):
    response = MagicMock()
    response.status_code = 200
    response.text = read_fixture("retailer_sale.html")
    session = MagicMock()
    session.get.return_value = response
    mocker.patch("price_checker.time.sleep")

    result = check_price(
        "https://shop.example.com/x", session=session, error_log=MagicMock()
    )

    assert result.unavailable is False
    assert result.sale_detected is True


def test_check_price_rotates_user_agents_and_sleeps(mocker):
    response = MagicMock()
    response.status_code = 200
    response.text = "<html></html>"
    session = MagicMock()
    session.get.return_value = response
    sleep_spy = mocker.patch("price_checker.time.sleep")
    # Force deterministic UA pick and delay
    mocker.patch("price_checker.random.choice", return_value=USER_AGENTS[2])
    mocker.patch("price_checker.random.uniform", return_value=2.0)

    check_price(
        "https://shop.example.com/x", session=session, error_log=MagicMock()
    )

    call = session.get.call_args
    assert call.kwargs["headers"]["User-Agent"] == USER_AGENTS[2]
    sleep_spy.assert_called_once_with(2.0)


def test_user_agents_list_has_five_entries():
    assert len(USER_AGENTS) == 5
    assert all("Mozilla" in ua for ua in USER_AGENTS)
