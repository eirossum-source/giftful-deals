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


def lookup(
    domain: str,
    session,
    error_log,
    today: Optional[date] = None,
) -> List[PromoCode]:
    today = today or date.today()
    cf_url = f"https://couponfollow.com/site/{domain}"
    html = _fetch(cf_url, session, error_log)
    if not html:
        return []
    return parse_couponfollow(html, today=today)
