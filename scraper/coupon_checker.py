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

_TITLE_CLASS_RE = re.compile(
    r"(^|\s)(coupon-title|offer-title|deal-title|title)(\s|$)", re.I
)
_SENTENCE_END_RE = re.compile(r"[.!?](?=\s|$)")
_WHITESPACE_RE = re.compile(r"\s+")


def _clean_text(text: str, max_chars: int = 80) -> str:
    """Tidy a description string for display.

    Collapses whitespace, prefers the first sentence when one ends within
    `max_chars`, falls back to a word-boundary cut with an ellipsis. Trailing
    punctuation on a sentence cut is stripped so we don't render
    "20% off." with a dangling period when the next sentence is irrelevant.
    """
    if not text:
        return ""
    cleaned = _WHITESPACE_RE.sub(" ", text).strip()

    # If the first sentence ends inside the budget, prefer that — it's
    # almost always more readable than a multi-sentence run-on.
    first = _SENTENCE_END_RE.search(cleaned)
    if first and first.end() <= max_chars + 1:
        sentence = cleaned[: first.end()].rstrip(" .!?,;:")
        if sentence and (len(sentence) < len(cleaned) or len(cleaned) <= max_chars):
            return sentence

    if len(cleaned) <= max_chars:
        return cleaned

    # Word boundary at or before max_chars.
    window = cleaned[:max_chars]
    space = window.rfind(" ")
    if space > 0:
        return window[:space].rstrip(" ,;:") + "…"
    # No space — hard cut.
    return window.rstrip() + "…"


def _extract_card_title(card) -> str:
    """Pull a clean offer headline from a CouponFollow / RetailMeNot card.

    Prefers explicit title elements (`h3`, `.coupon-title`, `.offer-title`)
    over the verbose `.description` body, since aggregator descriptions are
    often mid-sentence excerpts.
    """
    for tag_name in ("h2", "h3", "h4"):
        el = card.find(tag_name)
        if el and el.get_text(strip=True):
            return el.get_text(" ", strip=True)
    title_el = card.find(class_=_TITLE_CLASS_RE)
    if title_el and title_el.get_text(strip=True):
        return title_el.get_text(" ", strip=True)
    return ""


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


_CODE_VALIDATE_RE = re.compile(r"^[A-Z][A-Z0-9_-]{2,29}$")
_ARIA_GETCODE_RE = re.compile(
    r"(?:get|reveal|show|copy|use|click)\s+(?:the\s+)?code[:\s]+([A-Z][A-Z0-9_-]{2,29})",
    re.I,
)
_JSON_CODE_RE = re.compile(
    r'"code"\s*:\s*"([A-Z][A-Z0-9_-]{2,29})"'
    r'(?:[^{}]*?"(?:title|name|description)"\s*:\s*"([^"]+)")?',
    re.I,
)


def _extract_card_code(card) -> str:
    """Pull the promo code from a CouponFollow / RetailMeNot offer card.

    Cards expose codes in many ways: `data-code` on the card, or
    `data-clipboard-text` on a descendant reveal button, or an
    `aria-label="Get Code XXX"`, or plain text inside a `.code` element.
    """
    for attr in ("data-code", "data-clipboard-text", "data-coupon-code"):
        v = (card.get(attr) or "").strip().upper()
        if _CODE_VALIDATE_RE.match(v):
            return v
    for attr in ("data-clipboard-text", "data-code", "data-coupon-code"):
        el = card.find(attrs={attr: True})
        if el:
            v = (el.get(attr) or "").strip().upper()
            if _CODE_VALIDATE_RE.match(v):
                return v
    for el in card.find_all(attrs={"aria-label": True}):
        m = _ARIA_GETCODE_RE.search(el.get("aria-label", ""))
        if m and _CODE_VALIDATE_RE.match(m.group(1).upper()):
            return m.group(1).upper()
    code_el = card.find(class_=re.compile(r"(^|\s)(code|coupon-code)(\s|$)", re.I))
    if code_el:
        text = code_el.get_text(strip=True).upper()
        if _CODE_VALIDATE_RE.match(text):
            return text
    return ""


def _extract_codes(cards, today: date) -> List[PromoCode]:
    results: List[PromoCode] = []
    for card in cards:
        code = _extract_card_code(card)
        if not code:
            continue

        title = _extract_card_title(card)
        if title:
            description = _clean_text(title, max_chars=80)
        else:
            desc_el = card.find(
                class_=re.compile(r"(^|\s)(description|coupon-description)(\s|$)", re.I)
            )
            raw_desc = desc_el.get_text(" ", strip=True) if desc_el else ""
            description = _clean_text(raw_desc, max_chars=80)

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


