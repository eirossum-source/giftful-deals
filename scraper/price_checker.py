from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup


USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
]


_PRICE_NUM_RE = re.compile(r"(\d+(?:\.\d{1,2})?)")


@dataclass
class PriceResult:
    current_price: Optional[float] = None
    list_price: Optional[float] = None
    unavailable: bool = False
    reason: Optional[str] = None
    html: Optional[str] = None


# Browser fingerprint headers Amazon's bot detection looks for. Without
# these, the requests-based fetch consistently lands on the
# "Click the button below to continue shopping" soft block.
_BROWSER_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


def _to_float(text: str) -> Optional[float]:
    if text is None:
        return None
    cleaned = str(text).replace(",", "").strip()
    match = _PRICE_NUM_RE.search(cleaned)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _extract_jsonld(soup: BeautifulSoup) -> Optional[float]:
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        price = _find_product_price(data)
        if price is not None:
            return price
    return None


def _find_product_price(node) -> Optional[float]:
    if isinstance(node, list):
        for item in node:
            price = _find_product_price(item)
            if price is not None:
                return price
        return None
    if not isinstance(node, dict):
        return None
    type_val = node.get("@type")
    types = type_val if isinstance(type_val, list) else [type_val]
    if "Product" in types:
        offers = node.get("offers")
        if offers:
            price = _price_from_offers(offers)
            if price is not None:
                return price
    # Search nested graphs like @graph
    for value in node.values():
        if isinstance(value, (dict, list)):
            price = _find_product_price(value)
            if price is not None:
                return price
    return None


def _price_from_offers(offers) -> Optional[float]:
    if isinstance(offers, list):
        for offer in offers:
            price = _price_from_offers(offer)
            if price is not None:
                return price
        return None
    if isinstance(offers, dict):
        return _to_float(offers.get("price") or offers.get("lowPrice"))
    return None


def _extract_meta(soup: BeautifulSoup) -> Optional[float]:
    tag = soup.find("meta", attrs={"property": "product:price:amount"})
    if tag and tag.get("content"):
        return _to_float(tag["content"])
    tag = soup.find("meta", attrs={"itemprop": "price"})
    if tag and tag.get("content"):
        return _to_float(tag["content"])
    return None


