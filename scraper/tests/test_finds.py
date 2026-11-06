"""S3b — re-check the finder's finds at the store and track them until off sale."""
import json
from datetime import date

from finds import (
    MAX_MISSES,
    MAX_TRACKED,
    check_finds,
    is_on_sale,
    load_incoming,
    load_ledger,
    owned_keys,
    save_ledger,
    url_key,
)
from giftful import Item, StoreLink
from price_checker import PriceResult

TODAY = date(2026, 11, 9)


def _find(url="https://shop.example.com/products/faith-tee", name="Faith Boxy Tee",
          category="Casual", **extra):
    raw = {
        "url": url,
        "name": name,
        "store": "shop.example.com",
        "category": category,
        "image_url": "https://shop.example.com/cdn/faith-tee.jpg",
        "seen_price": 28.0,
        "seen_list_price": 40.0,
        "similar_to": "\"HOLY VIBES\" TEE (BLACK)",
        "found_at": "2026-11-09",
    }
    raw.update(extra)
    return raw


def _incoming(*finds, generated_at="2026-11-09T03:00:00Z"):
    return {"generated_at": generated_at, "finds": list(finds)}


def _ok(name, url, pr):
    return pr, "ok", None, 0.8


def _checker(results):
    """results: url -> PriceResult (or Exception to raise)."""
    calls = []

    def check(url):
        calls.append(url)
        r = results[url]
        if isinstance(r, Exception):
            raise r
        return r

    check.calls = calls
    return check


SALE = PriceResult(current_price=28.0, list_price=40.0, html="<html/>")
FULL_PRICE = PriceResult(current_price=40.0, list_price=None, html="<html/>")
NO_PRICE = PriceResult(current_price=None, list_price=None, html="<html/>")
URL = "https://shop.example.com/products/faith-tee"


def _run(ledger, incoming, results, resolve=_ok, owned_urls=(), owned_names=()):
    check = _checker(results)
    out = check_finds(
        ledger, incoming, check=check, resolve=resolve,
        owned_urls=set(owned_urls), owned_names=set(owned_names), today=TODAY,
    )
    return out, check


# --- discount test -------------------------------------------------------------

def test_is_on_sale_needs_crossed_out_price_above_current():
    assert is_on_sale(SALE)
    assert not is_on_sale(FULL_PRICE)
    assert not is_on_sale(NO_PRICE)
    assert not is_on_sale(PriceResult(current_price=40.0, list_price=40.0))
    assert not is_on_sale(PriceResult(current_price=45.0, list_price=40.0))
    assert not is_on_sale(PriceResult(current_price=0.0, list_price=40.0))


# --- new finds -------------------------------------------------------------------

def test_new_find_on_sale_is_tracked_and_shown():
    out, check = _run(load_ledger(None), _incoming(_find()), {URL: SALE})
    entry = out["items"][url_key(URL)]
    assert entry["on_sale"] is True
    assert entry["current_price"] == 28.0
    assert entry["list_price"] == 40.0
    assert entry["category"] == "Casual"
    assert entry["image_url"].endswith("faith-tee.jpg")
    assert entry["found_at"] == "2026-11-09"
    assert entry["last_checked"] == "2026-11-09"
    assert entry["misses"] == 0
    assert out["dropped"] == []
    assert out["source_generated_at"] == "2026-11-09T03:00:00Z"
    assert check.calls == [URL]


def test_finder_seen_prices_are_ignored():
    # Finder said $28 / $40, but the store shows full price now: not a find.
    out, _ = _run(load_ledger(None), _incoming(_find()), {URL: FULL_PRICE})
    assert out["items"] == {}
    assert "no longer on sale" in out["dropped"][0]["reason"]


def test_invalid_finds_are_dropped_without_a_store_check():
    incoming = _incoming(
        _find(url="https://a.example.com/p/1", category="Toys"),
        _find(url="https://a.example.com/p/2", image_url=""),
        _find(url="", name="No url"),
        _find(url="https://a.example.com/p/3", name=""),
    )
    out, check = _run(load_ledger(None), incoming, {})
    assert out["items"] == {}
    assert len(out["dropped"]) == 4
    assert all(d["reason"].startswith("invalid find") for d in out["dropped"])
    assert check.calls == []


def test_duplicate_urls_in_incoming_are_checked_once():
    incoming = _incoming(_find(), _find(url=URL + "?utm_source=x"))
    out, check = _run(load_ledger(None), incoming, {URL: SALE})
    assert len(out["items"]) == 1
    assert len(check.calls) == 1


