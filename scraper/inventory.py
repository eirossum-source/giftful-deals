from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


_TRACKING_PARAM_PREFIXES = (
    "utm_",
    "awc",
    "sv1",
    "sv2",
    "sv_",
    "acquisitionsource",
    "linkcode",
    "tag",
    "ref_",
    "ref",
    "affid",
    "aff",
    "_branch_match_id",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
)


def _is_tracking(key: str) -> bool:
    k = key.lower()
    return any(k == p or k.startswith(p) for p in _TRACKING_PARAM_PREFIXES)


def normalize_url(url: str) -> str:
    if not url:
        return url
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    kept = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=False) if not _is_tracking(k)]
    new_query = urlencode(kept)
    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, "")
    )


def load_state(path: Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {"items": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"items": {}}
    if not isinstance(data, dict) or "items" not in data:
        return {"items": {}}
    return data


def save_state(path: Path, state: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def update_item(
    state: dict,
    *,
    url: str,
    name: str,
    in_stock: bool,
    current_price: Optional[float],
    listed_price: float,
    today: Optional[date] = None,
    identity_score: Optional[float] = None,
) -> None:
    today = today or date.today()
    items = state.setdefault("items", {})
    prev = items.get(url, {})

    if in_stock:
        sold_out_since = None
    else:
        sold_out_since = prev.get("sold_out_since") or today.isoformat()

    # Carry forward last known identity score when the current run didn't
    # produce one (e.g., sold-out paths skip identity scoring). Avoids
    # losing soft-fail rescue context across runs.
    resolved_identity = (
        identity_score
        if identity_score is not None
        else prev.get("identity_score")
    )

    items[url] = {
        "name": name,
        "last_seen": today.isoformat(),
        "in_stock": bool(in_stock),
        "prev_in_stock": prev.get("in_stock") if prev else None,
        "current_price": current_price,
        "listed_price": listed_price,
        "sold_out_since": sold_out_since,
        "identity_score": resolved_identity,
    }


def is_back_in_stock(prev_state: dict, url: str, currently_in_stock: bool) -> bool:
    if not currently_in_stock:
        return False
    prev = (prev_state or {}).get("items", {}).get(url)
    if not prev:
        return False
    if prev.get("in_stock") is False:
        return True
    if prev.get("prev_in_stock") is False:
        return True
    return False
