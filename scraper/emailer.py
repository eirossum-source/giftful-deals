from __future__ import annotations

import html as html_mod
import os
from datetime import date
from typing import List

import resend

from filter import Deal, DealType


PAGE_URL = "https://eirossum-source.github.io/giftful-deals"
ACTIONS_URL = "https://github.com/eirossum-source/giftful-deals/actions"
SENDER = "onboarding@resend.dev"
ACCENT = "#0f7a4a"


def build_subject(deals: List[Deal], today: date) -> str:
    if not deals:
        return f"No deals found this week ({today.isoformat()})"
    n = len(deals)
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


def _multi_card_html(deal: Deal) -> str:
    item = deal.item
    winner = deal.winner
    name = html_mod.escape(item.name)
    winner_url = html_mod.escape(winner.store.url)
    winner_name = html_mod.escape(winner.store.display_name)

    price_html = _price_parts_html(
        winner.price_result.current_price, winner.store.listed_price
    )
    badges = _badges_html(winner.deal_types)
    promos = _promos_html(winner.promos)

    alt_lines = []
    for ev in deal.store_evaluations:
        if ev is winner:
            continue
        p = ev.price_result
        price_text = (
            _fmt_price(p.current_price)
            if p.current_price is not None
            else _fmt_price(ev.store.listed_price)
        )
        alt_lines.append(
            f'<div style="margin-top:4px;font-size:13px">'
            f'<a href="{html_mod.escape(ev.store.url)}" '
            f'style="color:{ACCENT};text-decoration:none">'
            f"{html_mod.escape(ev.store.display_name)}</a>"
            f' <span style="color:#888">{price_text}</span></div>'
        )

    secondary = ""
    if alt_lines:
        secondary = (
            f'<div style="border-top:1px solid #e7ebe9;margin-top:12px;padding-top:10px">'
            f'<div style="font-size:11px;color:#888;margin-bottom:4px">Also available at:</div>'
            f'{"".join(alt_lines)}</div>'
        )

    return (
        '<tr><td style="padding:0 0 16px">'
        f'<table cellpadding="0" cellspacing="0" width="100%" '
        f'style="background:#fff;border:1px solid #e7ebe9;border-radius:12px">'
        '<tr><td style="padding:16px">'
        f'<div style="font-size:12px;color:#888;font-weight:600;text-transform:uppercase">'
        f"{winner_name}</div>"
        f'<a href="{winner_url}" style="text-decoration:none;color:#1a1d1b">'
        f'<div style="font-size:17px;font-weight:600;margin-top:4px">{name}</div>'
        "</a>"
        f'<div style="margin-top:8px;font-size:15px">{price_html}{badges}</div>'
        f"{promos}"
        f"{secondary}"
        f'<div style="margin-top:12px">'
        f'<a href="{winner_url}" '
        f'style="color:{ACCENT};font-weight:600;text-decoration:none">'
        f"View at {winner_name} &rarr;</a>"
        "</div>"
        "</td></tr></table></td></tr>"
    )


