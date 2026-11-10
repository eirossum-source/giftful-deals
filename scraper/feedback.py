"""S4c — like / dislike votes on finds.

Votes travel as prefilled GitHub issues on the (public) repo: each 👍 / 👎 button is a link to
the new-issue form; he taps it and then "Submit new issue". The deals run reads open issues
written by the repo owner, records them in `state/feedback.json` and the workflow closes them.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Callable, Optional, Set, Tuple
from urllib.parse import quote, urlencode

import requests

from finds import url_key

REPO = os.environ.get("GITHUB_REPOSITORY") or "eirossum-source/giftful-deals"
OWNER = REPO.split("/")[0]
MARKER = "<!-- giftful-feedback v1 -->"
VOTES = ("like", "dislike")
_TITLES = {"like": "\U0001F44D Like", "dislike": "\U0001F44E Dislike"}
_FIELD = re.compile(r"^\s*([a-z_]+)\s*:\s*(.*?)\s*$")


def _empty() -> dict:
    return {"version": 1, "items": {}}


def vote_link(vote: str, entry: dict, repo: Optional[str] = None) -> str:
    """GitHub new-issue URL, prefilled so one tap on "Submit new issue" records the vote."""
    repo = repo or REPO
    name = (entry.get("name") or "").strip()
    title = f"{_TITLES[vote]}: {name[:80]}"
    body = (
        'Tap "Submit new issue" to send this to the giftful-deals finder.\n\n'
        f"{MARKER}\n"
        f"vote: {vote}\n"
        f"url: {entry.get('url') or ''}\n"
        f"name: {name}\n"
        f"category: {entry.get('category') or ''}\n"
        f"store: {entry.get('store') or ''}\n"
    )
    query = urlencode({"title": title, "body": body}, quote_via=quote)
    return f"https://github.com/{repo}/issues/new?{query}"


def parse_issue(issue: dict, owner: str) -> Optional[dict]:
    """Return the vote in a GitHub issue, or None if it is not a valid vote from the owner."""
    if not isinstance(issue, dict) or issue.get("pull_request"):
        return None
    user = issue.get("user") or {}
    login = user.get("login") if isinstance(user, dict) else None
    if not isinstance(login, str) or login.lower() != (owner or "").lower():
        return None
    body = issue.get("body")
    if not isinstance(body, str) or MARKER not in body:
        return None
    fields = {}
    for line in body.split(MARKER, 1)[1].splitlines():
        m = _FIELD.match(line)
        if m and m.group(1) not in fields:
            fields[m.group(1)] = m.group(2)
    vote = fields.get("vote", "").lower()
    url = fields.get("url", "")
    if vote not in VOTES or not url.startswith(("http://", "https://")):
        return None
    created_at = issue.get("created_at") or ""
    return {
        "vote": vote,
        "url": url,
        "name": fields.get("name", ""),
        "category": fields.get("category", ""),
        "store": fields.get("store", ""),
        "voted_at": created_at[:10],
        "issue": issue.get("number"),
        "created_at": created_at,
    }


def fetch_open_issues(repo: str, token: Optional[str], get: Callable = requests.get) -> list:
    """Open issues created by the repo owner. Any error, non-200 or missing token gives []."""
    if not token:
        return []
    owner = repo.split("/")[0]
    try:
        resp = get(
            f"https://api.github.com/repos/{repo}/issues",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            params={"state": "open", "creator": owner, "per_page": 100},
            timeout=30,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:  # noqa: BLE001 — votes are extra; never block the run
        return []
    return data if isinstance(data, list) else []


def load_feedback(path: Optional[Path]) -> dict:
    if path is None:
        return _empty()
    p = Path(path)
    if not p.exists():
        return _empty()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return _empty()
    if not isinstance(data, dict) or not isinstance(data.get("items"), dict):
        return _empty()
    return data


def save_feedback(path: Path, state: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def merge_votes(state: dict, votes: list) -> dict:
    """Apply parsed votes oldest first, so the latest vote per item wins."""
    items = dict((state or {}).get("items") or {})
    for v in sorted(votes, key=lambda v: v.get("created_at") or ""):
        items[url_key(v["url"])] = {
            "vote": v["vote"],
            "url": v["url"],
            "name": v.get("name", ""),
            "category": v.get("category", ""),
            "store": v.get("store", ""),
            "voted_at": v.get("voted_at", ""),
            "issue": v.get("issue"),
        }
    return {"version": 1, "items": items}


def vote_keys(state: dict) -> Tuple[Set[str], Set[str]]:
    liked: Set[str] = set()
    disliked: Set[str] = set()
    for key, entry in ((state or {}).get("items") or {}).items():
        vote = (entry or {}).get("vote")
        if vote == "like":
            liked.add(key)
        elif vote == "dislike":
            disliked.add(key)
    return liked, disliked
