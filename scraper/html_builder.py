from __future__ import annotations

import html
from datetime import datetime
from typing import List
from urllib.parse import quote

from filter import Deal, DealType


ACCENT = "#0f7a4a"
PLACEHOLDER_SVG = (
    "data:image/svg+xml;utf8,"
    + quote(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160">'
        '<rect width="160" height="160" rx="14" fill="#f1f3f2"/>'
        '<path d="M40 70h80v56a6 6 0 0 1-6 6H46a6 6 0 0 1-6-6z" fill="#cfd6d2"/>'
        '<path d="M36 54h88v18H36z" fill="#0f7a4a"/>'
        '<path d="M76 54h8v78h-8z" fill="#cfd6d2"/>'
        "</svg>"
    )
)


def _fmt_price(p: float) -> str:
    return f"${p:,.2f}"


def _pct_drop(listed: float, current: float) -> int:
    if listed <= 0:
        return 0
    return int(round((listed - current) / listed * 100))


def _deal_type_values(deal: Deal) -> str:
    return " ".join(t.value for t in deal.deal_types)


def _card_html(deal: Deal) -> str:
    item = deal.item
    price = deal.price_result
    img = html.escape(item.image_url) if item.image_url else PLACEHOLDER_SVG

    badges = []
    if (
        DealType.PRICE_DROP in deal.deal_types
        and price.current_price is not None
        and price.current_price < item.listed_price
    ):
        pct = _pct_drop(item.listed_price, price.current_price)
        badges.append(f'<span class="badge badge-drop">-{pct}%</span>')
    if DealType.SALE in deal.deal_types:
        badges.append('<span class="badge badge-sale">SALE</span>')
    if DealType.PROMO in deal.deal_types:
        badges.append('<span class="badge badge-promo">PROMO</span>')

    price_block_parts = []
    if price.current_price is not None and price.current_price < item.listed_price:
        price_block_parts.append(
            f'<span class="price-listed">{_fmt_price(item.listed_price)}</span>'
            f'<span class="price-current">{_fmt_price(price.current_price)}</span>'
        )
    elif price.current_price is not None:
        price_block_parts.append(
            f'<span class="price-current">{_fmt_price(price.current_price)}</span>'
        )
    else:
        price_block_parts.append(
            f'<span class="price-listed">{_fmt_price(item.listed_price)}</span>'
            '<span class="price-unavailable">Current price unavailable</span>'
        )

    promo_chips = []
    for promo in deal.promos:
        code = html.escape(promo.code)
        desc = html.escape(promo.description or "")
        promo_chips.append(
            f'<button type="button" class="promo-chip" '
            f'data-code="{code}" aria-label="Copy code {code}">'
            f'<span class="promo-code">{code}</span>'
            f'<span class="promo-desc">{desc}</span>'
            f'<span class="promo-copied" aria-hidden="true">Copied!</span>'
            f"</button>"
        )

    tags = " ".join(
        f'<span class="tag tag-{t.value}">{t.value.replace("_", " ")}</span>'
        for t in deal.deal_types
    )

    return (
        f'<article class="deal-card" '
        f'data-types="{_deal_type_values(deal)}" '
        f'data-store="{html.escape(item.domain)}">'
        f'<a href="{html.escape(item.url)}" target="_blank" rel="noopener noreferrer">'
        f'<div class="thumb"><img src="{img}" alt="{html.escape(item.name)}" loading="lazy"/>'
        f'<div class="badges">{"".join(badges)}</div>'
        f"</div>"
        f'<h3 class="deal-name">{html.escape(item.name)}</h3>'
        f"</a>"
        f'<div class="price-block">{"".join(price_block_parts)}</div>'
        f'<div class="promos">{"".join(promo_chips)}</div>'
        f'<div class="tags">{tags}</div>'
        f'<div class="store">{html.escape(item.domain)}</div>'
        f"</article>"
    )


