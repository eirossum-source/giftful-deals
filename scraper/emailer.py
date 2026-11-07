from __future__ import annotations

import html as html_mod
import os
from datetime import date
from typing import Dict, List, Optional

import resend

from filter import Deal, DealType, _effective_reference_price
from finds import CATEGORIES


PAGE_URL = "https://eirossum-source.github.io/giftful-deals"
ACTIONS_URL = "https://github.com/eirossum-source/giftful-deals/actions"
SENDER = "onboarding@resend.dev"
ACCENT = "#0f7a4a"
PER_CATEGORY = 4
TOTAL = 16
OTHER = "Other"


def build_subject(deals: List[Deal], today: date, finds_ledger: Optional[dict] = None) -> str:
    n = len(deals) + len(_eligible_finds(finds_ledger, today))
    if n == 0:
        return f"No deals found this week ({today.isoformat()})"
    noun = "item" if n == 1 else "items"
    return f"\U0001F381 Isaac's Deals — {n} {noun} on sale ({today.isoformat()})"


def _fmt_price(p: float) -> str:
    return f"${p:,.2f}"


def _price_parts_html(current_price, reference_price: float) -> str:
    if current_price is not None and current_price < reference_price:
        return (
            f'<span style="color:#888;text-decoration:line-through">'
            f"{_fmt_price(reference_price)}</span> "
            f'<strong style="color:{ACCENT}">{_fmt_price(current_price)}</strong>'
        )
    if current_price is not None:
        return f'<strong style="color:{ACCENT}">{_fmt_price(current_price)}</strong>'
    return f'<span style="color:#888">Listed {_fmt_price(reference_price)}</span>'


def _badges_html(deal_types) -> str:
    badges = []
    if DealType.PROMO in deal_types:
        badges.append(
            f'<span style="background:{ACCENT};color:#fff;font-size:11px;'
            'padding:2px 8px;border-radius:999px;margin-left:6px">PROMO</span>'
        )
    if DealType.BACK_IN_STOCK in deal_types:
        badges.append(
            '<span style="background:#2d4a66;color:#fff;font-size:11px;'
            'padding:2px 8px;border-radius:999px;margin-left:6px">BACK IN STOCK</span>'
        )
    return "".join(badges)


def _promos_html(promos) -> str:
    parts = []
    for promo in promos:
        code = html_mod.escape(promo.code)
        desc = html_mod.escape(promo.description or "")
        parts.append(
            f'<div style="margin-top:8px;font-family:ui-monospace,Menlo,monospace;'
            f"font-size:13px;color:{ACCENT};background:#f3faf6;"
            f'border:1px dashed {ACCENT};padding:6px 10px;border-radius:8px">'
            f'<strong>{code}</strong> <span style="color:#555">{desc}</span></div>'
        )
    return "".join(parts)


def _eligible_finds(ledger, today: Optional[date]) -> List[dict]:
    """Finds from a ledger that was checked today and are confirmed on sale."""
    if today is None or not isinstance(ledger, dict):
        return []
    if ledger.get("checked_at") != today.isoformat():
        return []
    items = ledger.get("items")
    if not isinstance(items, dict):
        return []
    out = []
    for entry in items.values():
        if not isinstance(entry, dict) or entry.get("on_sale") is not True:
            continue
        if not all(isinstance(entry.get(k), str) and entry.get(k) for k in ("url", "name", "image_url")):
            continue
        if entry.get("category") not in CATEGORIES:
            continue
        cur, lst = entry.get("current_price"), entry.get("list_price")
        try:
            if not (0 < cur < lst):
                continue
        except TypeError:
            continue
        out.append(entry)
    return out


def _deal_card(deal: Deal) -> dict:
    item = deal.item
    winner = deal.winner
    if winner is not None:
        pr = winner.price_result
        reference = _effective_reference_price(winner.store.listed_price, pr)
        store = winner.store.display_name
        url = winner.store.url
        promos, types = winner.promos, winner.deal_types
        alts = []
        for ev in deal.store_evaluations:
            if ev is winner:
                continue
            p = ev.price_result
            price = p.current_price if p.current_price is not None else ev.store.listed_price
            alts.append((ev.store.display_name, ev.store.url, price))
    else:
        pr = deal.price_result
        reference = _effective_reference_price(item.listed_price, pr)
        store = item.domain
        url = item.url
        promos, types, alts = deal.promos, deal.deal_types, []
    return {
        "your_list": True,
        "store": store,
        "name": item.name,
        "url": url,
        "image_url": item.image_url or "",
        "current": pr.current_price,
        "reference": reference,
        "promos": promos,
        "types": types,
        "alts": alts,
        "discount": 0.0,
    }


def _find_card(entry: dict) -> dict:
    cur, lst = entry["current_price"], entry["list_price"]
    return {
        "your_list": False,
        "store": entry.get("store") or "",
        "name": entry["name"],
        "url": entry["url"],
        "image_url": entry["image_url"],
        "current": cur,
        "reference": lst,
        "promos": [],
        "types": [],
        "alts": [],
        "discount": 1 - cur / lst,
    }