def _card_html(deal: Deal) -> str:
    if deal.store_evaluations:
        return _multi_card_html(deal)

    item = deal.item
    price = deal.price_result
    price_html = _price_parts_html(price.current_price, item.listed_price)
    badges = _badges_html(deal.deal_types)
    promos = _promos_html(deal.promos)

    name = html_mod.escape(item.name)
    url = html_mod.escape(item.url)
    store = html_mod.escape(item.domain)

    return (
        '<tr><td style="padding:0 0 16px">'
        f'<table cellpadding="0" cellspacing="0" width="100%" '
        f'style="background:#fff;border:1px solid #e7ebe9;border-radius:12px">'
        '<tr><td style="padding:16px">'
        f'<div style="font-size:12px;color:#888">{store}</div>'
        f'<a href="{url}" style="text-decoration:none;color:#1a1d1b">'
        f'<div style="font-size:17px;font-weight:600;margin-top:4px">{name}</div>'
        "</a>"
        f'<div style="margin-top:8px;font-size:15px">{price_html}{badges}</div>'
        f"{promos}"
        f'<div style="margin-top:12px">'
        f'<a href="{url}" '
        f'style="color:{ACCENT};font-weight:600;text-decoration:none">View at {store} &rarr;</a>'
        "</div>"
        "</td></tr></table></td></tr>"
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


def build_html(deals: List[Deal]) -> str:
    stores = _collect_domains(deals)
    n = len(deals)
    if n == 0:
        summary = (
            '<p style="font-size:16px;color:#444">No deals this week. '
            "Nothing on the wishlist is discounted or has an active promo code right now.</p>"
        )
        cards = ""
    else:
        noun_deal = "deal" if n == 1 else "deals"
        noun_store = "store" if len(stores) == 1 else "stores"
        summary = (
            f'<p style="font-size:16px;color:#444">'
            f"<strong>{n} {noun_deal}</strong> found across "
            f"<strong>{len(stores)} {noun_store}</strong>.</p>"
        )
        cards = (
            '<table cellpadding="0" cellspacing="0" width="100%" '
            'style="max-width:560px;margin:0 auto">'
            + "".join(_card_html(d) for d in deals)
            + "</table>"
        )

    return (
        "<!doctype html><html><body "
        'style="margin:0;padding:24px;background:#f5f7f6;'
        'font-family:-apple-system,BlinkMacSystemFont,system-ui,Segoe UI,Roboto,sans-serif;'
        'color:#1a1d1b;line-height:1.55">'
        '<table cellpadding="0" cellspacing="0" width="100%" '
        'style="max-width:600px;margin:0 auto;background:#fff;border-radius:16px;'
        'padding:32px 24px;box-shadow:0 1px 2px rgba(0,0,0,.04)">'
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


def _text_multi_deal(d: Deal, lines: List[str]) -> None:
    winner = d.winner
    lines.append(f"- {d.item.name} ({winner.store.display_name})")
    lines.append(f"  {_text_price_str(winner.price_result.current_price, winner.store.listed_price)}")
    for promo in winner.promos:
        lines.append(f"  Code: {promo.code} — {promo.description}")
    lines.append(f"  {winner.store.url}")
    for ev in d.store_evaluations:
        if ev is winner:
            continue
        p = ev.price_result
        price_text = (
            _fmt_price(p.current_price)
            if p.current_price is not None
            else _fmt_price(ev.store.listed_price)
        )
        lines.append(f"  Also at: {ev.store.display_name} — {price_text}")
        lines.append(f"    {ev.store.url}")
    lines.append("")


def _text_legacy_deal(d: Deal, lines: List[str]) -> None:
    item = d.item
    price = d.price_result
    lines.append(f"- {item.name} ({item.domain})")
    lines.append(f"  {_text_price_str(price.current_price, item.listed_price)}")
    for promo in d.promos:
        lines.append(f"  Code: {promo.code} — {promo.description}")
    lines.append(f"  {item.url}")
    lines.append("")


def build_text(deals: List[Deal]) -> str:
    lines: List[str] = ["Isaac's Deals", ""]
    if not deals:
        lines.append("No deals this week.")
        lines.append("")
    else:
        stores = _collect_domains(deals)
        lines.append(f"{len(deals)} deals found across {len(stores)} stores.")
        lines.append("")
        for d in deals:
            if d.store_evaluations:
                _text_multi_deal(d, lines)
            else:
                _text_legacy_deal(d, lines)
    lines.append(f"Full page: {PAGE_URL}")
    lines.append(f"Manual run: {ACTIONS_URL}")
    return "\n".join(lines)


def send(deals: List[Deal], today: date):
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
        "subject": build_subject(deals, today),
        "html": build_html(deals),
        "text": build_text(deals),
    }
    return resend.Emails.send(payload)
