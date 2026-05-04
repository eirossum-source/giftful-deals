from __future__ import annotations

import json
import os
import re
from typing import Optional, Tuple

from bs4 import BeautifulSoup


_DEAD_PAGE_PATTERNS = [
    (re.compile(r"page\s+not\s+found", re.I), "page not found"),
    (re.compile(r"no\s+longer\s+available", re.I), "no longer available"),
    (re.compile(r"item\s+(?:has\s+been\s+)?removed", re.I), "item removed"),
    (re.compile(r"\bproduct\s+not\s+found\b", re.I), "product not found"),
    (re.compile(r"\b404[\s-]+(?:not\s+found|error|page)\b", re.I), "404"),
    (re.compile(r"this\s+(?:product|item)\s+is\s+unavailable", re.I), "unavailable"),
]


def check_link_integrity(html: str) -> Tuple[bool, Optional[str]]:
    if not html or not html.strip():
        return True, "empty response"

    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    h1 = (soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else "")
    title = (soup.title.get_text(strip=True) if soup.title else "")
    headline_text = f"{h1} {title}".lower()

    body_text = soup.get_text(" ", strip=True)
    has_cta = bool(re.search(r"add\s+to\s+(cart|bag|basket)|buy\s+now", body_text, re.I))

    for pattern, label in _DEAD_PAGE_PATTERNS:
        if pattern.search(headline_text):
            return True, label
        if pattern.search(body_text) and not has_cta:
            return True, label

    return False, None


_TOKEN_RE = re.compile(r"[a-z0-9]+")

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "in", "on", "for", "with", "to",
    "by", "at", "as", "is", "it", "this", "that", "from", "into", "onto",
}


def _content_tokens(s: str) -> set:
    raw = _TOKEN_RE.findall((s or "").lower())
    return {t for t in raw if len(t) > 2 and t not in _STOPWORDS}


_CHALLENGE_PHRASES = (
    "just a moment",
    "checking your browser",
    "are you human",
    "verify you are human",
    "captcha",
    "access denied",
    "access has been denied",
    "request unsuccessful",
    "cloudflare",
    "your request was blocked",
    "robot or human",
    # Amazon Robot Check / automated-traffic interstitial
    "robot check",
    "type the characters",
    "enter the characters",
    "sorry, we just need to make sure",
    "discuss automated access",
    "automated access to amazon",
    "click the button below to continue",
    # Google / generic anti-bot interstitial
    "unusual traffic",
    "automated traffic",
    # PerimeterX / DataDome (Finish Line, Nike, etc.)
    "press and hold",
    "verify you are a human",
)

_MIN_IDENTIFIER_LEN = 10


def _looks_like_challenge_page(soup: BeautifulSoup) -> bool:
    body_text = soup.get_text(" ", strip=True)[:1500].lower()
    if any(p in body_text for p in _CHALLENGE_PHRASES):
        return True
    return _looks_like_amazon_soft_block(soup)


def _looks_like_amazon_soft_block(soup: BeautifulSoup) -> bool:
    """Amazon's "Click the button below to continue shopping" interstitial.

    The page returns title="Amazon.com" with no <h1> and a body that asks
    you to click through. The bare phrase "continue shopping" is too
    common (cart pages contain it) to add to _CHALLENGE_PHRASES directly,
    so we gate it on the title shape.
    """
    title = (soup.title.get_text(strip=True) if soup.title else "").lower()
    if title not in ("amazon.com", "amazon.ca", ""):
        return False
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return False
    body = soup.get_text(" ", strip=True)[:600].lower()
    return "continue shopping" in body or "click the button below" in body


def _jsonld_product_names(soup: BeautifulSoup) -> list:
    """Walk JSON-LD blocks and collect Product.name strings."""
    names: list = []

    def _walk(node):
        if isinstance(node, list):
            for n in node:
                _walk(n)
            return
        if not isinstance(node, dict):
            return
        type_val = node.get("@type")
        types = type_val if isinstance(type_val, list) else [type_val]
        if "Product" in types:
            n = node.get("name")
            if isinstance(n, str) and n.strip():
                names.append(n.strip())
        for v in node.values():
            if isinstance(v, (dict, list)):
                _walk(v)

    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        _walk(data)
    return names


def _prefix_tokens(s: str, n: int = 3) -> list:
    """First `n` significant tokens of `s` in original order."""
    raw = _TOKEN_RE.findall((s or "").lower())
    sig = [t for t in raw if len(t) > 2 and t not in _STOPWORDS]
    return sig[:n]