def _extract_json_codes(soup, today: date) -> List[PromoCode]:
    """Scan inline <script> blocks for `"code":"XXX"` patterns.

    CouponFollow and RetailMeNot ship the offer list in a JSON island; the
    static DOM around it sometimes only renders placeholders, so the codes
    live exclusively in script-tag JSON.
    """
    seen: dict[str, PromoCode] = {}
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        if not text or "code" not in text.lower():
            continue
        for m in _JSON_CODE_RE.finditer(text):
            code = m.group(1).upper()
            if code in seen:
                continue
            title = m.group(2) or ""
            description = _clean_text(title, max_chars=80)
            seen[code] = PromoCode(code=code, description=description, expiry=None)
    return list(seen.values())


def parse_couponfollow(html: str, today: Optional[date] = None) -> List[PromoCode]:
    today = today or date.today()
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select(
        "li.offer, .offer, .coupon, .deal, [data-code], [data-clipboard-text]"
    )
    found: dict[str, PromoCode] = {}
    for code in _extract_codes(cards, today):
        found.setdefault(code.code.upper(), code)
    if not found:
        for code in _extract_json_codes(soup, today):
            found.setdefault(code.code.upper(), code)
    return list(found.values())


def parse_dealspotr(html: str, today: Optional[date] = None) -> List[PromoCode]:
    today = today or date.today()
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select(".coupon, .offer, [data-code], [data-clipboard-text]")
    found: dict[str, PromoCode] = {}
    for code in _extract_codes(cards, today):
        found.setdefault(code.code.upper(), code)
    if not found:
        for code in _extract_json_codes(soup, today):
            found.setdefault(code.code.upper(), code)
    return list(found.values())


def parse_retailmenot(html: str, today: Optional[date] = None) -> List[PromoCode]:
    """Parse RetailMeNot's offer page (https://www.retailmenot.com/view/{slug}).

    RetailMeNot uses similar offer-card markup with `data-code` or
    `data-clipboard-text` attributes; offers also appear in inline JSON.
    """
    today = today or date.today()
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select(
        ".offer, .offer-row, .coupon, [data-code], [data-clipboard-text]"
    )
    found: dict[str, PromoCode] = {}
    for code in _extract_codes(cards, today):
        found.setdefault(code.code.upper(), code)
    if not found:
        for code in _extract_json_codes(soup, today):
            found.setdefault(code.code.upper(), code)
    return list(found.values())


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
    # Trigger phrase is case-insensitive ("Use Code", "use code", "USE CODE"
    # all appear in the wild). The code itself stays uppercase-anchored so we
    # don't pick up arbitrary words.
    r"(?i:"
    r"use\s+code"
    r"|with\s+code"
    r"|promo\s+code"
    r"|coupon\s+code"
    r"|enter\s+code"
    r"|code:"
    r"|off\s+using"
    r"|%\s+off\s+with"
    r")\s*[-:]?\s*([A-Z][A-Z0-9]{3,14})\b"
)
_ONSITE_CODE_DENYLIST = {
    "CODE", "PROMO", "COUPON", "SAVE", "OFFER", "DEAL", "GIFT",
    "FREE", "SHIP", "ENTER", "CHECKOUT", "DISCOUNT",
}

# Trailing prepositional phrases that read awkwardly once the code is stripped.
_ORPHAN_TAIL_RE = re.compile(
    r"\s*\b(?:in\s+cart|at\s+checkout|on\s+(?:your\s+)?order|in\s+checkout)\b\.?$",
    re.I,
)

# Phrases that appear next to actual offers — used to score candidate windows
# when the same code appears multiple times on a page (e.g. once in a footer
# account block and once in the real promo banner).
_OFFER_SIGNAL_RE = re.compile(
    r"\$\s*\d|"            # "$500", "$ 200"
    r"\d+%|"               # "20%"
    r"\b(?:free|off|save|saving|discount|gift|bonus|sale|"
    r"complimentary|reward|promo)\b",
    re.I,
)

# Once we walk up past banner-sized containers we hit page wrappers / body,
# whose text is the whole page. Cap candidate containers below that.
_MAX_CONTAINER_CHARS = 1500


def _smallest_matching_ancestor(text_node):
    """Return (element, container_text) for the smallest ancestor whose
    rendered text contains at least one complete trigger match. Walks up
    because the trigger phrase is often split across nested tags
    (e.g. ``Use Code <span>CODE</span>``)."""
    el = getattr(text_node, "parent", None)
    while el is not None and getattr(el, "name", None) not in (None, "[document]"):
        txt = el.get_text(" ", strip=True)
        if txt and _ONSITE_CODE_RE.search(txt):
            return el, txt
        el = el.parent
    return None, None