def _extract_amazon(soup: BeautifulSoup) -> Optional[float]:
    selectors = [
        "#corePrice_feature_div .a-offscreen",
        "span.a-price .a-offscreen",
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el is None:
            continue
        price = _to_float(el.get_text())
        if price is not None:
            return price
    return None


def _extract_css(soup: BeautifulSoup) -> Optional[float]:
    selectors = [
        ".product-price",
        ".sale-price",
        ".price-current",
        ".price-now",
        ".price",
        "[itemprop='price']",
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el is None:
            continue
        price = _to_float(el.get_text())
        if price is not None:
            return price
    return None


def extract_price(html: str) -> Optional[float]:
    soup = BeautifulSoup(html, "lxml")
    for extractor in (_extract_jsonld, _extract_meta, _extract_amazon, _extract_css):
        price = extractor(soup)
        if price is not None:
            return price
    return None


_LIST_PRICE_TYPES = ("listprice", "msrp", "suggestedretailprice", "srp")


def _extract_jsonld_list_price(soup: BeautifulSoup) -> Optional[float]:
    """Walk JSON-LD blocks for a priceSpecification with a list-price type."""
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        price = _walk_for_list_price(data)
        if price is not None:
            return price
    return None


def _walk_for_list_price(node) -> Optional[float]:
    if isinstance(node, list):
        for n in node:
            p = _walk_for_list_price(n)
            if p is not None:
                return p
        return None
    if not isinstance(node, dict):
        return None
    spec = node.get("priceSpecification")
    if isinstance(spec, dict):
        ptype = str(spec.get("priceType") or "").lower().replace("/", "").replace(" ", "")
        if any(t in ptype for t in _LIST_PRICE_TYPES):
            price = _to_float(spec.get("price"))
            if price is not None:
                return price
    if isinstance(spec, list):
        for s in spec:
            if isinstance(s, dict):
                ptype = (
                    str(s.get("priceType") or "")
                    .lower()
                    .replace("/", "")
                    .replace(" ", "")
                )
                if any(t in ptype for t in _LIST_PRICE_TYPES):
                    price = _to_float(s.get("price"))
                    if price is not None:
                        return price
    for v in node.values():
        if isinstance(v, (dict, list)):
            p = _walk_for_list_price(v)
            if p is not None:
                return p
    return None


def extract_list_price(html: str) -> Optional[float]:
    """Return the retailer's strikethrough / MSRP / "List Price" if shown.

    A retailer may display a higher original price next to the live price
    (e.g. Amazon: "List Price $99.99" -> $59.99). Used as a higher
    reference for is_deal so we capture retailer-side sales even when the
    Giftful baseline already matches the live price.
    """
    soup = BeautifulSoup(html, "lxml")

    jsonld = _extract_jsonld_list_price(soup)
    if jsonld is not None:
        return jsonld

    selectors = [
        # Amazon strikethrough
        'span.a-text-price[data-a-strike="true"] .a-offscreen',
        "span.basisPrice .a-offscreen",
        '[data-a-strike="true"] .a-offscreen',
        ".a-text-strike",
        # Shopify / generic strikethrough
        "s.price__sale",
        "del.price",
        ".compare-at-price",
        '[class*="strike"]',
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el is None:
            continue
        price = _to_float(el.get_text(" ", strip=True))
        if price is not None:
            return price
    return None


def _is_amazon_soft_block(page) -> bool:
    if "amazon.com" not in (page.url or "").lower():
        return False
    try:
        title = (page.title() or "").strip().lower()
    except Exception:
        title = ""
    if title not in ("amazon.com", "amazon.ca", ""):
        return False
    try:
        body_snippet = (
            page.evaluate(
                "() => document.body ? document.body.innerText.slice(0, 600) : ''"
            )
            or ""
        ).lower()
    except Exception:
        body_snippet = ""
    return (
        "click the button below to continue" in body_snippet
        or "continue shopping" in body_snippet
    )


def _fetch_via_playwright(url: str, page) -> Optional[str]:
    page.goto(url, wait_until="load", timeout=30_000)
    try:
        page.wait_for_load_state("networkidle", timeout=8_000)
    except Exception:
        pass

    # Amazon "Click the button below to continue shopping" soft block —
    # click through to land on the actual product page.
    try:
        if _is_amazon_soft_block(page):
            link = page.locator(
                "a:has-text('Continue shopping'), button:has-text('Continue shopping')"
            ).first
            if link.count() > 0:
                link.click(timeout=5_000)
                page.wait_for_load_state("load", timeout=15_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=6_000)
                except Exception:
                    pass
    except Exception:
        pass

    return page.content()


def check_price(url: str, session, error_log, page=None) -> PriceResult:
    headers = dict(_BROWSER_HEADERS)
    headers["User-Agent"] = random.choice(USER_AGENTS)
    time.sleep(random.uniform(1.0, 3.0))
    blocked = False
    try:
        resp = session.get(url, headers=headers, timeout=20)
    except Exception as exc:
        error_log.error(f"price fetch failed for {url}: {exc}")
        if page is None:
            return PriceResult(unavailable=True, reason="network")
        resp = None
        blocked = True

    if resp is not None:
        if resp.status_code in (403, 429) or "captcha" in (resp.text or "").lower():
            error_log.error(
                f"price unavailable for {url} (status {resp.status_code})"
            )
            if page is None:
                return PriceResult(unavailable=True, reason="blocked")
            blocked = True
        elif resp.status_code >= 400:
            error_log.error(f"price fetch {resp.status_code} for {url}")
            if page is None:
                return PriceResult(
                    unavailable=True, reason=f"http_{resp.status_code}"
                )
            blocked = True

    if not blocked and resp is not None:
        html = resp.text or ""
        current = extract_price(html)
        if current is not None or page is None:
            return PriceResult(
                current_price=current,
                list_price=extract_list_price(html),
                unavailable=False,
                html=html,
            )

    try:
        html = _fetch_via_playwright(url, page) or ""
    except Exception as exc:
        error_log.error(f"playwright fetch failed for {url}: {exc}")
        return PriceResult(unavailable=True, reason="playwright_error")

    return PriceResult(
        current_price=extract_price(html),
        list_price=extract_list_price(html),
        unavailable=False,
        html=html,
    )