def select_grid(deals: List[Deal], finds_ledger: Optional[dict], today: Optional[date]) -> List[dict]:
    """Group list deals and fresh finds by category and apply the caps.

    Returns [{"category", "cards", "more"}] in display order.
    """
    pools: Dict[str, List[dict]] = {c: [] for c in CATEGORIES}
    pools[OTHER] = []
    for d in deals:
        cat = d.item.category if d.item.category in CATEGORIES else OTHER
        pools[cat].append(_deal_card(d))
    found: Dict[str, List[dict]] = {c: [] for c in CATEGORIES}
    for entry in _eligible_finds(finds_ledger, today):
        found[entry["category"]].append(_find_card(entry))
    for cat, cards in found.items():
        cards.sort(key=lambda c: -c["discount"])
        pools[cat].extend(cards)

    order = list(CATEGORIES) + [OTHER]
    shown: Dict[str, List[dict]] = {c: [] for c in order}
    total = 0
    progressed = True
    while total < TOTAL and progressed:
        progressed = False
        for cat in order:
            if total >= TOTAL:
                break
            if len(shown[cat]) < PER_CATEGORY and len(shown[cat]) < len(pools[cat]):
                shown[cat].append(pools[cat][len(shown[cat])])
                total += 1
                progressed = True
    return [
        {"category": c, "cards": shown[c], "more": len(pools[c]) - len(shown[c])}
        for c in order
        if shown[c]
    ]


def _card_html(card: dict) -> str:
    name = html_mod.escape(card["name"])
    url = html_mod.escape(card["url"])
    store = html_mod.escape(card["store"])
    cur, ref = card["current"], card["reference"]

    if card["image_url"]:
        photo = (
            f'<a href="{url}"><img src="{html_mod.escape(card["image_url"])}" width="260" '
            f'alt="{name}" style="width:100%;max-width:260px;height:auto;display:block;'
            'border-radius:8px 8px 0 0"></a>'
        )
    else:
        photo = (
            '<div style="width:100%;height:180px;background:#e7ebe9;'
            'border-radius:8px 8px 0 0"></div>'
        )

    tag = ""
    if card["your_list"]:
        tag = (
            '<div style="margin-bottom:4px"><span style="background:#1a1d1b;color:#fff;'
            'font-size:10px;font-weight:700;letter-spacing:.04em;padding:2px 8px;'
            'border-radius:999px">YOUR LIST</span></div>'
        )

    pct = ""
    if cur is not None and cur < ref:
        pct = (
            f' <span style="color:{ACCENT};font-size:12px;font-weight:600">'
            f"{round((1 - cur / ref) * 100)}% off</span>"
        )
    price = f"{_price_parts_html(cur, ref)}{pct}{_badges_html(card['types'])}"

    alts = "".join(
        f'<div style="margin-top:4px;font-size:12px;color:#888">Also at '
        f'<a href="{html_mod.escape(a_url)}" style="color:{ACCENT};text-decoration:none">'
        f"{html_mod.escape(a_name)}</a> {_fmt_price(a_price)}</div>"
        for a_name, a_url, a_price in card["alts"]
    )

    return (
        '<table data-card="1" cellpadding="0" cellspacing="0" width="100%" '
        'style="background:#fff;border:1px solid #e7ebe9;border-radius:10px">'
        f"<tr><td>{photo}</td></tr>"
        '<tr><td style="padding:10px 12px 12px">'
        f"{tag}"
        f'<div style="font-size:11px;color:#888;text-transform:uppercase">{store}</div>'
        f'<a href="{url}" style="text-decoration:none;color:#1a1d1b">'
        f'<div style="font-size:14px;font-weight:600;margin-top:2px">{name}</div></a>'
        f'<div style="margin-top:6px;font-size:14px">{price}</div>'
        f"{_promos_html(card['promos'])}{alts}"
        "</td></tr></table>"
    )


def _section_html(section: dict) -> str:
    cards = section["cards"]
    rows = ""
    for i in range(0, len(cards), 2):
        pair = cards[i:i + 2]
        cells = "".join(
            f'<td width="50%" valign="top" style="padding:0 6px 12px">{_card_html(c)}</td>'
            for c in pair
        )
        if len(pair) == 1:
            cells += '<td width="50%" style="padding:0 6px 12px">&nbsp;</td>'
        rows += f"<tr>{cells}</tr>"
    more = ""
    if section["more"]:
        more = (
            '<div style="padding:0 6px 12px;font-size:13px">'
            f'<a href="{PAGE_URL}" style="color:{ACCENT};font-weight:600;text-decoration:none">'
            f"+{section['more']} more on the deals page &rarr;</a></div>"
        )
    return (
        f'<div style="font-size:18px;font-weight:700;margin:20px 6px 8px">'
        f"{html_mod.escape(section['category'])}</div>"
        '<table cellpadding="0" cellspacing="0" width="100%">'
        f"{rows}</table>{more}"
    )