def extract_onsite_codes(html: str) -> List[PromoCode]:
    """Extract promo codes from a retailer product page.

    Walks the DOM looking for trigger phrases ("use code: XXXX", "with code
    XXXX", etc.) inside text nodes. Anchoring to the smallest containing
    element bounds each candidate snippet to a banner / paragraph / span —
    so footer and nav chrome stay out of the rendered description.

    When the same code appears in multiple containers (common on retailer
    pages — banner + footer "use code" link), the candidate with the
    strongest offer signals nearby wins.
    """
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()

    # candidates[code] = list of (container_text, match-in-container)
    candidates: dict[str, list[tuple[str, "re.Match[str]"]]] = {}
    seen_elements: set[int] = set()
    for text_node in soup.find_all(string=True):
        if not str(text_node).strip():
            continue
        element, container_text = _smallest_matching_ancestor(text_node)
        if element is None or container_text is None:
            continue
        if id(element) in seen_elements:
            continue
        seen_elements.add(id(element))
        # Cap container text — once we walk up to <body>/<html>, the candidate
        # is "the whole page," which always wins on offer-signal score because
        # it sweeps in every promo word on the page. Anything larger than a
        # banner-sized block is treated as too noisy to render directly.
        if len(container_text) > _MAX_CONTAINER_CHARS:
            continue
        for match in _ONSITE_CODE_RE.finditer(container_text):
            code = match.group(1).upper()
            if code in _ONSITE_CODE_DENYLIST:
                continue
            if not re.search(r"\d", code) and len(code) < 5:
                continue
            candidates.setdefault(code, []).append((container_text, match))

    results: list[PromoCode] = []
    seen_codes: set[str] = set()
    for code, occurrences in candidates.items():
        if code in seen_codes:
            continue
        seen_codes.add(code)

        # Sort: higher offer-signal count first, smaller container second.
        # Smaller containers are tighter — body-level wrappers always lose
        # to banner-sized blocks even when both score the same.
        occurrences_sorted = sorted(
            occurrences,
            key=lambda om: (-_score_container(om[0], om[1]), len(om[0])),
        )
        best_text, best_match = occurrences_sorted[0]
        best_score = _score_container(best_text, best_match)

        if best_score == 0:
            # No offer signal in any container — likely just a chrome link.
            # Emit the code so an aggregator description can still be used,
            # but suppress the meaningless container text.
            results.append(PromoCode(code=code, description="", expiry=None))
        else:
            snippet = _build_onsite_snippet(best_text, best_match)
            results.append(PromoCode(code=code, description=snippet, expiry=None))
    return results


def _score_container(container_text: str, match: "re.Match[str]") -> int:
    """Count offer signals in the container, excluding the trigger phrase
    itself so "20% off with code" doesn't double-count its own 'off'."""
    cleaned = container_text.replace(match.group(0), " ")
    return len(_OFFER_SIGNAL_RE.findall(cleaned))


def _build_onsite_snippet(text: str, match: "re.Match[str]") -> str:
    """Return a clean offer-headline snippet for an onsite code match.

    Strips the trigger phrase + code from the container text, splits into
    sentences, and returns the sentence with the strongest offer signals.
    The first sentence in a banner block is often a side-note ("Expedited
    delivery available in checkout") — the actual offer ("Free 1/4 Carat
    Lab Diamond Studs With Purchase Over $500") lives further along.
    """
    cleaned = text.replace(match.group(0), " ")
    cleaned = _ORPHAN_TAIL_RE.sub("", cleaned).strip(" .,;:—-")

    if not cleaned:
        return ""

    # Split on sentence-ending punctuation. Keep punctuation as a separator
    # cue but drop empty fragments.
    sentences = [
        s.strip(" .,;:—-")
        for s in re.split(r"[.!?](?=\s|$)", cleaned)
        if s.strip()
    ]
    if not sentences:
        return _clean_text(cleaned, max_chars=80)

    def _sig(s: str) -> int:
        return len(_OFFER_SIGNAL_RE.findall(s))

    # Pick the highest-scoring sentence. On ties, the earlier sentence wins
    # (more likely to be the headline rather than fine-print).
    best_idx = max(range(len(sentences)), key=lambda i: (_sig(sentences[i]), -i))
    best_sentence = sentences[best_idx]
    if _sig(best_sentence) == 0:
        # No sentence had an offer signal — fall back to the first sentence
        # (matches the simple single-sentence banner case).
        best_sentence = sentences[0]

    return _clean_text(best_sentence, max_chars=80)


def lookup(
    domain: str,
    session,
    error_log,
    today: Optional[date] = None,
    onsite_html: Optional[str] = None,
) -> List[PromoCode]:
    """Look up promo codes for a domain.

    Order: (1) extract from the retailer's own HTML if provided,
    (2) CouponFollow, (3) DealsPotr when CouponFollow turns up nothing,
    (4) RetailMeNot when both CouponFollow AND DealsPotr are empty.
    De-dupes across sources by code (case-insensitive).
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
        ds_codes: List[PromoCode] = []
        if ds_html:
            ds_codes = parse_dealspotr(ds_html, today=today)
            for code in ds_codes:
                found.setdefault(code.code.upper(), code)

        if not ds_codes:
            rmn_url = f"https://www.retailmenot.com/view/{slug}"
            rmn_html = _fetch(rmn_url, session, error_log)
            if rmn_html:
                for code in parse_retailmenot(rmn_html, today=today):
                    found.setdefault(code.code.upper(), code)

    return list(found.values())