# --- not already his -----------------------------------------------------------

def test_find_already_on_his_list_by_url_is_dropped():
    out, check = _run(
        load_ledger(None), _incoming(_find()), {URL: SALE},
        owned_urls={url_key("http://www.shop.example.com/products/faith-tee/")},
    )
    assert out["items"] == {}
    assert "already his" in out["dropped"][0]["reason"]
    assert check.calls == []


def test_find_already_his_by_name_is_dropped():
    out, _ = _run(
        load_ledger(None), _incoming(_find(name="Faith  Boxy TEE")), {URL: SALE},
        owned_names={"faith boxy tee"},
    )
    assert out["items"] == {}


def test_owned_keys_cover_wishes_store_links_inventory_and_taste():
    items = [
        Item(name="Wish One", listed_price=10.0, url="https://a.example.com/one?utm_source=g"),
        Item(name="Wish Two", listed_price=20.0, store_urls=[
            StoreLink(url="https://b.example.com/two", display_name="B", listed_price=20.0),
            StoreLink(url="https://www.c.example.com/two/", display_name="C", listed_price=21.0),
        ]),
    ]
    inventory = {"items": {"https://d.example.com/old": {"name": "Old Wish"}}}
    taste = {"items": {"holy vibes tee": {"name": "HOLY VIBES Tee"}}}
    urls, names = owned_keys(items, inventory, taste)
    for u in ("https://a.example.com/one", "https://b.example.com/two",
              "https://c.example.com/two", "https://d.example.com/old"):
        assert url_key(u) in urls
    assert {"wish one", "wish two", "old wish", "holy vibes tee"} <= names


def test_url_key_ignores_tracking_scheme_www_and_trailing_slash():
    assert url_key("https://www.Shop.example.com/p/1/?utm_source=x&color=red") == \
        url_key("http://shop.example.com/p/1?color=red")
    assert url_key("https://shop.example.com/p/1?color=red") != \
        url_key("https://shop.example.com/p/1?color=blue")


# --- repeat until off sale -----------------------------------------------------------

def _tracked(on_sale=True, misses=0, found_at="2026-11-05"):
    entry = {
        "url": URL, "name": "Faith Boxy Tee", "store": "shop.example.com",
        "category": "Casual", "image_url": "https://shop.example.com/cdn/faith-tee.jpg",
        "similar_to": "x", "found_at": found_at, "last_checked": "2026-11-05",
        "current_price": 28.0, "list_price": 40.0, "on_sale": on_sale, "misses": misses,
    }
    ledger = load_ledger(None)
    ledger["items"][url_key(URL)] = entry
    ledger["source_generated_at"] = "2026-11-05T03:00:00Z"
    return ledger


def test_tracked_find_still_on_sale_is_kept_and_rechecked():
    out, check = _run(_tracked(), _incoming(), {URL: PriceResult(current_price=25.0, list_price=40.0)})
    entry = out["items"][url_key(URL)]
    assert entry["on_sale"] is True
    assert entry["current_price"] == 25.0
    assert entry["found_at"] == "2026-11-05"
    assert entry["last_checked"] == "2026-11-09"
    assert check.calls == [URL]


def test_tracked_find_off_sale_is_dropped():
    out, _ = _run(_tracked(), _incoming(), {URL: FULL_PRICE})
    assert out["items"] == {}
    assert out["dropped"][0]["url"] == URL
    assert "no longer on sale" in out["dropped"][0]["reason"]


def test_sold_out_find_is_dropped():
    def sold_out(name, url, pr):
        return pr, "sold_out", "out of stock", 0.8

    out, _ = _run(_tracked(), _incoming(), {URL: SALE}, resolve=sold_out)
    assert out["items"] == {}
    assert "sold out" in out["dropped"][0]["reason"]


def test_wrong_product_is_dropped():
    def mismatch(name, url, pr):
        return pr, "review", "product name mismatch (score 0.20)", 0.2

    out, _ = _run(_tracked(), _incoming(), {URL: SALE}, resolve=mismatch)
    assert out["items"] == {}
    assert "mismatch" in out["dropped"][0]["reason"]


def test_unreadable_find_is_kept_hidden_then_dropped_after_max_misses():
    assert MAX_MISSES == 2
    out, _ = _run(_tracked(), _incoming(), {URL: NO_PRICE})
    entry = out["items"][url_key(URL)]
    assert entry["on_sale"] is False
    assert entry["misses"] == 1
    assert entry["current_price"] == 28.0  # last known price kept

    out2, _ = _run(out, _incoming(), {URL: NO_PRICE})
    assert out2["items"] == {}
    assert "unreadable" in out2["dropped"][0]["reason"]


