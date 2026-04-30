from unittest.mock import MagicMock

import pytest

from price_checker import (
    PriceResult,
    USER_AGENTS,
    _to_float,
    check_price,
    extract_price,
)


def test_to_float_handles_thousands_separator():
    # The Movado regression: "$1,095.00" was parsing as 109.0
    # because the regex grabbed first 3 digits after commas were stripped.
    assert _to_float("$1,095.00") == 1095.0
    assert _to_float("$10,000") == 10000.0
    assert _to_float("1,234,567.89") == 1234567.89
    # Sanity: still works without commas
    assert _to_float("$99.99") == 99.99
    assert _to_float("42") == 42.0


def test_extracts_price_with_thousands_separator():
    html = """
    <html><body>
      <div class="price">$1,095.00</div>
    </body></html>
    """
    assert extract_price(html) == 1095.00


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


def test_check_price_playwright_clicks_amazon_continue_shopping(mocker):
    # Amazon soft-block: page lands on title "Amazon.com" with no h1 and
    # body has "Click the button below to continue shopping". Playwright
    # must click the "Continue shopping" anchor and re-await the product.
    response = MagicMock()
    response.status_code = 403
    response.text = "forbidden"
    session = MagicMock()
    session.get.return_value = response
    mocker.patch("price_checker.time.sleep")

    page = MagicMock()
    page.url = "https://www.amazon.com/dp/B0BZWRSRWV"
    page.title.return_value = "Amazon.com"
    # First evaluate call returns the soft-block body; subsequent calls
    # are not asserted on (the function only inspects body once).
    page.evaluate.return_value = (
        "Click the button below to continue shopping. Conditions of Use"
    )

    # Locator chain: page.locator(...).first -> .count() == 1 -> .click()
    link = MagicMock()
    link.count.return_value = 1
    locator = MagicMock()
    locator.first = link
    page.locator.return_value = locator

    page.content.return_value = (
        '<html><body>'
        '<span class="a-price"><span class="a-offscreen">$42.50</span></span>'
        '</body></html>'
    )

    result = check_price(
        "https://www.amazon.com/dp/B0BZWRSRWV",
        session=session,
        error_log=MagicMock(),
        page=page,
    )

    page.locator.assert_called()
    link.click.assert_called_once()
    # The post-click load wait should also be requested
    assert any(
        c.args and c.args[0] == "load"
        for c in page.wait_for_load_state.call_args_list
    )
    assert result.unavailable is False
    assert result.current_price == 42.50


def test_check_price_playwright_skips_click_on_normal_amazon_page(mocker):
    # If the Amazon page isn't the soft block, click-through must NOT fire.
    response = MagicMock()
    response.status_code = 403
    response.text = "forbidden"
    session = MagicMock()
    session.get.return_value = response
    mocker.patch("price_checker.time.sleep")

    page = MagicMock()
    page.url = "https://www.amazon.com/dp/B0BZWRSRWV"
    page.title.return_value = "Ring Battery Doorbell - Amazon.com"
    page.evaluate.return_value = "Buy now and save"

    link = MagicMock()
    link.count.return_value = 1
    locator = MagicMock()
    locator.first = link
    page.locator.return_value = locator

    page.content.return_value = _amazon_html()

    check_price(
        "https://www.amazon.com/dp/B0BZWRSRWV",
        session=session,
        error_log=MagicMock(),
        page=page,
    )

    link.click.assert_not_called()


def test_check_price_playwright_waits_for_full_load(mocker):
    # JS-heavy retailers (Finish Line, SmartBuyGlasses) need a "load" wait
    # so titles/h1 populate before we hand HTML to check_identity. networkidle
    # is best-effort (sites with long-poll connections never fully idle).
    response = MagicMock()
    response.status_code = 403
    response.text = "forbidden"
    session = MagicMock()
    session.get.return_value = response
    mocker.patch("price_checker.time.sleep")

    page = MagicMock()
    page.content.return_value = _amazon_html()

    check_price(
        "https://blocked.example.com/x",
        session=session,
        error_log=MagicMock(),
        page=page,
    )

    assert page.goto.call_args.kwargs.get("wait_until") == "load"
    page.wait_for_load_state.assert_called_once_with("networkidle", timeout=8_000)


def test_check_price_playwright_tolerates_networkidle_timeout(mocker):
    # Some retailers never reach networkidle (analytics long-polls). The
    # fetch must succeed anyway by returning whatever DOM is loaded.
    response = MagicMock()
    response.status_code = 403
    response.text = "forbidden"
    session = MagicMock()
    session.get.return_value = response
    mocker.patch("price_checker.time.sleep")

    page = MagicMock()
    page.wait_for_load_state.side_effect = Exception("timeout 8000ms exceeded")
    page.content.return_value = _amazon_html()

    result = check_price(
        "https://blocked.example.com/x",
        session=session,
        error_log=MagicMock(),
        page=page,
    )

    assert result.unavailable is False
    assert result.current_price == 42.50


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