def check_identity(giftful_name: str, html: str) -> Tuple[bool, float]:
    """Returns (matches, score).

    Returns False only when we have substantial page content AND zero
    meaningful overlap with the Giftful product name. Empty pages, very
    short titles, and bot-challenge pages all return (True, 0.0) — those
    are "couldn't read" not "wrong product." Lets us flag genuinely-wrong
    products while not punishing the scraper for getting bot-blocked.
    """
    if not giftful_name or not html or not html.strip():
        return True, 0.0

    soup = BeautifulSoup(html, "lxml")

    if _looks_like_challenge_page(soup):
        return True, 0.0

    candidates = []
    if soup.title and soup.title.get_text(strip=True):
        candidates.append(soup.title.get_text(strip=True))
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        candidates.append(og["content"])
    og_desc = soup.find("meta", attrs={"property": "og:description"})
    if og_desc and og_desc.get("content"):
        candidates.append(og_desc["content"])
    desc = soup.find("meta", attrs={"name": "description"})
    if desc and desc.get("content"):
        candidates.append(desc["content"])
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        candidates.append(h1.get_text(strip=True))
    candidates.extend(_jsonld_product_names(soup))

    if not candidates:
        return True, 0.0

    if max(len(c) for c in candidates) < _MIN_IDENTIFIER_LEN:
        return True, 0.0

    name_toks = _content_tokens(giftful_name)
    if not name_toks:
        return True, 0.0

    best = 0.0
    for cand in candidates:
        cand_toks = _content_tokens(cand)
        if not cand_toks:
            continue
        overlap = len(name_toks & cand_toks)
        denom = min(len(name_toks), len(cand_toks))
        score = overlap / denom if denom else 0.0
        if score > best:
            best = score

    # Prefix-token match: brand+product-type at the start of the Giftful
    # name is highly identifying. Catches cases where the candidate page
    # has many extra unrelated tokens diluting the whole-set ratio.
    prefix = _prefix_tokens(giftful_name, n=3)
    prefix_score = 0.0
    if prefix:
        for cand in candidates:
            cand_toks = _content_tokens(cand)
            if not cand_toks:
                continue
            hits = sum(1 for t in prefix if t in cand_toks)
            score = hits / len(prefix)
            if score > prefix_score:
                prefix_score = score

    matches = best >= 0.5 or prefix_score >= 0.67
    return matches, max(best, prefix_score)


def identity_diagnostic_snippet(html: str, max_chars: int = 120) -> str:
    """Return a short snippet describing what `check_identity` saw on a page.

    Used in review_log diagnostics so a 0.00 mismatch is debuggable without
    re-fetching the page. Prefers <title>, then <h1>, then og:title.
    """
    if not html or not str(html).strip():
        return ""
    soup = BeautifulSoup(html, "lxml")
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(strip=True)[:max_chars]
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)[:max_chars]
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return og["content"][:max_chars]
    return ""


_SOLD_OUT_TEXT_RE = re.compile(r"\bsold\s+out\b", re.I)
_CTA_RE = re.compile(
    r"add\s+to\s+(cart|bag|basket)|buy\s+now|add\s+to\s+wishlist", re.I
)


def check_sold_out(html: str) -> bool:
    """Return True only when we have a strong signal the product is sold out.

    Strong signals:
      - Schema.org Offer.availability says OutOfStock / SoldOut / Discontinued
      - The page has no buy-CTA AND explicitly says "sold out"

    We deliberately ignore "sold out" text in size-variant selectors and
    related-products carousels, because matching it loosely (as a previous
    iteration did) flagged 80% of in-stock products as sold-out.
    """
    if not html or not html.strip():
        return False

    soup = BeautifulSoup(html, "lxml")

    schema_verdict = None  # None=unknown, True=oos, False=in_stock
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if _schema_says_sold_out(data):
            schema_verdict = True
            break
        if _schema_says_in_stock(data):
            schema_verdict = False
            # keep scanning in case a later schema overrides — but in_stock
            # is a strong signal so we can stop once we see it
            break

    if schema_verdict is True:
        return True
    if schema_verdict is False:
        return False

    # No schema signal — fall back to: "sold out" mentioned AND no buy CTA.
    body_text = soup.get_text(" ", strip=True)
    if _CTA_RE.search(body_text):
        return False
    return bool(_SOLD_OUT_TEXT_RE.search(body_text))


def _schema_says_sold_out(node) -> bool:
    if isinstance(node, list):
        return any(_schema_says_sold_out(n) for n in node)
    if not isinstance(node, dict):
        return False
    avail = node.get("availability")
    if isinstance(avail, str) and _avail_means_sold_out(avail):
        return True
    offers = node.get("offers")
    if offers is not None and _schema_says_sold_out(offers):
        return True
    for v in node.values():
        if isinstance(v, (dict, list)) and _schema_says_sold_out(v):
            return True
    return False


def _schema_says_in_stock(node) -> bool:
    if isinstance(node, list):
        return any(_schema_says_in_stock(n) for n in node)
    if not isinstance(node, dict):
        return False
    avail = node.get("availability")
    if isinstance(avail, str) and "instock" in avail.lower().replace("_", "").replace(" ", ""):
        return True
    offers = node.get("offers")
    if offers is not None and _schema_says_in_stock(offers):
        return True
    for v in node.values():
        if isinstance(v, (dict, list)) and _schema_says_in_stock(v):
            return True
    return False


def _avail_means_sold_out(avail: str) -> bool:
    a = avail.lower().replace("_", "").replace(" ", "")
    return any(flag in a for flag in ("outofstock", "soldout", "discontinued"))


def llm_validate_enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def llm_validate(giftful_name, listed_price, html):
    if not llm_validate_enabled():
        return None
    return None