def test_unreadable_variants_count_as_misses():
    def blank_identity(name, url, pr):
        return pr, "review", "dead link (404)", 0.0

    for results, resolve in (
        ({URL: PriceResult(unavailable=True, reason="blocked")}, _ok),
        ({URL: RuntimeError("boom")}, _ok),
        ({URL: SALE}, blank_identity),
    ):
        out, _ = _run(_tracked(), _incoming(), results, resolve=resolve)
        assert out["items"][url_key(URL)]["misses"] == 1, results


def test_a_readable_check_resets_misses():
    out, _ = _run(_tracked(on_sale=False, misses=1), _incoming(), {URL: SALE})
    entry = out["items"][url_key(URL)]
    assert entry["misses"] == 0
    assert entry["on_sale"] is True


def test_tracked_find_that_lands_on_his_list_is_dropped():
    out, check = _run(_tracked(), _incoming(), {URL: SALE}, owned_urls={url_key(URL)})
    assert out["items"] == {}
    assert check.calls == []


def test_incoming_url_already_tracked_keeps_original_found_at():
    out, check = _run(_tracked(found_at="2026-11-02"), _incoming(_find()), {URL: SALE})
    assert out["items"][url_key(URL)]["found_at"] == "2026-11-02"
    assert len(check.calls) == 1


def test_same_finder_output_is_not_merged_twice():
    # Finder did not run since last check: its retired finds must not come back.
    ledger = load_ledger(None)
    ledger["source_generated_at"] = "2026-11-09T03:00:00Z"
    out, check = _run(ledger, _incoming(_find()), {URL: SALE})
    assert out["items"] == {}
    assert check.calls == []


def test_tracked_finds_are_capped_keeping_newest():
    incoming = _incoming(*[
        _find(url=f"https://shop.example.com/p/{i}",
              found_at=f"2026-{10 + i // 30:02d}-{1 + i % 28:02d}")
        for i in range(MAX_TRACKED + 5)
    ])
    results = {f"https://shop.example.com/p/{i}": SALE for i in range(MAX_TRACKED + 5)}
    out, check = _run(load_ledger(None), incoming, results)
    assert len(out["items"]) == MAX_TRACKED
    assert len(check.calls) == MAX_TRACKED
    capped = [d for d in out["dropped"] if "cap" in d["reason"]]
    assert len(capped) == 5
    kept_dates = sorted(e["found_at"] for e in out["items"].values())
    dropped_urls = {d["url"] for d in capped}
    dropped_dates = [f["found_at"] for f in incoming["finds"] if f["url"] in dropped_urls]
    assert max(dropped_dates) <= min(kept_dates)


# --- files -------------------------------------------------------------------------

def test_load_incoming_handles_missing_corrupt_and_wrong_shape(tmp_path):
    assert load_incoming(None) == {"generated_at": None, "finds": []}
    assert load_incoming(tmp_path / "nope.json") == {"generated_at": None, "finds": []}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert load_incoming(bad)["finds"] == []
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"finds": "x"}))
    assert load_incoming(wrong)["finds"] == []
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"version": 1, "generated_at": "g", "finds": [_find(), "junk"]}))
    loaded = load_incoming(good)
    assert loaded["generated_at"] == "g"
    assert loaded["finds"] == [_find()]


def test_ledger_round_trip_and_defaults(tmp_path):
    path = tmp_path / "state" / "tracked_finds.json"
    assert load_ledger(path) == {"version": 1, "source_generated_at": None, "items": {}}
    out, _ = _run(load_ledger(path), _incoming(_find()), {URL: SALE})
    save_ledger(path, out)
    again = load_ledger(path)
    assert again["items"] == out["items"]
    assert again["checked_at"] == "2026-11-09"
    path.write_text("[]")
    assert load_ledger(path)["items"] == {}


def test_owned_finds_do_not_take_cap_slots():
    owned = [_find(url=f"https://shop.example.com/owned/{i}", found_at="2026-12-01")
             for i in range(5)]
    fresh = [_find(url=f"https://shop.example.com/p/{i}", found_at="2026-11-01")
             for i in range(MAX_TRACKED)]
    results = {f["url"]: SALE for f in fresh}
    out, _ = _run(load_ledger(None), _incoming(*owned, *fresh), results,
                  owned_urls={url_key(f["url"]) for f in owned})
    assert len(out["items"]) == MAX_TRACKED
    assert not [d for d in out["dropped"] if "cap" in d["reason"]]
