from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup


GIFTFUL_URL = "https://giftful.com/isaacrossum"

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)


class GiftfulEmptyListError(RuntimeError):
    pass


@dataclass
class StoreLink:
    url: str
    display_name: str
    listed_price: float

    @property
    def domain(self) -> str:
        return urlparse(self.url).netloc


@dataclass
class Category:
    name: str
    url: str
    item_count: int = 0


class Item:
    def __init__(
        self,
        name: str,
        listed_price: float,
        image_url: str = "",
        category: str = "",
        store_urls: Optional[List[StoreLink]] = None,
        url: str = "",
    ):
        self.name = name
        self.listed_price = listed_price
        self.image_url = image_url
        self.category = category
        self.store_urls = list(store_urls) if store_urls else []
        self._url = url

    @property
    def url(self) -> str:
        if self._url:
            return self._url
        if self.store_urls:
            return self.store_urls[0].url
        return ""

    @property
    def domain(self) -> str:
        u = self.url
        return urlparse(u).netloc if u else ""


_PRICE_RE = re.compile(r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)")


def _parse_price(text: str) -> Optional[float]:
    if not text:
        return None
    match = _PRICE_RE.search(text)
    if not match:
        return None
    raw = match.group(1).replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_categories(html: str, base_url: str) -> List[Category]:
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    out: List[Category] = []
    for a in soup.select('a[href*="/wishlists/"]'):
        href = a.get("href") or ""
        if not href:
            continue
        full_url = urljoin(base_url, href)
        if full_url in seen:
            continue
        name_el = a.find("h2")
        if name_el is None:
            continue
        name = name_el.get_text(strip=True)
        if not name:
            continue
        count = 0
        for div in a.find_all("div"):
            txt = div.get_text(strip=True)
            if "Wish" in txt:
                m = re.search(r"(\d+)", txt)
                if m:
                    count = int(m.group(1))
                    break
        seen.add(full_url)
        out.append(Category(name=name, url=full_url, item_count=count))
    return out


def parse_items(html: str, category_name: str = "") -> List[Item]:
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    out: List[Item] = []
    for btn in soup.find_all("button"):
        if btn.find("img", alt="Feature Image") is None:
            continue
        if btn.find("img", alt="Claimed") is not None:
            continue

        name_el = btn.select_one(".leading-5")
        name = name_el.get_text(strip=True) if name_el else ""
        if not name:
            continue

        price: Optional[float] = None
        for div in btn.find_all("div"):
            txt = div.get_text(strip=True)
            if txt.startswith("$"):
                price = _parse_price(txt)
                if price is not None:
                    break
        if price is None:
            continue

        thumb = ""
        for im in btn.find_all("img", alt="Feature Image"):
            cls = set(im.get("class") or [])
            if "hidden" in cls and "dark:flex" in cls:
                continue
            src = im.get("src") or ""
            if src:
                thumb = src
                break

        out.append(
            Item(
                name=name,
                listed_price=price,
                image_url=thumb,
                category=category_name,
            )
        )
    return out


def parse_modal(
    html: str,
) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    if not html:
        return (None, None, None)
    soup = BeautifulSoup(html, "lxml")
    dlg = soup.select_one('[role="dialog"]')
    if dlg is None:
        return (None, None, None)

    h3 = dlg.find("h3")
    name = h3.get_text(strip=True) if h3 else None

    listed_price: Optional[float] = None
    price_container = dlg.find(class_="text-xl")
    if price_container is not None:
        for div in price_container.find_all("div"):
            txt = div.get_text(strip=True)
            if txt.startswith("$"):
                listed_price = _parse_price(txt)
                if listed_price is not None:
                    break

    view_online_url: Optional[str] = None
    btn = dlg.select_one("a.btn-submit")
    if btn is not None:
        href = btn.get("href")
        if href:
            view_online_url = href

    return (name, listed_price, view_online_url)


_REDIRECT_HOSTS = {
    "skimresources.com": "url",
    "viglink.com": "u",
}


def extract_destination_url(url: str) -> str:
    if not url:
        return url
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    host = (parsed.netloc or "").lower()
    for suffix, param in _REDIRECT_HOSTS.items():
        if host == suffix or host.endswith("." + suffix):
            params = parse_qs(parsed.query)
            values = params.get(param)
            if values and values[0]:
                return values[0]
            return url
    return url


def resolve_redirect(url: str, session) -> str:
    extracted = extract_destination_url(url)
    if extracted != url:
        return extracted
    try:
        resp = session.head(url, allow_redirects=True, timeout=15)
        return resp.url or url
    except Exception:
        return url


def fetch_list(profile_url: str = GIFTFUL_URL, session=None) -> List[Item]:
    """Live fetch of the Giftful wishlists via Playwright.

    Walks profile -> each category -> each item modal, harvesting retailer
    StoreLinks and unwrapping affiliate redirects. Integration-tested
    manually; unit tests cover parse_categories, parse_items, parse_modal,
    and resolve_redirect independently.
    """
    from playwright.sync_api import sync_playwright
    import requests

    session = session or requests.Session()

    all_items: List[Item] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=_USER_AGENT, viewport={"width": 1280, "height": 900}
        )
        page = ctx.new_page()

        page.goto(profile_url, wait_until="networkidle", timeout=60_000)
        categories = parse_categories(page.content(), base_url=profile_url)
        if not categories:
            browser.close()
            raise GiftfulEmptyListError(
                "No categories discovered on profile page."
            )

        for cat in categories:
            page.goto(cat.url, wait_until="networkidle", timeout=60_000)
            items = parse_items(page.content(), category_name=cat.name)
            cards = page.locator('button:has(img[alt="Feature Image"]):not(:has(img[alt="Claimed"]))')
            n = min(cards.count(), len(items))

            for idx in range(n):
                view_online_url: Optional[str] = None
                try:
                    card = cards.nth(idx)
                    card.scroll_into_view_if_needed(timeout=3_000)
                    card.click(timeout=5_000)
                    page.wait_for_selector(
                        '[role="dialog"] h3', state="visible", timeout=10_000
                    )
                    page.wait_for_timeout(500)
                    _n, _p, view_online_url = parse_modal(page.content())
                except Exception:
                    view_online_url = None

                if view_online_url:
                    resolved_url = resolve_redirect(view_online_url, session)
                    domain = urlparse(resolved_url).netloc
                    display = re.sub(r"^www\.", "", domain)
                    items[idx].store_urls = [
                        StoreLink(
                            url=resolved_url,
                            display_name=display,
                            listed_price=items[idx].listed_price,
                        )
                    ]

                try:
                    page.keyboard.press("Escape")
                    page.wait_for_selector(
                        '[role="dialog"] h3', state="hidden", timeout=5_000
                    )
                except Exception:
                    pass

            all_items.extend(items)

        browser.close()

    if not all_items:
        raise GiftfulEmptyListError("No items found across all categories.")
    return all_items
