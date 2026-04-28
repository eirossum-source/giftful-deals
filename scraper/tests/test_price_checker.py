from unittest.mock import MagicMock

import pytest

from price_checker import (
    PriceResult,
    USER_AGENTS,
    check_price,
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


def test_extracts_amazon_price(read_fixture):
    html = read_fixture("retailer_amazon.html")
    assert extract_price(html) == 34.99


def test_extraction_priority_amazon_after_meta(read_fixture):
    # meta = 50, amazon .a-offscreen = 22.50, css .price = 99
    # Amazon step runs after meta, so meta wins.
    html = read_fixture("retailer_amazon_priority.html")
    assert extract_price(html) == 50.00


def test_amazon_picks_live_price_not_strikethrough_reference(read_fixture):
    # Page has $49.99 strikethrough "List Price" near the top AND a live
    # $24.99 in #corePrice_feature_div. The Amazon extractor must pick the
    # live price, not the strikethrough reference.
    html = read_fixture("retailer_amazon_with_strikethrough.html")
    assert extract_price(html) == 24.99


def test_extraction_amazon_runs_before_generic_css():
    # No JSON-LD, no meta. Amazon-specific should beat generic CSS.
    html = """
    <html><body>
      <span class="a-price"><span class="a-offscreen">$19.95</span></span>
      <div class="price">$99.00</div>
    </body></html>
    """
    assert extract_price(html) == 19.95


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


def test_check_price_returns_html_on_success(mocker, read_fixture):
    response = MagicMock()
    response.status_code = 200
    response.text = read_fixture("retailer_jsonld.html")
    session = MagicMock()
    session.get.return_value = response
    mocker.patch("price_checker.time.sleep")

    result = check_price(
        "https://shop.example.com/x", session=session, error_log=MagicMock()
    )

    assert result.unavailable is False
    assert result.html is not None
    assert "ld+json" in result.html


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


# ---------- Playwright fallback ----------


def _amazon_html() -> str:
    return (
        '<html><body>'
        '<span class="a-price"><span class="a-offscreen">$42.50</span></span>'
        '</body></html>'
    )


def test_check_price_uses_playwright_when_blocked(mocker):
    response = MagicMock()
    response.status_code = 403
    response.text = "forbidden"
    session = MagicMock()
    session.get.return_value = response
    mocker.patch("price_checker.time.sleep")

    page = MagicMock()
    page.content.return_value = _amazon_html()

    log = MagicMock()
    result = check_price(
        "https://blocked.example.com/x",
        session=session,
        error_log=log,
        page=page,
    )

    page.goto.assert_called_once()
    assert page.goto.call_args.args[0] == "https://blocked.example.com/x"
    assert result.unavailable is False
    assert result.current_price == 42.50


def test_check_price_uses_playwright_when_no_price_extracted(mocker):
    # 200 OK but extract_price returns None (e.g. JS-rendered page).
    response = MagicMock()
    response.status_code = 200
    response.text = "<html><body>nothing here</body></html>"
    session = MagicMock()
    session.get.return_value = response
    mocker.patch("price_checker.time.sleep")

    page = MagicMock()
    page.content.return_value = _amazon_html()

    result = check_price(
        "https://shop.example.com/js-spa",
        session=session,
        error_log=MagicMock(),
        page=page,
    )

    page.goto.assert_called_once()
    assert result.unavailable is False
    assert result.current_price == 42.50


def test_check_price_no_playwright_fallback_when_page_is_none(mocker):
    # Existing back-compat: page omitted, blocked stays blocked.
    response = MagicMock()
    response.status_code = 403
    response.text = "forbidden"
    session = MagicMock()
    session.get.return_value = response
    mocker.patch("price_checker.time.sleep")

    result = check_price(
        "https://blocked.example.com/x",
        session=session,
        error_log=MagicMock(),
    )

    assert result.unavailable is True
    assert result.reason == "blocked"


def test_check_price_skips_playwright_when_requests_succeeded_with_price(
    mocker, read_fixture
):
    response = MagicMock()
    response.status_code = 200
    response.text = read_fixture("retailer_jsonld.html")
    session = MagicMock()
    session.get.return_value = response
    mocker.patch("price_checker.time.sleep")

    page = MagicMock()
    result = check_price(
        "https://shop.example.com/x",
        session=session,
        error_log=MagicMock(),
        page=page,
    )

    page.goto.assert_not_called()
    assert result.current_price == 149.00


def test_check_price_playwright_failure_returns_unavailable(mocker):
    response = MagicMock()
    response.status_code = 403
    response.text = "forbidden"
    session = MagicMock()
    session.get.return_value = response
    mocker.patch("price_checker.time.sleep")

    page = MagicMock()
    page.goto.side_effect = Exception("playwright timeout")

    log = MagicMock()
    result = check_price(
        "https://blocked.example.com/x",
        session=session,
        error_log=log,
        page=page,
    )

    assert result.unavailable is True
    assert result.reason == "playwright_error"
    log.error.assert_called()


def test_check_price_playwright_returns_html_for_validator(mocker):
    response = MagicMock()
    response.status_code = 403
    response.text = ""
    session = MagicMock()
    session.get.return_value = response
    mocker.patch("price_checker.time.sleep")

    page = MagicMock()
    page.content.return_value = (
        '<html><body>'
        '<span class="a-price"><span class="a-offscreen">$42.50</span></span>'
        '</body></html>'
    )

    result = check_price(
        "https://blocked.example.com/x",
        session=session,
        error_log=MagicMock(),
        page=page,
    )

    assert result.current_price == 42.50
    assert result.html is not None
    assert "a-offscreen" in result.html
