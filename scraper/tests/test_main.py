from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from coupon_checker import PromoCode
from giftful import Item
from main import run
from price_checker import PriceResult


def _items():
    return [
        Item(
            name="Headphones",
            url="https://shop.example.com/x",
            listed_price=199.0,
            image_url="",
        ),
        Item(
            name="Grinder",
            url="https://store.example.net/y",
            listed_price=249.0,
            image_url="",
        ),
        Item(
            name="Backpack",
            url="https://gear.example.org/z",
            listed_price=129.0,
            image_url="",
        ),
    ]


def test_happy_path_writes_file_and_summary(tmp_path, capsys):
    items = _items()
    fetch = MagicMock(return_value=items)
    check = MagicMock(
        side_effect=[
            PriceResult(current_price=149.0),  # drop -> deal
            PriceResult(current_price=300.0),  # no drop, no sale -> not a deal
            PriceResult(current_price=119.0),   # sale -> deal
        ]
    )
    lookup = MagicMock(return_value=[])
    sender = MagicMock(return_value={"id": "e1"})
    output = tmp_path / "index.html"
    log_path = tmp_path / "errors.log"

    summary = run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=output,
        log_path=log_path,
        state_path=tmp_path / "state.json",
        review_log_path=tmp_path / "review_log.json",
        now=datetime(2026, 4, 18, 7, 0, 0),
    )

    assert summary["checked"] == 3
    assert summary["deals"] == 2  # item 0 (drop) and item 2 (sale)
    assert summary["errors"] == 0
    assert output.exists()
    content = output.read_text()
    assert "Headphones" in content
    assert "Backpack" in content
    assert "Grinder" not in content  # excluded
    sender.assert_called_once()
    captured = capsys.readouterr()
    assert "3 items checked" in captured.out
    assert "2 deals found" in captured.out
    assert "0 errors" in captured.out


def test_item_error_does_not_crash(tmp_path):
    items = _items()
    fetch = MagicMock(return_value=items)

    def check_side_effect(url, session, error_log, page=None):
        if "store.example.net" in url:
            raise RuntimeError("simulated failure")
        return PriceResult(current_price=10.0)

    check = MagicMock(side_effect=check_side_effect)
    lookup = MagicMock(return_value=[])
    sender = MagicMock()

    summary = run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        state_path=tmp_path / "state.json",
        review_log_path=tmp_path / "review_log.json",
        now=datetime(2026, 4, 18),
    )

    assert summary["checked"] == 3
    assert summary["errors"] == 1
    # Two non-failing items had a price drop -> 2 deals
    assert summary["deals"] == 2
    # error appended
    assert "Grinder" in (tmp_path / "errors.log").read_text()


def test_zero_deals_still_sends_email(tmp_path):
    items = _items()
    fetch = MagicMock(return_value=items)
    check = MagicMock(
        return_value=PriceResult(current_price=9999.0)
    )
    lookup = MagicMock(return_value=[])
    sender = MagicMock()

    summary = run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        state_path=tmp_path / "state.json",
        review_log_path=tmp_path / "review_log.json",
        now=datetime(2026, 4, 18),
    )

    assert summary["deals"] == 0
    sender.assert_called_once()
    html = (tmp_path / "index.html").read_text()
    assert "No deals this week" in html


def test_zero_deals_prints_diagnostic_price_samples(tmp_path, capsys):
    items = _items()
    fetch = MagicMock(return_value=items)
    check = MagicMock(
        return_value=PriceResult(current_price=9999.0)
    )
    lookup = MagicMock(return_value=[])
    sender = MagicMock()

    run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        state_path=tmp_path / "state.json",
        review_log_path=tmp_path / "review_log.json",
        now=datetime(2026, 4, 18),
    )

    captured = capsys.readouterr()
    assert "0 deals" in captured.out
    assert "price samples" in captured.out.lower()
    assert "Headphones" in captured.out
    assert "listed $199" in captured.out
    assert "current $9999" in captured.out


def test_nonzero_deals_omits_diagnostic_samples(tmp_path, capsys):
    items = _items()
    fetch = MagicMock(return_value=items)
    check = MagicMock(
        return_value=PriceResult(current_price=10.0)
    )
    lookup = MagicMock(return_value=[])
    sender = MagicMock()

    run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        state_path=tmp_path / "state.json",
        review_log_path=tmp_path / "review_log.json",
        now=datetime(2026, 4, 18),
    )

    captured = capsys.readouterr()
    assert "price samples" not in captured.out.lower()


