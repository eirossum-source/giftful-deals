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
