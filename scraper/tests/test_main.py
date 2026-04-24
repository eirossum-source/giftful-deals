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
            PriceResult(current_price=149.0, sale_detected=False),  # drop -> deal
            PriceResult(current_price=300.0, sale_detected=False),  # no drop, no sale -> not a deal
            PriceResult(current_price=129.0, sale_detected=True),   # sale -> deal
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

    def check_side_effect(url, session, error_log):
        if "store.example.net" in url:
            raise RuntimeError("simulated failure")
        return PriceResult(current_price=10.0, sale_detected=False)

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
        return_value=PriceResult(current_price=9999.0, sale_detected=False)
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
        now=datetime(2026, 4, 18),
    )

    assert summary["deals"] == 0
    sender.assert_called_once()
    html = (tmp_path / "index.html").read_text()
    assert "No deals this week" in html


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
        "https://shop-a.com/hp": PriceResult(current_price=180.0, sale_detected=False),
        "https://shop-b.com/hp": PriceResult(current_price=160.0, sale_detected=False),
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
        now=datetime(2026, 4, 18),
    )

    checked_urls = [call.args[0] for call in check.call_args_list]
    assert "https://shop-a.com/hp" in checked_urls
    assert "https://shop-b.com/hp" in checked_urls
    assert summary["deals"] == 1


def test_multi_store_deal_has_store_evaluations(tmp_path):
    items = _multi_store_items()
    fetch = MagicMock(return_value=items)
    check = MagicMock(return_value=PriceResult(current_price=150.0, sale_detected=False))
    lookup = MagicMock(return_value=[])
    sender = MagicMock()

    run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
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
        "https://shop-a.com/hp": PriceResult(current_price=180.0, sale_detected=False),
        "https://shop-b.com/hp": PriceResult(current_price=160.0, sale_detected=False),
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
    check = MagicMock(return_value=PriceResult(current_price=80.0, sale_detected=False))
    lookup = MagicMock(return_value=[])
    sender = MagicMock()

    summary = run(
        fetch_items=fetch,
        check_price=check,
        lookup_coupons=lookup,
        send_email=sender,
        output_path=tmp_path / "index.html",
        log_path=tmp_path / "errors.log",
        now=datetime(2026, 4, 18),
    )

    check.assert_called_once()
    assert check.call_args.args[0] == "https://solo.example.com/x"
    assert summary["deals"] == 1


def test_multi_store_partial_error_still_evaluates_others(tmp_path):
    items = _multi_store_items()
    fetch = MagicMock(return_value=items)

    def check_side(url, **kw):
        if "shop-a" in url:
            raise RuntimeError("boom")
        return PriceResult(current_price=160.0, sale_detected=False)

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
        now=datetime(2026, 4, 18),
    )

    assert summary["deals"] == 1
    assert summary["errors"] == 1
