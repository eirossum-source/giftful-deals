"""Re-check the finder's finds at the store and track them until they are off sale.

Input: `state/finds.json` from the `claude/finds` branch (contract: finder/PROMPT.md), copied
to a temp file by the workflow. Output: `state/tracked_finds.json` on main. A find is shown
(`on_sale: true`) only when this run read a crossed-out price above the current price, in
stock, on the right product, and it is not already on Isaac's list or already his.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Callable, Iterable, Optional, Set, Tuple
from urllib.parse import urlparse, urlunparse

from inventory import normalize_url

CATEGORIES = ("Accessories", "Athleisure", "Casual", "Jackets", "Shoes", "Tech")
MAX_MISSES = 2  # unreadable this many runs in a row -> dropped
MAX_TRACKED = 60  # bounds run time; newest unliked finds kept (liked ones are exempt)
DISLIKED_REASON = "you said \U0001F44E"


def url_key(url: str) -> str:
    """Comparison key: no tracking params, scheme, `www.`, case in host or trailing slash."""
    parsed = urlparse(normalize_url((url or "").strip()))
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/")
    return urlunparse(("", host, path, parsed.params, parsed.query, "")).lstrip("/")


def name_key(name: str) -> str:
    return re.sub(r"\s+", " ", name or "").strip().lower()


def is_on_sale(price_result) -> bool:
    cur = price_result.current_price
    lst = price_result.list_price
    if cur is None or lst is None:
        return False
    return 0 < round(cur, 2) < round(lst, 2)


def owned_keys(items: Iterable, inventory_state: dict, taste_state: dict) -> Tuple[Set[str], Set[str]]:
    """URLs and names that are already his: this run's wishes, last run's inventory, taste."""
    urls: Set[str] = set()
    names: Set[str] = set()
    for item in items or []:
        urls.add(url_key(item.url))
        for store in getattr(item, "store_urls", None) or []:
            urls.add(url_key(store.url))
        names.add(name_key(item.name))
    for url, entry in ((inventory_state or {}).get("items") or {}).items():
        urls.add(url_key(url))
        names.add(name_key((entry or {}).get("name", "")))
    for key, entry in ((taste_state or {}).get("items") or {}).items():
        names.add(name_key(key))
        names.add(name_key((entry or {}).get("name", "")))
    urls.discard("")
    names.discard("")
    return urls, names


def load_incoming(path: Optional[Path]) -> dict:
    empty = {"generated_at": None, "finds": []}
    if path is None:
        return empty
    p = Path(path)
    if not p.exists():
        return empty
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return empty
    if not isinstance(data, dict) or not isinstance(data.get("finds"), list):
        return empty
    return {
        "generated_at": data.get("generated_at"),
        "finds": [f for f in data["finds"] if isinstance(f, dict)],
    }


def load_ledger(path: Optional[Path]) -> dict:
    empty = {"version": 1, "source_generated_at": None, "items": {}}
    if path is None:
        return empty
    p = Path(path)
    if not p.exists():
        return empty
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return empty
    if not isinstance(data, dict) or not isinstance(data.get("items"), dict):
        return empty
    return data


def save_ledger(path: Path, ledger: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8")


def _str(raw: dict, field: str) -> str:
    value = raw.get(field)
    return value.strip() if isinstance(value, str) else ""


def _from_incoming(raw: dict, today: date) -> Tuple[Optional[dict], Optional[str]]:
    url = _str(raw, "url")
    name = _str(raw, "name")
    image_url = _str(raw, "image_url")
    category = _str(raw, "category")
    if not url.startswith(("http://", "https://")):
        return None, "invalid find (no product url)"
    if not name:
        return None, "invalid find (no name)"
    if not image_url:
        return None, "invalid find (no image)"
    if category not in CATEGORIES:
        return None, f"invalid find (category {category!r} is not a Giftful list)"
    store = _str(raw, "store") or urlparse(url).netloc
    if store.lower().startswith("www."):
        store = store[4:]
    return {
        "url": normalize_url(url),
        "name": name,
        "store": store,
        "category": category,
        "image_url": image_url,
        "similar_to": _str(raw, "similar_to"),
        "found_at": _str(raw, "found_at") or today.isoformat(),
        "last_checked": None,
        "current_price": None,
        "list_price": None,
        "on_sale": False,
        "misses": 0,
    }, None


def _drop(dropped: list, entry_or_raw: dict, reason: str) -> None:
    dropped.append({
        "url": entry_or_raw.get("url") or "",
        "name": entry_or_raw.get("name") or "",
        "reason": reason,
    })


def check_finds(
    ledger: dict,
    incoming: dict,
    *,
    check: Callable,
    resolve: Callable,
    owned_urls: Set[str],
    owned_names: Set[str],
    today: Optional[date] = None,
    liked: Iterable[str] = frozenset(),
    disliked: Iterable[str] = frozenset(),
) -> dict:
    """Merge new finds into the ledger, re-check every tracked find, return the new ledger.

    `liked` / `disliked` are `url_key`s he voted on: disliked finds are never (re)added and are
    removed; liked finds stay tracked (off sale) when they go off sale or sell out.

    `check(url)` returns a PriceResult. `resolve(name, url, price_result)` returns
    `(price_result, status, reason, identity_score)` like main._resolve_identity.
    """
    today = today or date.today()
    liked = set(liked or ())
    disliked = set(disliked or ())
    items = dict((ledger or {}).get("items") or {})
    source = (ledger or {}).get("source_generated_at")
    dropped: list = []

    generated_at = (incoming or {}).get("generated_at")
    if not (generated_at and generated_at == source):
        for raw in (incoming or {}).get("finds") or []:
            entry, reason = _from_incoming(raw, today)
            if entry is None:
                _drop(dropped, raw, reason)
                continue
            key = url_key(entry["url"])
            if key in disliked:
                _drop(dropped, entry, DISLIKED_REASON)
                continue
            if key not in items:
                items[key] = entry
        if generated_at:
            source = generated_at

    for key, entry in list(items.items()):
        if key in disliked:
            _drop(dropped, entry, DISLIKED_REASON)
            del items[key]
            continue
        if key in owned_urls or name_key(entry.get("name")) in owned_names:
            _drop(dropped, entry, "already his (on his list or checked off)")
            del items[key]

    unliked = [(k, e) for k, e in items.items() if k not in liked]
    if len(unliked) > MAX_TRACKED:
        ordered = sorted(unliked, key=lambda kv: kv[1].get("found_at") or "", reverse=True)
        for key, entry in ordered[MAX_TRACKED:]:
            _drop(dropped, entry, f"over the {MAX_TRACKED}-find cap")
            del items[key]

    kept: dict = {}
    for key, entry in items.items():
        entry = dict(entry)
        outcome, reason, result = _check_one(entry, check, resolve)
        entry["last_checked"] = today.isoformat()
        if outcome == "on_sale":
            entry.update(
                current_price=result.current_price,
                list_price=result.list_price,
                on_sale=True,
                misses=0,
            )
            kept[key] = entry
        elif outcome == "miss":
            entry["misses"] = int(entry.get("misses") or 0) + 1
            entry["on_sale"] = False
            if entry["misses"] >= MAX_MISSES:
                _drop(dropped, entry, f"unreadable {entry['misses']} runs in a row ({reason})")
            else:
                kept[key] = entry
        elif key in liked and _keeps_when_liked(reason):
            entry["on_sale"] = False
            entry["misses"] = 0
            if result is not None and result.current_price is not None:
                entry["current_price"] = result.current_price
                entry["list_price"] = result.list_price
            kept[key] = entry
        else:
            _drop(dropped, entry, reason)

    return {
        "version": 1,
        "checked_at": today.isoformat(),
        "source_generated_at": source,
        "items": kept,
        "dropped": dropped,
    }


def _keeps_when_liked(reason: Optional[str]) -> bool:
    """A liked find survives going off sale or selling out (not a wrong product)."""
    return bool(reason) and (reason == "sold out" or reason.startswith("no longer on sale"))


def _check_one(entry: dict, check: Callable, resolve: Callable):
    """Return (outcome, reason, price_result); outcome is on_sale / miss / drop."""
    try:
        result = check(entry["url"])
        if result.unavailable:
            return "miss", f"store unavailable ({result.reason})", result
        result, status, reason, score = resolve(entry["name"], entry["url"], result)
    except Exception as exc:  # noqa: BLE001 — one bad page must not stop the run
        return "miss", f"error: {exc}", None

    if status == "sold_out":
        return "drop", "sold out", result
    if status == "review":
        if score and score > 0:
            return "drop", reason or "wrong product", result
        return "miss", reason or "page unreadable", result
    if status == "skip" or result.current_price is None:
        return "miss", "no price on the page", result
    if not is_on_sale(result):
        if result.list_price is None:
            return "drop", f"no longer on sale (no crossed-out price, now ${result.current_price:.2f})", result
        return "drop", (
            f"no longer on sale (crossed-out ${result.list_price:.2f}, "
            f"now ${result.current_price:.2f})"
        ), result
    return "on_sale", None, result