def _collect_domains(deals: List[Deal]) -> set:
    domains: set = set()
    for d in deals:
        if d.store_evaluations:
            for ev in d.store_evaluations:
                if ev.store.domain:
                    domains.add(ev.store.domain)
        elif d.item.domain:
            domains.add(d.item.domain)
    return domains


def _summary_counts(deals, finds_ledger, today):
    found = _eligible_finds(finds_ledger, today)
    stores = _collect_domains(deals)
    for e in found:
        s = (e.get("store") or "").strip()
        if s:
            stores.add(s)
    return len(deals) + len(found), len(stores)


def build_html(deals: List[Deal], finds_ledger: Optional[dict] = None,
               today: Optional[date] = None) -> str:
    n, n_stores = _summary_counts(deals, finds_ledger, today)
    if n == 0:
        summary = (
            '<p style="font-size:16px;color:#444">No deals this week. '
            "Nothing on the wishlist is discounted or has an active promo code right now.</p>"
        )
        cards = ""
    else:
        noun_deal = "deal" if n == 1 else "deals"
        noun_store = "store" if n_stores == 1 else "stores"
        summary = (
            f'<p style="font-size:16px;color:#444">'
            f"<strong>{n} {noun_deal}</strong> found across "
            f"<strong>{n_stores} {noun_store}</strong>.</p>"
        )
        cards = "".join(_section_html(s) for s in select_grid(deals, finds_ledger, today))

    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "</head><body "
        'style="margin:0;padding:12px;background:#f5f7f6;'
        'font-family:-apple-system,BlinkMacSystemFont,system-ui,Segoe UI,Roboto,sans-serif;'
        'color:#1a1d1b;line-height:1.55">'
        '<table cellpadding="0" cellspacing="0" width="100%" '
        'style="max-width:600px;margin:0 auto;background:#fff;border-radius:16px;'
        'padding:28px 14px;box-shadow:0 1px 2px rgba(0,0,0,.04)">'
        "<tr><td>"
        f'<h1 style="font-size:24px;margin:0 0 8px">\U0001F381 Isaac\'s Deals</h1>'
        f"{summary}"
        '<p style="margin:24px 0">'
        f'<a href="{PAGE_URL}" '
        f'style="display:inline-block;background:{ACCENT};color:#fff;'
        'padding:12px 24px;border-radius:10px;font-weight:600;text-decoration:none">'
        "View Full Deals Page</a></p>"
        f"{cards}"
        '<hr style="border:0;border-top:1px solid #e7ebe9;margin:28px 0 16px"/>'
        '<p style="font-size:13px;color:#888">Trigger a manual run any time: '
        f'<a href="{ACTIONS_URL}" style="color:{ACCENT}">GitHub Actions</a></p>'
        "</td></tr></table></body></html>"
    )


def _text_price_str(current_price, reference_price: float) -> str:
    if current_price is not None and current_price < reference_price:
        return f"{_fmt_price(reference_price)} -> {_fmt_price(current_price)}"
    if current_price is not None:
        return _fmt_price(current_price)
    return f"Listed {_fmt_price(reference_price)} (current unavailable)"


def _text_card(card: dict, lines: List[str]) -> None:
    marker = "[Your list] " if card["your_list"] else ""
    lines.append(f"- {marker}{card['name']} ({card['store']})")
    lines.append(f"  {_text_price_str(card['current'], card['reference'])}")
    for promo in card["promos"]:
        lines.append(f"  Code: {promo.code} — {promo.description}")
    lines.append(f"  {card['url']}")
    for a_name, a_url, a_price in card["alts"]:
        lines.append(f"  Also at: {a_name} — {_fmt_price(a_price)}")
        lines.append(f"    {a_url}")
    lines.append("")


def build_text(deals: List[Deal], finds_ledger: Optional[dict] = None,
               today: Optional[date] = None) -> str:
    lines: List[str] = ["Isaac's Deals", ""]
    n, n_stores = _summary_counts(deals, finds_ledger, today)
    if n == 0:
        lines.append("No deals this week.")
        lines.append("")
    else:
        lines.append(f"{n} deals found across {n_stores} stores.")
        lines.append("")
        for section in select_grid(deals, finds_ledger, today):
            lines.append(f"== {section['category']} ==")
            for card in section["cards"]:
                _text_card(card, lines)
            if section["more"]:
                lines.append(f"  +{section['more']} more on the deals page: {PAGE_URL}")
                lines.append("")
    lines.append(f"Full page: {PAGE_URL}")
    lines.append(f"Manual run: {ACTIONS_URL}")
    return "\n".join(lines)


def send(deals: List[Deal], today: date, finds: Optional[dict] = None):
    api_key = os.environ.get("RESEND_API_KEY")
    to_email = os.environ.get("TO_EMAIL")
    if not api_key:
        raise RuntimeError("RESEND_API_KEY is not set")
    if not to_email:
        raise RuntimeError("TO_EMAIL is not set")

    resend.api_key = api_key
    payload = {
        "from": SENDER,
        "to": [to_email],
        "subject": build_subject(deals, today, finds),
        "html": build_html(deals, finds, today),
        "text": build_text(deals, finds, today),
    }
    return resend.Emails.send(payload)
