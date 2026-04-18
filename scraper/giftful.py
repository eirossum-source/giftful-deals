from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List
from urllib.parse import urlparse

from bs4 import BeautifulSoup


GIFTFUL_URL = "https://giftful.com/isaacrossum"


class GiftfulEmptyListError(RuntimeError):
    pass


@dataclass
class Item:
    name: str
    url: str
    listed_price: float
    image_url: str

    @property
    def domain(self) -> str:
        return urlparse(self.url).netloc


_PRICE_RE = re.compile(r"(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+\.\d+|\d+)")


def _parse_price(text: str) -> float | None:
    if not text:
        return None
    match = _PRICE_RE.search(text.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def parse_items(html: str) -> List[Item]:
    soup = BeautifulSoup(html, "lxml")
    items: List[Item] = []

    candidates = soup.select(
        "[data-item-id], article.wish-item, li.wish-item, .wish-item"
    )
    if not candidates:
        candidates = [
            a.find_parent()
            for a in soup.find_all("a", href=True)
            if _is_external(a.get("href", ""))
        ]

    seen_urls: set[str] = set()
    for card in candidates:
        if card is None:
            continue
        link = card.find("a", href=True)
        if link is None or not _is_external(link["href"]):
            continue
        url = link["href"]
        if url in seen_urls:
            continue
        seen_urls.add(url)

        name_el = card.find(["h1", "h2", "h3", "h4"]) or link
        name = name_el.get_text(strip=True) if name_el else ""

        price_el = card.find(class_=re.compile(r"price", re.I))
        listed_price = _parse_price(price_el.get_text()) if price_el else None

        img = card.find("img")
        image_url = img["src"] if img and img.has_attr("src") else ""

        if not name or listed_price is None:
            continue

        items.append(
            Item(
                name=name,
                url=url,
                listed_price=listed_price,
                image_url=image_url,
            )
        )

    if not items:
        raise GiftfulEmptyListError(
            "Parsed Giftful page but found no items. Page structure may have changed."
        )

    return items


def _is_external(href: str) -> bool:
    if not href:
        return False
    if href.startswith(("#", "/", "mailto:", "javascript:")):
        return False
    parsed = urlparse(href)
    if not parsed.netloc:
        return False
    return "giftful.com" not in parsed.netloc


def resolve_redirect(url: str, session) -> str:
    try:
        resp = session.head(url, allow_redirects=True, timeout=15)
        return resp.url or url
    except Exception:
        return url


def fetch_list(page_url: str = GIFTFUL_URL, session=None) -> List[Item]:
    """Live fetch of the Giftful wishlist via headless Chromium.

    Integration-tested manually; unit tests cover parse_items and
    resolve_redirect independently.
    """
    from playwright.sync_api import sync_playwright
    import requests

    session = session or requests.Session()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(page_url, wait_until="networkidle", timeout=60_000)
        html = page.content()
        browser.close()

    items = parse_items(html)
    for item in items:
        item.url = resolve_redirect(item.url, session)
    return items
