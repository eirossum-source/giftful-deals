import json
from datetime import date

from giftful import Item
from taste import load_taste, merge_claimed, save_taste

TODAY = date(2026, 11, 5)


def _item(name, price=50.0, category="Tops", url="https://giftful.com/wishlists/t"):
    return Item(name=name, listed_price=price, category=category, category_url=url)


def test_load_taste_missing_file_is_empty(tmp_path):
    assert load_taste(tmp_path / "nope.json") == {"items": {}}


def test_load_taste_corrupt_file_is_empty(tmp_path):
    p = tmp_path / "taste.json"
    p.write_text("{oops", encoding="utf-8")
    assert load_taste(p) == {"items": {}}


def test_load_taste_wrong_shape_is_empty(tmp_path):
    p = tmp_path / "taste.json"
    p.write_text(json.dumps(["x"]), encoding="utf-8")
    assert load_taste(p) == {"items": {}}


def test_merge_adds_new_item():
    state = {"items": {}}
    merge_claimed(state, [_item("Nike Tech Fleece Hoodie", 130.0, "Athleisure")], TODAY)

    entry = state["items"]["nike tech fleece hoodie"]
    assert entry["name"] == "Nike Tech Fleece Hoodie"
    assert entry["price"] == 130.0
    assert entry["lists"] == ["Athleisure"]
    assert entry["first_seen"] == "2026-11-05"
    assert entry["last_seen"] == "2026-11-05"


def test_merge_dedupes_same_item_across_lists():
    state = {"items": {}}
    merge_claimed(
        state,
        [_item("Tee  Shirt", 30.0, "Tops"), _item("tee shirt", 30.0, "Gifts")],
        TODAY,
    )

    assert len(state["items"]) == 1
    entry = state["items"]["tee shirt"]
    assert entry["lists"] == ["Tops", "Gifts"]


def test_merge_accumulates_across_runs_and_keeps_first_seen():
    state = {"items": {}}
    merge_claimed(state, [_item("Hat")], date(2026, 11, 1))
    merge_claimed(state, [_item("Shoes", 90.0)], date(2026, 11, 5))

    assert set(state["items"]) == {"hat", "shoes"}
    assert state["items"]["hat"]["first_seen"] == "2026-11-01"
    assert state["items"]["hat"]["last_seen"] == "2026-11-01"


def test_merge_refreshes_last_seen_and_does_not_duplicate_lists():
    state = {"items": {}}
    merge_claimed(state, [_item("Hat", category="Tops")], date(2026, 11, 1))
    merge_claimed(state, [_item("Hat", category="Tops")], date(2026, 11, 5))

    entry = state["items"]["hat"]
    assert entry["first_seen"] == "2026-11-01"
    assert entry["last_seen"] == "2026-11-05"
    assert entry["lists"] == ["Tops"]


def test_merge_skips_blank_names():
    state = {"items": {}}
    merge_claimed(state, [_item("   ")], TODAY)
    assert state["items"] == {}


def test_save_then_load_roundtrips(tmp_path):
    state = {"items": {}}
    merge_claimed(state, [_item("Hat")], TODAY)
    p = tmp_path / "state" / "taste.json"

    save_taste(p, state)

    assert load_taste(p) == state


def test_refresh_taste_saves_fetched_items(tmp_path):
    from taste import refresh_taste

    p = tmp_path / "taste.json"
    count = refresh_taste(lambda: [_item("Hat"), _item("Shoes")], p, TODAY)

    assert count == 2
    assert set(load_taste(p)["items"]) == {"hat", "shoes"}


def test_refresh_taste_swallows_fetch_failure_and_keeps_old_file(tmp_path):
    from taste import refresh_taste

    p = tmp_path / "taste.json"
    state = {"items": {}}
    merge_claimed(state, [_item("Hat")], TODAY)
    save_taste(p, state)

    def boom():
        raise RuntimeError("giftful down")

    assert refresh_taste(boom, p, TODAY) is None
    assert load_taste(p) == state
