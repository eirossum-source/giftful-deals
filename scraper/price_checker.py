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


SALE_PATTERNS = [
    re.compile(r"\bsale\b", re.I),
    re.compile(r"\d+\s*%\s*off", re.I),
    re.compile(r"\bnow\s*:", re.I),
    re.compile(r"limited\s+time", re.I),
]

_PRICE_NUM_RE = re.compile(r"(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+\.\d+|\d+)")


@dataclass
class PriceResult:
    current_price: Optional[float] = None
    sale_detected: bool = False
    unavailable: bool = False
    reason: Optional[str] = None


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
    for extractor in (_extract_jsonld, _extract_meta, _extract_css):
        price = extractor(soup)
        if price is not None:
            return price
    return None


def detect_sale(html: str) -> bool:
    soup = BeautifulSoup(html, "lxml")
    if soup.find(["s", "strike", "del"]):
        return True
    text = soup.get_text(" ", strip=True)
    return any(pat.search(text) for pat in SALE_PATTERNS)


def check_price(url: str, session, error_log) -> PriceResult:
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    time.sleep(random.uniform(1.0, 3.0))
    try:
        resp = session.get(url, headers=headers, timeout=20)
    except Exception as exc:
        error_log.error(f"price fetch failed for {url}: {exc}")
        return PriceResult(unavailable=True, reason="network")

    if resp.status_code in (403, 429) or "captcha" in (resp.text or "").lower():
        error_log.error(
            f"price unavailable for {url} (status {resp.status_code})"
        )
        return PriceResult(unavailable=True, reason="blocked")
    if resp.status_code >= 400:
        error_log.error(f"price fetch {resp.status_code} for {url}")
        return PriceResult(unavailable=True, reason=f"http_{resp.status_code}")

    html = resp.text or ""
    return PriceResult(
        current_price=extract_price(html),
        sale_detected=detect_sale(html),
        unavailable=False,
    )
