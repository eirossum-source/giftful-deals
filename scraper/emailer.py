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


def _card_html(deal: Deal) -> str:
    item = deal.item
    price = deal.price_result
    price_parts = []
    if price.current_price is not None and price.current_price < item.listed_price:
        price_parts.append(
            f'<span style="color:#888;text-decoration:line-through">'
            f"{_fmt_price(item.listed_price)}</span> "
            f'<strong style="color:{ACCENT}">{_fmt_price(price.current_price)}</strong>'
        )
    elif price.current_price is not None:
        price_parts.append(
            f'<strong style="color:{ACCENT}">{_fmt_price(price.current_price)}</strong>'
        )
    else:
        price_parts.append(
            f'<span style="color:#888">Listed {_fmt_price(item.listed_price)}</span>'
        )

    badges = []
    if DealType.SALE in deal.deal_types:
        badges.append(
            '<span style="background:#c73c3c;color:#fff;font-size:11px;'
            'padding:2px 8px;border-radius:999px;margin-left:6px">SALE</span>'
        )
    if DealType.PROMO in deal.deal_types:
        badges.append(
            f'<span style="background:{ACCENT};color:#fff;font-size:11px;'
            'padding:2px 8px;border-radius:999px;margin-left:6px">PROMO</span>'
        )

    promo_lines = ""
    for promo in deal.promos:
        code = html_mod.escape(promo.code)
        desc = html_mod.escape(promo.description or "")
        promo_lines += (
            f'<div style="margin-top:8px;font-family:ui-monospace,Menlo,monospace;'
            f"font-size:13px;color:{ACCENT};background:#f3faf6;"
            f'border:1px dashed {ACCENT};padding:6px 10px;border-radius:8px">'
            f'<strong>{code}</strong> <span style="color:#555">{desc}</span></div>'
        )

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
        f'<div style="margin-top:8px;font-size:15px">{"".join(price_parts)}{"".join(badges)}</div>'
        f"{promo_lines}"
        f'<div style="margin-top:12px">'
        f'<a href="{url}" '
        f'style="color:{ACCENT};font-weight:600;text-decoration:none">View at {store} &rarr;</a>'
        "</div>"
        "</td></tr></table></td></tr>"
    )


def build_html(deals: List[Deal]) -> str:
    stores = {d.item.domain for d in deals}
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


def build_text(deals: List[Deal]) -> str:
    lines: List[str] = ["Isaac's Deals", ""]
    if not deals:
        lines.append("No deals this week.")
        lines.append("")
    else:
        stores = {d.item.domain for d in deals}
        lines.append(f"{len(deals)} deals found across {len(stores)} stores.")
        lines.append("")
        for d in deals:
            item = d.item
            price = d.price_result
            if price.current_price is not None and price.current_price < item.listed_price:
                price_str = (
                    f"{_fmt_price(item.listed_price)} -> {_fmt_price(price.current_price)}"
                )
            elif price.current_price is not None:
                price_str = _fmt_price(price.current_price)
            else:
                price_str = f"Listed {_fmt_price(item.listed_price)} (current unavailable)"
            lines.append(f"- {item.name} ({item.domain})")
            lines.append(f"  {price_str}")
            for promo in d.promos:
                lines.append(f"  Code: {promo.code} — {promo.description}")
            lines.append(f"  {item.url}")
            lines.append("")
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
