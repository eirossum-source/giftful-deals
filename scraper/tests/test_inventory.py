import json
from datetime import date

from inventory import (
    is_back_in_stock,
    load_state,
    normalize_url,
    save_state,
    update_item,
)


def test_load_state_returns_empty_when_file_missing(tmp_path):
    state = load_state(tmp_path / "missing.json")
    assert state == {"items": {}}


def test_load_state_returns_empty_on_corrupt_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    state = load_state(p)
    assert state == {"items": {}}


def test_save_then_load_roundtrips(tmp_path):
    p = tmp_path / "state.json"
    state = {
        "items": {
            "https://shop.example.com/x": {
                "name": "Widget",
                "last_seen": "2026-04-26",
                "in_stock": True,
                "current_price": 19.99,
                "listed_price": 29.99,
                "sold_out_since": None,
            }
        }
    }
    save_state(p, state)
    loaded = load_state(p)
    assert loaded == state


def test_save_creates_parent_directories(tmp_path):
    p = tmp_path / "nested" / "dir" / "state.json"
    save_state(p, {"items": {}})
    assert p.exists()


def test_update_item_marks_sold_out_with_today():
    state = {"items": {}}
    update_item(
        state,
        url="https://shop.example.com/x",
        name="Widget",
        in_stock=False,
        current_price=None,
        listed_price=29.99,
        today=date(2026, 4, 26),
    )
    item = state["items"]["https://shop.example.com/x"]
    assert item["in_stock"] is False
    assert item["sold_out_since"] == "2026-04-26"
    assert item["last_seen"] == "2026-04-26"


def test_update_item_clears_sold_out_when_back():
    state = {
        "items": {
            "https://shop.example.com/x": {
                "name": "Widget",
                "last_seen": "2026-04-19",
                "in_stock": False,
                "current_price": None,
                "listed_price": 29.99,
                "sold_out_since": "2026-04-19",
            }
        }
    }
    update_item(
        state,
        url="https://shop.example.com/x",
        name="Widget",
        in_stock=True,
        current_price=24.99,
        listed_price=29.99,
        today=date(2026, 4, 26),
    )
    item = state["items"]["https://shop.example.com/x"]
    assert item["in_stock"] is True
    assert item["sold_out_since"] is None
    assert item["current_price"] == 24.99


def test_update_item_keeps_sold_out_since_unchanged_on_consecutive_runs():
    state = {
        "items": {
            "https://shop.example.com/x": {
                "name": "Widget",
                "last_seen": "2026-04-19",
                "in_stock": False,
                "current_price": None,
                "listed_price": 29.99,
                "sold_out_since": "2026-04-19",
            }
        }
    }
    update_item(
        state,
        url="https://shop.example.com/x",
        name="Widget",
        in_stock=False,
        current_price=None,
        listed_price=29.99,
        today=date(2026, 4, 26),
    )
    item = state["items"]["https://shop.example.com/x"]
    assert item["sold_out_since"] == "2026-04-19"  # preserved
    assert item["last_seen"] == "2026-04-26"


def test_is_back_in_stock_true_when_was_oos_now_in_stock():
    prev = {
        "items": {
            "https://shop.example.com/x": {
                "in_stock": False,
                "sold_out_since": "2026-04-19",
            }
        }
    }
    assert is_back_in_stock(prev, "https://shop.example.com/x", True) is True


def test_is_back_in_stock_false_when_was_in_stock():
    prev = {
        "items": {
            "https://shop.example.com/x": {
                "in_stock": True,
                "sold_out_since": None,
            }
        }
    }
    assert is_back_in_stock(prev, "https://shop.example.com/x", True) is False


def test_is_back_in_stock_false_when_still_oos():
    prev = {
        "items": {
            "https://shop.example.com/x": {
                "in_stock": False,
                "sold_out_since": "2026-04-19",
            }
        }
    }
    assert is_back_in_stock(prev, "https://shop.example.com/x", False) is False


def test_is_back_in_stock_false_when_url_unknown():
    prev = {"items": {}}
    assert is_back_in_stock(prev, "https://shop.example.com/x", True) is False


def test_update_item_records_prev_in_stock_from_existing_entry():
    # Run N-1 saw the item out of stock. Run N stamps in_stock=False and
    # prev_in_stock=True (the value before this run).
    state = {
        "items": {
            "https://shop.example.com/x": {
                "name": "Widget",
                "last_seen": "2026-04-19",
                "in_stock": True,
                "current_price": 24.99,
                "listed_price": 29.99,
                "sold_out_since": None,
            }
        }
    }
    update_item(
        state,
        url="https://shop.example.com/x",
        name="Widget",
        in_stock=False,
        current_price=None,
        listed_price=29.99,
        today=date(2026, 4, 26),
    )
    item = state["items"]["https://shop.example.com/x"]
    assert item["in_stock"] is False
    assert item["prev_in_stock"] is True


def test_update_item_prev_in_stock_none_for_brand_new_url():
    state = {"items": {}}
    update_item(
        state,
        url="https://shop.example.com/new",
        name="New Widget",
        in_stock=True,
        current_price=49.0,
        listed_price=49.0,
        today=date(2026, 4, 26),
    )
    item = state["items"]["https://shop.example.com/new"]
    assert item["prev_in_stock"] is None


def test_back_in_stock_persists_for_two_consecutive_runs():
    # Trace: oos -> in -> in -> in
    # Run 1 (oos):  in_stock=False
    # Run 2 (back): in_stock=True, prev_in_stock=False  -> BACK_IN_STOCK
    # Run 3 (in):   in_stock=True, prev_in_stock=False  -> still BACK_IN_STOCK (2nd run)
    # Run 4 (in):   in_stock=True, prev_in_stock=True   -> NOT back-in-stock anymore
    url = "https://shop.example.com/x"

    # State after Run 2 (back in stock for the first time)
    state_after_run2 = {
        "items": {
            url: {
                "in_stock": True,
                "prev_in_stock": False,  # was oos last run
                "sold_out_since": None,
            }
        }
    }
    # When Run 3 runs and reads state_after_run2 as prev_state:
    assert is_back_in_stock(state_after_run2, url, True) is True

    # State after Run 3 (still in stock, two runs after coming back)
    state_after_run3 = {
        "items": {
            url: {
                "in_stock": True,
                "prev_in_stock": True,  # was in stock last run too
                "sold_out_since": None,
            }
        }
    }
    # When Run 4 runs and reads state_after_run3 as prev_state:
    assert is_back_in_stock(state_after_run3, url, True) is False


def test_is_back_in_stock_handles_legacy_entries_without_prev_in_stock():
    # Existing inventory.json entries don't have prev_in_stock — must not
    # treat the missing field as False (no spurious BACK_IN_STOCK).
    prev = {
        "items": {
            "https://shop.example.com/x": {
                "in_stock": True,
                "sold_out_since": None,
                # no prev_in_stock key
            }
        }
    }
    assert is_back_in_stock(prev, "https://shop.example.com/x", True) is False


def test_normalize_url_strips_tracking_params():
    out = normalize_url(
        "https://shop.example.com/p/widget?utm_source=email&utm_campaign=spring&color=blue"
    )
    # tracking gone, content params preserved
    assert "utm_source" not in out
    assert "utm_campaign" not in out
    assert "color=blue" in out
    assert out.startswith("https://shop.example.com/p/widget")


def test_normalize_url_strips_affiliate_params():
    out = normalize_url(
        "https://shop.example.com/p/widget?awc=123_456&sv1=affiliate&sku=789"
    )
    assert "awc" not in out
    assert "sv1" not in out
    assert "sku=789" in out