def _filter_bar(deals: List[Deal]) -> str:
    stores = sorted({d.item.domain for d in deals})
    type_buttons = [
        ('<button type="button" class="chip chip-active" data-filter-type="all">All</button>'),
        '<button type="button" class="chip" data-filter-type="price_drop">Price Drop</button>',
        '<button type="button" class="chip" data-filter-type="sale">Sale</button>',
        '<button type="button" class="chip" data-filter-type="promo">Promo Code</button>',
    ]
    store_buttons = [
        '<button type="button" class="chip chip-active" data-filter-store="all">All stores</button>'
    ]
    for store in stores:
        store_buttons.append(
            f'<button type="button" class="chip" data-filter-store="{html.escape(store)}">'
            f"{html.escape(store)}</button>"
        )

    return (
        '<section class="filter-bar" aria-label="Filters">'
        f'<div class="filter-row"><span class="filter-label">Type</span>{"".join(type_buttons)}</div>'
        f'<div class="filter-row"><span class="filter-label">Store</span>{"".join(store_buttons)}</div>'
        "</section>"
    )


def _empty_state(generated_at: datetime) -> str:
    ts = html.escape(generated_at.strftime("%Y-%m-%d %H:%M UTC"))
    return (
        f'<section class="empty-state">'
        f'<div class="empty-icon" aria-hidden="true">\U0001F381</div>'
        f"<h2>No deals this week</h2>"
        f'<p class="empty-ts">Last checked {ts}</p>'
        f"</section>"
    )


_CSS = (
    ":root{--accent:"
    + ACCENT
    + """;--ink:#1a1d1b;--muted:#5f6b66;--line:#e7ebe9;--bg:#ffffff;--chip:#f1f3f2;}
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,Roboto,Helvetica,Arial,sans-serif;margin:0;background:var(--bg);color:var(--ink);line-height:1.55;-webkit-font-smoothing:antialiased;}
header.site{padding:48px 24px 24px;max-width:1200px;margin:0 auto}
header.site h1{font-size:clamp(28px,4vw,44px);letter-spacing:-.02em;margin:0 0 6px}
header.site p{color:var(--muted);margin:0}
main{max-width:1200px;margin:0 auto;padding:0 24px 64px}
.filter-bar{display:flex;flex-direction:column;gap:12px;padding:20px 0 28px;border-bottom:1px solid var(--line);margin-bottom:28px}
.filter-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.filter-label{font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-right:4px}
.chip{border:1px solid var(--line);background:var(--chip);color:var(--ink);padding:8px 14px;border-radius:999px;font:inherit;font-size:14px;cursor:pointer;transition:all .15s}
.chip:hover{border-color:var(--accent)}
.chip.chip-active{background:var(--accent);color:#fff;border-color:var(--accent)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:20px}
.deal-card{background:#fff;border-radius:14px;box-shadow:0 1px 2px rgba(20,30,25,.04),0 8px 24px rgba(20,30,25,.06);overflow:hidden;display:flex;flex-direction:column;transition:transform .15s,box-shadow .15s}
.deal-card:hover{transform:translateY(-2px);box-shadow:0 2px 4px rgba(20,30,25,.06),0 16px 36px rgba(20,30,25,.09)}
.deal-card a{color:inherit;text-decoration:none;display:block}
.deal-card .thumb{position:relative;aspect-ratio:4/3;background:#f6f8f7;overflow:hidden}
.deal-card .thumb img{width:100%;height:100%;object-fit:cover;display:block}
.deal-card .badges{position:absolute;top:12px;left:12px;display:flex;gap:6px;flex-wrap:wrap}
.badge{font-size:11px;font-weight:700;letter-spacing:.04em;padding:5px 10px;border-radius:999px;color:#fff;background:var(--ink)}
.badge-drop{background:var(--accent)}
.badge-sale{background:#c73c3c}
.badge-promo{background:#2d4a66}
.deal-name{font-size:16px;margin:14px 16px 6px;line-height:1.35}
.price-block{padding:0 16px;display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.price-listed{color:var(--muted);text-decoration:line-through;font-size:14px}
.price-current{font-size:20px;font-weight:700;color:var(--accent)}
.price-unavailable{color:var(--muted);font-size:13px}
.promos{padding:12px 16px 0;display:flex;flex-wrap:wrap;gap:8px}
.promo-chip{position:relative;font:inherit;cursor:pointer;border:1px dashed var(--accent);background:#f3faf6;color:var(--accent);padding:8px 12px;border-radius:10px;display:flex;flex-direction:column;align-items:flex-start;gap:2px}
.promo-chip .promo-code{font-weight:700;letter-spacing:.04em;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.promo-chip .promo-desc{font-size:12px;color:var(--muted)}
.promo-chip .promo-copied{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:var(--accent);color:#fff;border-radius:9px;opacity:0;transition:opacity .15s}
.promo-chip.copied .promo-copied{opacity:1}
.tags{padding:12px 16px;display:flex;flex-wrap:wrap;gap:6px}
.tag{font-size:11px;color:var(--muted);background:var(--chip);padding:3px 8px;border-radius:6px;text-transform:capitalize}
.store{padding:0 16px 16px;color:var(--muted);font-size:12px}
.empty-state{text-align:center;padding:96px 24px}
.empty-state .empty-icon{font-size:56px;margin-bottom:12px}
.empty-state h2{font-size:24px;margin:0 0 6px}
.empty-state .empty-ts{color:var(--muted)}
footer.site{max-width:1200px;margin:0 auto;padding:24px;color:var(--muted);font-size:13px;border-top:1px solid var(--line)}
@media (max-width:540px){header.site{padding:32px 20px 16px}main{padding:0 20px 48px}}
"""
)