def test_empty_wishlist_raises_and_does_not_send(tmp_path):
    from giftful import GiftfulEmptyListError

    fetch = MagicMock(side_effect=GiftfulEmptyListError("no items"))
    sender = MagicMock()

    with pytest.raises(GiftfulEmptyListError):
        run(
            fetch_items=fetch,
            check_price=MagicMock(),
            lookup_coupons=MagicMock(),
            send_email=sender,
            output_path=tmp_path / "index.html",
            log_path=tmp_path / "errors.log",
            now=datetime(2026, 4, 18),
        )

    sender.assert_not_called()


# --- Slice C: per-store evaluation in main loop ---

from filter import StoreEvaluation
from giftful import StoreLink


def _multi_store_items():
    return [
        Item(
            name="Headphones",
            listed_price=199.0,
            image_url="",
            store_urls=[
                StoreLink(url="https://shop-a.com/hp", display_name="Shop A", listed_price=199.0),
                StoreLink(url="https://shop-b.com/hp", display_name="Shop B", listed_price=219.0),
            ],
        ),
    ]


def test_multi_store_checks_each_store_url(tmp_path):
    items = _multi_store_items()
    fetch = MagicMock(return_value=items)

    prices = {
        "https://shop-a.com/hp": PriceResult(current_price=180.0),
        "https://shop-b.com/hp": PriceResult(current_price=160.0),
    }
    check = MagicMock(side_effect=lambda url, **kw: prices[url])
    lookup = MagicMock(return_value=[])
    sender = MagicMock()

    summary = run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        state_path=tmp_path / "state.json",
        review_log_path=tmp_path / "review_log.json",
        now=datetime(2026, 4, 18),
    )

    checked_urls = [call.args[0] for call in check.call_args_list]
    assert "https://shop-a.com/hp" in checked_urls
    assert "https://shop-b.com/hp" in checked_urls
    assert summary["deals"] == 1


def test_multi_store_deal_has_store_evaluations(tmp_path):
    items = _multi_store_items()
    fetch = MagicMock(return_value=items)
    check = MagicMock(return_value=PriceResult(current_price=150.0))
    lookup = MagicMock(return_value=[])
    sender = MagicMock()

    run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        state_path=tmp_path / "state.json",
        review_log_path=tmp_path / "review_log.json",
        now=datetime(2026, 4, 18),
    )

    deals = sender.call_args.kwargs["deals"]
    assert len(deals) == 1
    deal = deals[0]
    assert len(deal.store_evaluations) == 2
    assert all(isinstance(ev, StoreEvaluation) for ev in deal.store_evaluations)


def test_multi_store_winner_is_lowest_price(tmp_path):
    items = _multi_store_items()
    fetch = MagicMock(return_value=items)
    prices = {
        "https://shop-a.com/hp": PriceResult(current_price=180.0),
        "https://shop-b.com/hp": PriceResult(current_price=160.0),
    }
    check = MagicMock(side_effect=lambda url, **kw: prices[url])
    lookup = MagicMock(return_value=[])
    sender = MagicMock()

    run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        state_path=tmp_path / "state.json",
        review_log_path=tmp_path / "review_log.json",
        now=datetime(2026, 4, 18),
    )

    deal = sender.call_args.kwargs["deals"][0]
    assert deal.winner.store.url == "https://shop-b.com/hp"
    assert deal.winner.price_result.current_price == 160.0


def test_fallback_single_url_when_no_store_urls(tmp_path):
    items = [
        Item(
            name="Simple",
            url="https://solo.example.com/x",
            listed_price=100.0,
            image_url="",
        ),
    ]
    fetch = MagicMock(return_value=items)
    check = MagicMock(return_value=PriceResult(current_price=80.0))
    lookup = MagicMock(return_value=[])
    sender = MagicMock()

    summary = run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        state_path=tmp_path / "state.json",
        review_log_path=tmp_path / "review_log.json",
        now=datetime(2026, 4, 18),
    )

    check.assert_called_once()
    assert check.call_args.args[0] == "https://solo.example.com/x"
    assert summary["deals"] == 1


