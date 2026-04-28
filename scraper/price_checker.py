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


_PRICE_NUM_RE = re.compile(r"(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+\.\d+|\d+)")


@dataclass
class PriceResult:
    current_price: Optional[float] = None
    unavailable: bool = False
    reason: Optional[str] = None
    html: Optional[str] = None


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


def _fetch_via_playwright(url: str, page) -> Optional[str]:
    page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    return page.content()


def check_price(url: str, session, error_log, page=None) -> PriceResult:
    headers = {"User-Agent": random.choice(USER_AGENTS)}
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
        unavailable=False,
        html=html,
    )
