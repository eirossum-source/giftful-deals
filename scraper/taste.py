from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import List, Optional

from giftful import Item


def _key(name: str) -> str:
    return re.sub(r"\s+", " ", name or "").strip().lower()


def load_taste(path: Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {"items": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"items": {}}
    if not isinstance(data, dict) or not isinstance(data.get("items"), dict):
        return {"items": {}}
    return data


def save_taste(path: Path, state: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def merge_claimed(state: dict, items: List[Item], today: Optional[date] = None) -> None:
    """Fold checked-off items into taste state, de-duplicated by normalised name.

    Accumulates across runs: an item stays once seen, even if Giftful later
    drops it. An item claimed on several lists keeps one entry listing them all.
    """
    today = (today or date.today()).isoformat()
    entries = state.setdefault("items", {})
    for item in items:
        key = _key(item.name)
        if not key:
            continue
        entry = entries.get(key)
        if entry is None:
            entry = {
                "name": item.name.strip(),
                "price": item.listed_price,
                "image_url": item.image_url,
                "lists": [],
                "first_seen": today,
            }
            entries[key] = entry
        if item.category and item.category not in entry["lists"]:
            entry["lists"].append(item.category)
        entry["last_seen"] = today


def refresh_taste(fetch, path: Path, today: Optional[date] = None) -> Optional[int]:
    """Fetch checked-off items and merge them into the taste file.

    Never raises: taste is a side job and must not block the deals email.
    Returns the number of items fetched, or None if the fetch failed.
    """
    try:
        items = fetch()
        state = load_taste(path)
        merge_claimed(state, items, today)
        save_taste(path, state)
    except Exception as exc:  # noqa: BLE001 — side job, report and move on
        print(f"taste refresh skipped: {exc}")
        return None
    return len(items)