def test_run_threads_page_kwarg_to_check_price(tmp_path):
    items = [
        Item(
            name="Solo",
            url="https://solo.example.com/x",
            listed_price=100.0,
            image_url="",
        ),
    ]
    fetch = MagicMock(return_value=items)
    check = MagicMock(return_value=PriceResult(current_price=80.0))
    lookup = MagicMock(return_value=[])
    sender = MagicMock()
    fake_page = MagicMock()

    run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        state_path=tmp_path / "state.json",
        review_log_path=tmp_path / "review_log.json",
        now=datetime(2026, 4, 18),
        page=fake_page,
    )

    check.assert_called_once()
    assert check.call_args.kwargs.get("page") is fake_page


def test_run_threads_page_kwarg_for_multi_store(tmp_path):
    items = _multi_store_items()
    fetch = MagicMock(return_value=items)
    check = MagicMock(return_value=PriceResult(current_price=150.0))
    lookup = MagicMock(return_value=[])
    sender = MagicMock()
    fake_page = MagicMock()

    run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        state_path=tmp_path / "state.json",
        review_log_path=tmp_path / "review_log.json",
        now=datetime(2026, 4, 18),
        page=fake_page,
    )

    for call in check.call_args_list:
        assert call.kwargs.get("page") is fake_page


def test_run_omits_page_kwarg_when_no_page_provided(tmp_path):
    items = [
        Item(
            name="Solo",
            url="https://solo.example.com/x",
            listed_price=100.0,
            image_url="",
        ),
    ]
    fetch = MagicMock(return_value=items)
    check = MagicMock(return_value=PriceResult(current_price=80.0))
    lookup = MagicMock(return_value=[])
    sender = MagicMock()

    run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        state_path=tmp_path / "state.json",
        review_log_path=tmp_path / "review_log.json",
        now=datetime(2026, 4, 18),
    )

    # When page is not supplied, it should still be passed (as None) so
    # check_price can decide whether to fall back. This keeps the contract
    # explicit instead of "sometimes a kwarg, sometimes not".
    assert check.call_args.kwargs.get("page") is None


def test_identity_retry_via_playwright_when_score_zero(tmp_path):
    """When the requests-derived html scores 0.00 on identity check, the
    runner re-fetches via Playwright and re-validates. If the retry html
    matches, the item is processed as ok rather than flagged for review.

    Mirrors the Tommy John soft-block scenario: requests gets a generic
    landing page; Playwright (which executes anti-bot JS) gets the real
    product page.
    """
    import json as _json
    from unittest.mock import patch

    items = [
        Item(
            name="Second Skin Boxer Brief 8 3-Pack",
            url="https://www.tommyjohn.com/products/second-skin-boxer-brief-8-3-pack-31",
            listed_price=68.0,
            image_url="",
        ),
    ]
    fetch = MagicMock(return_value=items)
    bad_html = """
    <html><head><title>Find Your Perfect Underwear</title></head>
    <body><h1>Shop By Category</h1><div>browse our collection</div></body></html>
    """
    good_html = """
    <html><head><title>Second Skin Boxer Brief 8" (3-Pack) | Tommy John</title></head>
    <body><h1>Second Skin Boxer Brief 8 (3-Pack)</h1>
    <div class="price">$54</div><button>Add to Cart</button></body></html>
    """
    check = MagicMock(return_value=PriceResult(current_price=54.0, html=bad_html))
    lookup = MagicMock(return_value=[])
    sender = MagicMock()
    sentinel_page = MagicMock(name="page")

    retry_result = PriceResult(current_price=54.0, html=good_html)
    with patch("main.recheck_via_playwright", return_value=retry_result) as recheck:
        run(
            fetch_items=fetch,
            check_price=check,
            lookup_coupons=lookup,
            send_email=sender,
            output_path=tmp_path / "index.html",
            log_path=tmp_path / "errors.log",
            state_path=tmp_path / "state.json",
            review_log_path=tmp_path / "review_log.json",
            now=datetime(2026, 5, 4),
            page=sentinel_page,
        )

    assert recheck.called, "Playwright retry should fire on score 0.00"
    log = _json.loads((tmp_path / "review_log.json").read_text())
    statuses = {(e["name"], e["status"]) for e in log["items"]}
    assert ("Second Skin Boxer Brief 8 3-Pack", "ok") in statuses


