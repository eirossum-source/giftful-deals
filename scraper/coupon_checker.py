from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from price_checker import USER_AGENTS


@dataclass
class PromoCode:
    code: str
    description: str
    expiry: Optional[date]


EXPIRY_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


def _parse_expiry(text: str) -> Optional[date]:
    if not text:
        return None
    match = EXPIRY_RE.search(text)
    if match:
        try:
            return dateparser.parse(match.group(1)).date()
        except (ValueError, TypeError):
            return None
    try:
        return dateparser.parse(text, fuzzy=True).date()
    except (ValueError, TypeError, OverflowError):
        return None


def _is_expired(expiry: Optional[date], today: date) -> bool:
    if expiry is None:
        return False
    return expiry < today


def _extract_codes(cards, today: date) -> List[PromoCode]:
    results: List[PromoCode] = []
    for card in cards:
        code_attr = card.get("data-code")
        code_el = card.find(class_=re.compile(r"(^|\s)(code|coupon-code)(\s|$)", re.I))
        code = code_attr or (code_el.get_text(strip=True) if code_el else "")
        if not code:
            continue

        desc_el = card.find(
            class_=re.compile(r"(^|\s)(description|coupon-description)(\s|$)", re.I)
        )
        description = desc_el.get_text(strip=True) if desc_el else ""

        expiry_attr = card.get("data-expires")
        expiry_el = card.find(
            class_=re.compile(r"(^|\s)(expiry|coupon-expiry)(\s|$)", re.I)
        )
        expiry_text = expiry_attr or (
            expiry_el.get_text(strip=True) if expiry_el else ""
        )
        expiry = _parse_expiry(expiry_text)

        if _is_expired(expiry, today):
            continue

        results.append(PromoCode(code=code, description=description, expiry=expiry))
    return results


def parse_couponfollow(html: str, today: Optional[date] = None) -> List[PromoCode]:
    today = today or date.today()
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("li.offer, .offer, [data-code]")
    return _extract_codes(cards, today)


def parse_dealspotr(html: str, today: Optional[date] = None) -> List[PromoCode]:
    today = today or date.today()
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select(".coupon, [data-code]")
    return _extract_codes(cards, today)


def _fetch(url: str, session, error_log) -> Optional[str]:
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    time.sleep(random.uniform(1.0, 3.0))
    try:
        resp = session.get(url, headers=headers, timeout=20)
    except Exception as exc:
        error_log.error(f"coupon fetch failed for {url}: {exc}")
        return None
    if resp.status_code in (403, 429):
        error_log.error(
            f"coupon source blocked: {url} (status {resp.status_code})"
        )
        return None
    if resp.status_code >= 400:
        error_log.error(f"coupon fetch {resp.status_code} for {url}")
        return None
    return resp.text or ""


def _normalize_domain(domain: str) -> str:
    return re.sub(r"^www\.", "", (domain or "").strip().lower())


_ONSITE_CODE_RE = re.compile(
    r"(?:"
    r"[Uu]se\s+code|"
    r"[Ww]ith\s+code|"
    r"[Pp]romo\s+code|"
    r"[Cc]oupon\s+code|"
    r"[Ee]nter\s+code|"
    r"[Cc]ode:|"
    r"off\s+using|"
    r"%\s+off\s+with"
    r")\s*[-:]?\s*([A-Z][A-Z0-9]{3,14})\b"
)
_ONSITE_CODE_DENYLIST = {
    "CODE", "PROMO", "COUPON", "SAVE", "OFFER", "DEAL", "GIFT",
    "FREE", "SHIP", "ENTER", "CHECKOUT", "DISCOUNT",
}


def extract_onsite_codes(html: str) -> List[PromoCode]:
    """Extract promo codes from a retailer product page.

    Looks for trigger phrases ("use code: XXXX", "with code XXXX", etc.) in the
    visible page text. Codes shown to actual buyers are the highest-signal source —
    no extra HTTP request, retailer-confirmed valid.
    """
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)

    seen: dict[str, PromoCode] = {}
    for match in _ONSITE_CODE_RE.finditer(text):
        raw = match.group(1)
        code = raw.upper()
        if code in _ONSITE_CODE_DENYLIST:
            continue
        if not re.search(r"\d", code) and len(code) < 5:
            # Pure-letter codes shorter than 5 chars are usually false positives.
            continue
        if code in seen:
            continue
        # Pull a description from the surrounding sentence.
        start = max(0, match.start() - 60)
        end = min(len(text), match.end() + 80)
        snippet = text[start:end].strip()
        seen[code] = PromoCode(code=code, description=snippet, expiry=None)
    return list(seen.values())


def lookup(
    domain: str,
    session,
    error_log,
    today: Optional[date] = None,
    onsite_html: Optional[str] = None,
) -> List[PromoCode]:
    """Look up promo codes for a domain.

    Order: (1) extract from the retailer's own HTML if provided, (2) CouponFollow,
    (3) DealsPotr fallback when CouponFollow turns up nothing. De-dupes across
    sources by code (case-insensitive).
    """
    today = today or date.today()
    slug = _normalize_domain(domain)

    found: dict[str, PromoCode] = {}

    if onsite_html:
        for code in extract_onsite_codes(onsite_html):
            found.setdefault(code.code.upper(), code)

    cf_url = f"https://couponfollow.com/site/{slug}"
    cf_html = _fetch(cf_url, session, error_log)
    cf_codes: List[PromoCode] = []
    if cf_html:
        cf_codes = parse_couponfollow(cf_html, today=today)
        for code in cf_codes:
            found.setdefault(code.code.upper(), code)

    if not cf_codes:
        ds_url = f"https://dealspotr.com/promo-codes/{slug}"
        ds_html = _fetch(ds_url, session, error_log)
        if ds_html:
            for code in parse_dealspotr(ds_html, today=today):
                found.setdefault(code.code.upper(), code)

    return list(found.values())