_JS = """
(() => {
  const cards = Array.from(document.querySelectorAll('.deal-card'));
  const state = { type: 'all', store: 'all' };
  function apply() {
    for (const card of cards) {
      const types = (card.dataset.types || '').split(' ');
      const store = card.dataset.store || '';
      const typeOk = state.type === 'all' || types.includes(state.type);
      const storeOk = state.store === 'all' || store === state.store;
      card.style.display = (typeOk && storeOk) ? '' : 'none';
    }
  }
  function setActive(group, btn) {
    group.querySelectorAll('.chip').forEach(c => c.classList.remove('chip-active'));
    btn.classList.add('chip-active');
  }
  document.querySelectorAll('[data-filter-type]').forEach(btn => {
    btn.addEventListener('click', () => {
      state.type = btn.dataset.filterType;
      setActive(btn.parentElement, btn);
      apply();
    });
  });
  document.querySelectorAll('[data-filter-store]').forEach(btn => {
    btn.addEventListener('click', () => {
      state.store = btn.dataset.filterStore;
      setActive(btn.parentElement, btn);
      apply();
    });
  });
  document.querySelectorAll('.promo-chip').forEach(chip => {
    chip.addEventListener('click', async (e) => {
      e.preventDefault();
      const code = chip.dataset.code;
      try { await navigator.clipboard.writeText(code); }
      catch (_) {
        const tmp = document.createElement('textarea');
        tmp.value = code; document.body.appendChild(tmp); tmp.select();
        try { document.execCommand('copy'); } catch (_) {}
        tmp.remove();
      }
      chip.classList.add('copied');
      setTimeout(() => chip.classList.remove('copied'), 1200);
    });
  });
})();
"""


def render(deals: List[Deal], generated_at: datetime) -> str:
    timestamp = generated_at.strftime("%Y-%m-%d %H:%M UTC")

    if not deals:
        body = _empty_state(generated_at)
    else:
        cards_html = "".join(_card_html(d) for d in deals)
        body = (
            _filter_bar(deals)
            + f'<section class="grid">{cards_html}</section>'
        )

    return (
        "<!doctype html>"
        '<html lang="en">'
        "<head>"
        '<meta charset="utf-8"/>'
        '<meta name="viewport" content="width=device-width,initial-scale=1"/>'
        f"<title>Isaac's Deals — {html.escape(timestamp)}</title>"
        f"<style>{_CSS}</style>"
        "</head>"
        "<body>"
        '<header class="site">'
        "<h1>Isaac's Deals</h1>"
        f'<p>Last updated {html.escape(timestamp)}</p>'
        "</header>"
        f"<main>{body}</main>"
        '<footer class="site">'
        "Automatically updated every Monday. "
        '<a href="https://github.com/eirossum-source/giftful-deals/actions" '
        'style="color:var(--accent)">Run manually</a>.'
        "</footer>"
        f"<script>{_JS}</script>"
        "</body></html>"
    )