def test_review_log_includes_diagnostic_snippet_on_identity_fail(tmp_path):
    """When identity flags as mismatch, the review_log reason field includes
    `saw: <title-snippet>` so future false positives are debuggable without
    re-fetching the page."""
    import json as _json

    items = [
        Item(
            name="Vintage Brown Loafers",
            url="https://shop.example.com/x",
            listed_price=200.0,
            image_url="",
        ),
    ]
    fetch = MagicMock(return_value=items)
    mismatch_html = """
    <html><head><title>Sneakers Collection — Outlet Page</title></head>
    <body><h1>All Sneakers</h1><button>Add to Cart</button></body></html>
    """
    check = MagicMock(return_value=PriceResult(current_price=180.0, html=mismatch_html))
    lookup = MagicMock(return_value=[])
    sender = MagicMock()

    run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        state_path=tmp_path / "state.json",
        review_log_path=tmp_path / "review_log.json",
        now=datetime(2026, 5, 4),
    )

    log = _json.loads((tmp_path / "review_log.json").read_text())
    entry = next(e for e in log["items"] if e["name"] == "Vintage Brown Loafers")
    assert entry["status"] == "review"
    assert "saw:" in entry["reason"]
    assert "Sneakers" in entry["reason"]


def test_soft_fail_when_prior_run_identified_url(tmp_path):
    """If the current run scores 0.00 but inventory has a prior pass for
    the same URL, treat as ok (likely intermittent bot block) and emit
    diagnostic reason. Item still appears as a deal, not in the review section."""
    import json as _json
    from unittest.mock import patch

    state_path = tmp_path / "state.json"
    state_path.write_text(
        _json.dumps(
            {
                "items": {
                    "https://shop.example.com/x": {
                        "name": "Vintage Brown Loafers",
                        "last_seen": "2026-04-26",
                        "in_stock": True,
                        "current_price": 180.0,
                        "listed_price": 200.0,
                        "sold_out_since": None,
                        "identity_score": 1.0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    items = [
        Item(
            name="Vintage Brown Loafers",
            url="https://shop.example.com/x",
            listed_price=200.0,
            image_url="",
        ),
    ]
    fetch = MagicMock(return_value=items)
    soft_block_html = """
    <html><head><title>Welcome to ShopExample</title></head>
    <body><h1>Browse our store</h1><button>Sign in</button></body></html>
    """
    check = MagicMock(return_value=PriceResult(current_price=170.0, html=soft_block_html))
    lookup = MagicMock(return_value=[])
    sender = MagicMock()

    # No page provided — Playwright retry doesn't fire; pure soft-fail path.
    summary = run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        state_path=state_path,
        review_log_path=tmp_path / "review_log.json",
        now=datetime(2026, 5, 4),
    )

    assert summary["deals"] == 1
    assert summary.get("review", 0) == 0


def test_validator_flags_dead_link_to_review_section(tmp_path):
    items = [
        Item(
            name="Widget",
            url="https://shop.example.com/x",
            listed_price=100.0,
            image_url="",
        ),
    ]
    fetch = MagicMock(return_value=items)
    dead_html = "<html><body><h1>Page Not Found</h1></body></html>"
    check = MagicMock(return_value=PriceResult(current_price=10.0, html=dead_html))
    lookup = MagicMock(return_value=[])
    sender = MagicMock()

    summary = run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        state_path=tmp_path / "state.json",
        review_log_path=tmp_path / "review_log.json",
        now=datetime(2026, 4, 26),
    )

    assert summary["deals"] == 0
    assert summary.get("review", 0) == 1


def test_drops_sold_out_items_from_deals(tmp_path):
    items = [
        Item(
            name="Widget",
            url="https://shop.example.com/x",
            listed_price=100.0,
            image_url="",
        ),
    ]
    fetch = MagicMock(return_value=items)
    sold_out_html = """
    <html><head>
    <script type="application/ld+json">
    {"@type":"Product","name":"Widget","offers":{"availability":"OutOfStock","price":"50"}}
    </script>
    <title>Widget</title></head>
    <body><h1>Widget</h1></body></html>
    """
    check = MagicMock(return_value=PriceResult(current_price=50.0, html=sold_out_html))
    lookup = MagicMock(return_value=[])
    sender = MagicMock()

    summary = run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        state_path=tmp_path / "state.json",
        review_log_path=tmp_path / "review_log.json",
        now=datetime(2026, 4, 26),
    )

    assert summary["deals"] == 0


def test_marks_back_in_stock_when_state_says_was_oos(tmp_path):
    import json as _json

    state_path = tmp_path / "state.json"
    state_path.write_text(
        _json.dumps(
            {
                "items": {
                    "https://shop.example.com/x": {
                        "name": "Widget",
                        "last_seen": "2026-04-19",
                        "in_stock": False,
                        "current_price": None,
                        "listed_price": 100.0,
                        "sold_out_since": "2026-04-19",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    items = [
        Item(
            name="Widget",
            url="https://shop.example.com/x",
            listed_price=100.0,
            image_url="",
        ),
    ]
    fetch = MagicMock(return_value=items)
    in_stock_html = """
    <html><head><title>Widget - Shop</title></head>
    <body><h1>Widget</h1><div class="price">$100</div>
    <button>Add to Cart</button></body></html>
    """
    check = MagicMock(return_value=PriceResult(current_price=100.0, html=in_stock_html))
    lookup = MagicMock(return_value=[])
    sender = MagicMock()

    summary = run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        state_path=state_path,
        review_log_path=tmp_path / "review_log.json",
        now=datetime(2026, 4, 26),
    )

    assert summary["deals"] == 1
    deal = sender.call_args.kwargs["deals"][0]
    from filter import DealType as _DT
    assert _DT.BACK_IN_STOCK in deal.deal_types


def test_writes_review_log_with_per_item_status(tmp_path):
    import json as _json

    items = [
        Item(name="Dead", url="https://shop.example.com/dead", listed_price=100.0, image_url=""),
        Item(name="Live", url="https://shop.example.com/live", listed_price=50.0, image_url=""),
    ]
    fetch = MagicMock(return_value=items)

    dead_html = "<html><body><h1>Page Not Found</h1></body></html>"
    live_html = """
    <html><head><title>Live - Shop</title></head>
    <body><h1>Live</h1><div class="price">$40</div>
    <button>Add to Cart</button></body></html>
    """
    def check_side(url, **kw):
        if "dead" in url:
            return PriceResult(current_price=10.0, html=dead_html)
        return PriceResult(current_price=40.0, html=live_html)

    check = MagicMock(side_effect=check_side)
    lookup = MagicMock(return_value=[])
    sender = MagicMock()
    review_log_path = tmp_path / "review_log.json"

    run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        state_path=tmp_path / "state.json",
        review_log_path=review_log_path,
        now=datetime(2026, 4, 28),
    )

    log = _json.loads(review_log_path.read_text())
    assert "run_at" in log
    assert "items" in log
    statuses = {(e["name"], e["status"]) for e in log["items"]}
    assert ("Dead", "review") in statuses
    # "Live" is OK so it's in the log too with status="ok"
    statuses_dict = {e["name"]: e for e in log["items"]}
    assert statuses_dict["Live"]["status"] == "ok"
    # Review item has its reason populated
    assert "page not found" in statuses_dict["Dead"]["reason"].lower()


def test_writes_inventory_state(tmp_path):
    import json as _json

    items = [
        Item(
            name="Widget",
            url="https://shop.example.com/x",
            listed_price=100.0,
            image_url="",
        ),
    ]
    fetch = MagicMock(return_value=items)
    good_html = """
    <html><head><title>Widget</title></head>
    <body><h1>Widget</h1><div class="price">$80</div>
    <button>Add to Cart</button></body></html>
    """
    check = MagicMock(return_value=PriceResult(current_price=80.0, html=good_html))
    lookup = MagicMock(return_value=[])
    sender = MagicMock()
    state_path = tmp_path / "state.json"

    run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        state_path=state_path,
        review_log_path=tmp_path / "review_log.json",
        now=datetime(2026, 4, 26),
    )

    saved = _json.loads(state_path.read_text())
    assert "https://shop.example.com/x" in saved["items"]
    item = saved["items"]["https://shop.example.com/x"]
    assert item["in_stock"] is True
    assert item["current_price"] == 80.0


def test_multi_store_partial_error_still_evaluates_others(tmp_path):
    items = _multi_store_items()
    fetch = MagicMock(return_value=items)

    def check_side(url, **kw):
        if "shop-a" in url:
            raise RuntimeError("boom")
        return PriceResult(current_price=160.0)

    check = MagicMock(side_effect=check_side)
    lookup = MagicMock(return_value=[])
    sender = MagicMock()

    summary = run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        state_path=tmp_path / "state.json",
        review_log_path=tmp_path / "review_log.json",
        now=datetime(2026, 4, 18),
    )

    assert summary["deals"] == 1
    assert summary["errors"] == 1


def test_coupons_looked_up_once_per_unique_domain(tmp_path):
    """Per-domain cache: many items at the same retailer -> one aggregator call."""
    items = [
        Item(
            name="Item A",
            url="https://www.acme.com/a",
            listed_price=100.0,
            image_url="",
        ),
        Item(
            name="Item B",
            url="https://www.acme.com/b",
            listed_price=120.0,
            image_url="",
        ),
        Item(
            name="Item C",
            url="https://www.other.com/c",
            listed_price=80.0,
            image_url="",
        ),
    ]
    fetch = MagicMock(return_value=items)
    check = MagicMock(return_value=PriceResult(current_price=50.0))
    lookup = MagicMock(return_value=[])
    sender = MagicMock()

    run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        state_path=tmp_path / "state.json",
        review_log_path=tmp_path / "review_log.json",
        now=datetime(2026, 4, 18),
    )

    # 3 items, 2 unique domains -> 2 aggregator calls (not 3).
    assert lookup.call_count == 2
    domains_passed = [call.args[0] for call in lookup.call_args_list]
    # And the slug passed in should be www-stripped.
    assert "acme.com" in domains_passed
    assert "other.com" in domains_passed


def test_onsite_codes_surface_as_promo_deal(tmp_path):
    """A page whose HTML has 'use code: XYZ123' yields a PROMO deal even with no aggregator hits."""
    items = [
        Item(
            name="Shorts",
            url="https://www.asos.com/shorts",
            listed_price=65.0,
            image_url="",
        ),
    ]
    onsite_html = (
        '<html><body><div class="banner">'
        "20% off using essentials. Use code: BJDDM"
        "</div></body></html>"
    )
    fetch = MagicMock(return_value=items)
    check = MagicMock(
        return_value=PriceResult(current_price=65.0, html=onsite_html)
    )
    lookup = MagicMock(return_value=[])  # aggregators find nothing
    sender = MagicMock()

    run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        state_path=tmp_path / "state.json",
        review_log_path=tmp_path / "review_log.json",
        now=datetime(2026, 4, 18),
    )

    deals = sender.call_args.kwargs["deals"]
    assert len(deals) == 1
    promos = deals[0].promos
    assert any(p.code == "BJDDM" for p in promos)


def test_onsite_description_wins_over_aggregator_for_shared_code(tmp_path):
    """When the same code appears onsite and on an aggregator, the onsite
    description must win — aggregator HTML often leaks accessibility-popup
    junk into descriptions, while the retailer's own page shows the real
    offer headline.
    """
    items = [
        Item(
            name="Watch",
            url="https://www.movado.com/watch",
            listed_price=595.0,
            image_url="",
        ),
    ]
    onsite_html = (
        "<html><body><div class='promo'>"
        "20% off at checkout with code MOM20"
        "</div></body></html>"
    )
    fetch = MagicMock(return_value=items)
    check = MagicMock(
        return_value=PriceResult(current_price=476.0, html=onsite_html)
    )
    # Aggregator returns the same code with junk text — must lose to onsite.
    junk = "Popup heading Close Accessibility Press enter for more options"
    lookup = MagicMock(return_value=[PromoCode("MOM20", junk, None)])
    sender = MagicMock()

    run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        state_path=tmp_path / "state.json",
        review_log_path=tmp_path / "review_log.json",
        now=datetime(2026, 4, 18),
    )

    deals = sender.call_args.kwargs["deals"]
    assert len(deals) == 1
    mom20 = next(p for p in deals[0].promos if p.code == "MOM20")
    assert "Popup" not in mom20.description
    assert "Accessibility" not in mom20.description
    assert "20% off" in mom20.description.lower()
