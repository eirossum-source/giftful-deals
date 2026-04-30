from __future__ import annotations

import html
from datetime import datetime
from typing import Iterable, List
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

from filter import Deal, DealType
from giftful import GIFTFUL_URL


_ET = ZoneInfo("America/New_York")

PLACEHOLDER_SVG = (
    "data:image/svg+xml;utf8,"
    + quote(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160">'
        '<rect width="160" height="160" rx="14" fill="#1a1c1e"/>'
        '<path d="M40 70h80v56a6 6 0 0 1-6 6H46a6 6 0 0 1-6-6z" fill="#2a2d30"/>'
        '<path d="M36 54h88v18H36z" fill="#3a3d40"/>'
        '<path d="M76 54h8v78h-8z" fill="#2a2d30"/>'
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


def _to_et_string(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(_ET).strftime("%Y-%m-%d %I:%M %p ET")


def _promo_chips_html(promos) -> str:
    parts = []
    for promo in promos:
        code = html.escape(promo.code)
        desc = html.escape(promo.description or "")
        parts.append(
            f'<button type="button" class="promo-chip" '
            f'data-code="{code}" aria-label="Copy code {code}">'
            f'<span class="promo-code">{code}</span>'
            f'<span class="promo-desc">{desc}</span>'
            f'<span class="promo-copied" aria-hidden="true">Copied!</span>'
            f"</button>"
        )
    return "".join(parts)


def _price_block_html(current_price, reference_price) -> str:
    if current_price is not None and current_price < reference_price:
        return (
            f'<span class="price-listed">{_fmt_price(reference_price)}</span>'
            f'<span class="price-current">{_fmt_price(current_price)}</span>'
        )
    if current_price is not None:
        return f'<span class="price-current">{_fmt_price(current_price)}</span>'
    return f'<span class="price-current">{_fmt_price(reference_price)}</span>'


def _effective_reference(baseline: float, price_result) -> float:
    """Higher of the Giftful baseline and the retailer's strikethrough."""
    retailer_list = getattr(price_result, "list_price", None) or 0.0
    return max(baseline, retailer_list)


def _badges_for_winner(winner) -> str:
    badges = []
    if DealType.PRICE_DROP in winner.deal_types and winner.price_result.current_price is not None:
        ref = _effective_reference(winner.store.listed_price, winner.price_result)
        pct = _pct_drop(ref, winner.price_result.current_price)
        badges.append(f'<span class="badge badge-drop">-{pct}%</span>')
    if DealType.PROMO in winner.deal_types:
        badges.append('<span class="badge badge-promo">PROMO</span>')
    if DealType.BACK_IN_STOCK in winner.deal_types:
        badges.append('<span class="badge badge-stock">BACK IN STOCK</span>')
    return "".join(badges)


def _badges_for_legacy(deal: Deal, item) -> str:
    price = deal.price_result
    badges = []
    if (
        DealType.PRICE_DROP in deal.deal_types
        and price is not None
        and price.current_price is not None
    ):
        ref = _effective_reference(item.listed_price, price)
        if price.current_price < ref:
            pct = _pct_drop(ref, price.current_price)
            badges.append(f'<span class="badge badge-drop">-{pct}%</span>')
    if DealType.PROMO in deal.deal_types:
        badges.append('<span class="badge badge-promo">PROMO</span>')
    if DealType.BACK_IN_STOCK in deal.deal_types:
        badges.append('<span class="badge badge-stock">BACK IN STOCK</span>')
    return "".join(badges)


def _multi_card_html(deal: Deal) -> str:
    item = deal.item
    winner = deal.winner
    img = html.escape(item.image_url) if item.image_url else PLACEHOLDER_SVG

    all_domains = " ".join(ev.store.domain for ev in deal.store_evaluations)
    all_types = " ".join({t.value for ev in deal.store_evaluations for t in ev.deal_types})

    badges = _badges_for_winner(winner)

    alt_items = []
    for ev in deal.store_evaluations:
        if ev is winner:
            continue
        p = ev.price_result
        price_text = (
            _fmt_price(p.current_price)
            if p.current_price is not None
            else _fmt_price(ev.store.listed_price)
        )
        alt_items.append(
            f'<li class="store-alt">'
            f'<a href="{html.escape(ev.store.url)}" target="_blank" rel="noopener noreferrer">'
            f"{html.escape(ev.store.display_name)}</a>"
            f'<span class="store-alt-price">{price_text}</span>'
            f"</li>"
        )

    secondary_html = (
        f'<ul class="stores-secondary">{"".join(alt_items)}</ul>' if alt_items else ""
    )

    winner_ref = _effective_reference(winner.store.listed_price, winner.price_result)

    return (
        f'<article class="deal-card" '
        f'data-types="{html.escape(all_types)}" '
        f'data-store="{html.escape(all_domains)}">'
        f'<a href="{html.escape(winner.store.url)}" target="_blank" rel="noopener noreferrer">'
        f'<div class="thumb"><img src="{img}" alt="{html.escape(item.name)}" loading="lazy"/>'
        f'<div class="badges">{badges}</div>'
        f"</div>"
        f'<h3 class="deal-name">{html.escape(item.name)}</h3>'
        f"</a>"
        f'<div class="store-winner">'
        f'<div class="winner-name">{html.escape(winner.store.display_name)}</div>'
        f'<div class="price-block">'
        f'{_price_block_html(winner.price_result.current_price, winner_ref)}'
        f"</div>"
        f'<div class="promos">{_promo_chips_html(winner.promos)}</div>'
        f"</div>"
        f"{secondary_html}"
        f"</article>"
    )


def _card_html(deal: Deal) -> str:
    if deal.store_evaluations:
        return _multi_card_html(deal)

    item = deal.item
    price = deal.price_result
    img = html.escape(item.image_url) if item.image_url else PLACEHOLDER_SVG
    badges = _badges_for_legacy(deal, item)
    tags = " ".join(
        f'<span class="tag tag-{t.value}">{t.value.replace("_", " ")}</span>'
        for t in deal.deal_types
    )

    legacy_ref = _effective_reference(item.listed_price, price)

    return (
        f'<article class="deal-card" '
        f'data-types="{_deal_type_values(deal)}" '
        f'data-store="{html.escape(item.domain)}">'
        f'<a href="{html.escape(item.url)}" target="_blank" rel="noopener noreferrer">'
        f'<div class="thumb"><img src="{img}" alt="{html.escape(item.name)}" loading="lazy"/>'
        f'<div class="badges">{badges}</div>'
        f"</div>"
        f'<h3 class="deal-name">{html.escape(item.name)}</h3>'
        f"</a>"
        f'<div class="price-block">'
        f'{_price_block_html(price.current_price, legacy_ref)}'
        f"</div>"
        f'<div class="promos">{_promo_chips_html(deal.promos)}</div>'
        f'<div class="tags">{tags}</div>'
        f'<div class="store">{html.escape(item.domain)}</div>'
        f"</article>"
    )


def _has_promo(deal: Deal) -> bool:
    if deal.store_evaluations:
        return any(DealType.PROMO in ev.deal_types for ev in deal.store_evaluations)
    return DealType.PROMO in deal.deal_types


def _has_back_in_stock(deal: Deal) -> bool:
    if deal.store_evaluations:
        return any(DealType.BACK_IN_STOCK in ev.deal_types for ev in deal.store_evaluations)
    return DealType.BACK_IN_STOCK in deal.deal_types


def _domains_of(deal: Deal) -> Iterable[str]:
    if deal.store_evaluations:
        for ev in deal.store_evaluations:
            if ev.store.domain:
                yield ev.store.domain
    elif deal.item.domain:
        yield deal.item.domain


def _filter_bar(deals: List[Deal]) -> str:
    domains: set = set()
    has_promo = False
    has_back_in_stock = False
    for d in deals:
        for dom in _domains_of(d):
            domains.add(dom)
        if _has_promo(d):
            has_promo = True
        if _has_back_in_stock(d):
            has_back_in_stock = True

    type_options = ['<option value="all">All types</option>',
                    '<option value="price_drop">Price Drop</option>']
    if has_promo:
        type_options.append('<option value="promo">Promo Code</option>')
    if has_back_in_stock:
        type_options.append('<option value="back_in_stock">Back in stock</option>')

    store_options = ['<option value="all">All stores</option>']
    for store in sorted(domains):
        esc = html.escape(store)
        store_options.append(f'<option value="{esc}">{esc}</option>')

    return (
        '<section class="filter-bar" aria-label="Filters">'
        '<label class="filter-field">'
        '<span class="filter-label">Type</span>'
        f'<select class="filter-select" data-filter-type>{"".join(type_options)}</select>'
        '</label>'
        '<label class="filter-field">'
        '<span class="filter-label">Store</span>'
        f'<select class="filter-select" data-filter-store>{"".join(store_options)}</select>'
        '</label>'
        "</section>"
    )


def _category_section(category_name: str, deals: List[Deal]) -> str:
    if not deals:
        return ""
    name = html.escape(category_name) if category_name else "Other"
    cards_html = "".join(_card_html(d) for d in deals)
    return (
        f'<section class="category-group" data-category="{html.escape(category_name)}">'
        f'<h2 class="category-heading">{name}</h2>'
        f'<div class="grid">{cards_html}</div>'
        '</section>'
    )


def _grouped_deals_html(deals: List[Deal]) -> str:
    order: List[str] = []
    grouped: dict = {}
    for d in deals:
        cat = d.item.category or "Other"
        if cat not in grouped:
            grouped[cat] = []
            order.append(cat)
        grouped[cat].append(d)
    return "".join(_category_section(cat, grouped[cat]) for cat in order)


def _empty_state(timestamp_et: str) -> str:
    return (
        f'<section class="empty-state">'
        f'<div class="empty-icon" aria-hidden="true">\U0001F381</div>'
        f"<h2>No deals this week</h2>"
        f'<p class="empty-ts">Last checked {html.escape(timestamp_et)}</p>'
        f"</section>"
    )


def _review_section_html(review_items) -> str:
    if not review_items:
        return ""
    rows = []
    for entry in review_items:
        item = entry["item"]
        reasons = entry.get("reasons") or []
        reasons_html = "; ".join(html.escape(r) for r in reasons)
        link_target = (
            getattr(item, "category_url", "") or item.url or GIFTFUL_URL
        )
        origin = urlparse(item.url).netloc if item.url else ""
        origin_html = (
            f'<span class="review-origin">{html.escape(origin)}</span>'
            if origin
            else ""
        )
        rows.append(
            f'<li class="review-row">'
            f'<a href="{html.escape(link_target)}" target="_blank" rel="noopener noreferrer">'
            f'{html.escape(item.name)}</a>'
            f'<span class="review-meta">'
            f'{origin_html}'
            f'<span class="review-reason">{reasons_html}</span>'
            f'</span>'
            f"</li>"
        )
    return (
        '<section class="review-section" aria-label="Review manually">'
        '<h2 class="review-heading">Review manually</h2>'
        '<p class="review-note">Click an item name to open it in your Giftful list — '
        'easiest place to edit or remove it.</p>'
        f'<ul class="review-list">{"".join(rows)}</ul>'
        "</section>"
    )


_CSS = """
:root{
  --bg:#0e0f10;
  --panel:#16181a;
  --line:#26282b;
  --ink:#f5f6f7;
  --muted:#9aa0a6;
  --accent:#3aa86b;
  --accent-soft:#1f2e26;
  --brand:#52A352;
  --drop:#3aa86b;
  --promo:#5b8def;
  --stock:#e0a23a;
}
*{box-sizing:border-box}
html,body{background:var(--bg)}
body{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,Roboto,Helvetica,Arial,sans-serif;
  margin:0;color:var(--ink);line-height:1.55;-webkit-font-smoothing:antialiased;
}
header.site{
  max-width:1200px;margin:0 auto;padding:40px 24px 20px;
  display:flex;flex-direction:column;align-items:center;gap:12px;text-align:center;
}
.brand{
  display:inline-flex;flex-direction:column;align-items:center;gap:8px;
  text-decoration:none;color:var(--brand);
}
.brand-mark{
  display:block;
  width:clamp(180px,28vw,280px);height:auto;
}
.brand-tagline{
  font-family:Quicksand,-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
  font-size:11px;font-weight:700;
  color:var(--muted);
  text-transform:uppercase;letter-spacing:.28em;
}
header.site .meta{
  color:var(--muted);font-size:12px;
  display:flex;justify-content:center;gap:16px;flex-wrap:wrap;align-items:center;
}
header.site .meta a{color:var(--accent);text-decoration:none}
header.site .meta a:hover{text-decoration:underline}
main{max-width:1200px;margin:0 auto;padding:0 24px 64px}
.filter-bar{
  display:flex;flex-wrap:wrap;gap:12px;
  padding:18px 0 24px;border-bottom:1px solid var(--line);margin-bottom:28px;
}
.filter-field{display:flex;flex-direction:column;gap:6px;flex:1;min-width:180px}
.filter-label{font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}
.filter-select{
  appearance:none;-webkit-appearance:none;
  background:var(--panel);color:var(--ink);
  border:1px solid var(--line);border-radius:10px;
  padding:10px 36px 10px 14px;font:inherit;font-size:14px;cursor:pointer;
  background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'><path fill='%239aa0a6' d='M6 8L2 4h8z'/></svg>");
  background-repeat:no-repeat;background-position:right 12px center;background-size:12px;
}
.filter-select:focus{outline:none;border-color:var(--accent)}
.category-group{margin-bottom:36px}
.category-heading{
  font-size:13px;font-weight:600;color:var(--muted);
  text-transform:uppercase;letter-spacing:.12em;margin:0 0 14px;
}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px}
.deal-card{
  background:var(--panel);border:1px solid var(--line);border-radius:14px;
  overflow:hidden;display:flex;flex-direction:column;
  transition:transform .15s,border-color .15s;
}
.deal-card:hover{transform:translateY(-2px);border-color:#3a3d40}
.deal-card a{color:inherit;text-decoration:none;display:block}
.deal-card .thumb{position:relative;aspect-ratio:1/1;background:#1a1c1e;overflow:hidden}
.deal-card .thumb img{width:100%;height:100%;object-fit:cover;display:block}
.deal-card .badges{position:absolute;top:10px;left:10px;display:flex;gap:6px;flex-wrap:wrap}
.badge{
  font-size:10px;font-weight:700;letter-spacing:.06em;
  padding:4px 9px;border-radius:999px;color:#0e0f10;background:#fff;
  text-transform:uppercase;
}
.badge-drop{background:var(--drop);color:#fff}
.badge-promo{background:var(--promo);color:#fff}
.badge-stock{background:var(--stock);color:#0e0f10}
.deal-name{font-size:14px;margin:12px 14px 6px;line-height:1.3;color:var(--ink);font-weight:500}
.price-block{padding:0 14px;display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.price-listed{color:var(--muted);text-decoration:line-through;font-size:13px}
.price-current{font-size:18px;font-weight:700;color:var(--ink)}
.promos{padding:10px 14px 0;display:flex;flex-wrap:wrap;gap:8px}
.promo-chip{
  position:relative;font:inherit;cursor:pointer;
  border:1px dashed var(--accent);background:var(--accent-soft);color:var(--accent);
  padding:7px 11px;border-radius:10px;display:flex;flex-direction:column;align-items:flex-start;gap:2px;
}
.promo-chip .promo-code{font-weight:700;letter-spacing:.04em;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px}
.promo-chip .promo-desc{font-size:11px;color:var(--muted)}
.promo-chip .promo-copied{
  position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  background:var(--accent);color:#fff;border-radius:9px;opacity:0;transition:opacity .15s;
}
.promo-chip.copied .promo-copied{opacity:1}
.tags{padding:10px 14px;display:flex;flex-wrap:wrap;gap:6px}
.tag{font-size:10px;color:var(--muted);background:#1a1c1e;padding:3px 8px;border-radius:6px;text-transform:capitalize}
.store{padding:0 14px 14px;color:var(--muted);font-size:11px}
.store-winner{padding:8px 14px 4px}
.winner-name{font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px}
.stores-secondary{list-style:none;margin:0;padding:0 14px 12px;display:flex;flex-direction:column;gap:4px}
.store-alt{display:flex;align-items:baseline;justify-content:space-between;font-size:12px}
.store-alt a{color:var(--accent);text-decoration:none}
.store-alt a:hover{text-decoration:underline}
.store-alt-price{color:var(--muted);font-size:11px}
.empty-state{text-align:center;padding:96px 24px;color:var(--muted)}
.empty-state .empty-icon{font-size:56px;margin-bottom:12px}
.empty-state h2{font-size:20px;margin:0 0 6px;color:var(--ink)}
.review-section{
  margin:48px 0 16px;padding:24px;
  background:var(--panel);border:1px solid var(--line);border-radius:14px;
}
.review-heading{
  font-size:13px;font-weight:600;color:var(--muted);
  text-transform:uppercase;letter-spacing:.12em;margin:0 0 6px;
}
.review-note{margin:0 0 14px;color:var(--muted);font-size:13px}
.review-list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}
.review-row{display:flex;flex-direction:column;gap:2px;padding:10px 0;border-top:1px solid var(--line)}
.review-row:first-child{border-top:none;padding-top:0}
.review-row a{color:var(--ink);text-decoration:none;font-size:14px}
.review-row a:hover{text-decoration:underline;color:var(--accent)}
.review-meta{display:flex;gap:10px;flex-wrap:wrap;align-items:baseline;font-size:12px;color:var(--muted)}
.review-origin{color:var(--muted);font-size:11px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.review-origin::after{content:"·";margin-left:10px;color:var(--line)}
.review-reason{color:var(--muted);font-size:12px}
footer.site{
  max-width:1200px;margin:0 auto;padding:24px;
  color:var(--muted);font-size:12px;border-top:1px solid var(--line);
}
@media (max-width:540px){
  header.site{padding:28px 18px 14px;gap:10px}
  .brand-mark{width:170px}
  .brand-tagline{font-size:10px;letter-spacing:.24em}
  main{padding:0 18px 48px}
  .grid{grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
}
"""


_JS = """
(() => {
  const cards = Array.from(document.querySelectorAll('.deal-card'));
  const groups = Array.from(document.querySelectorAll('.category-group'));
  const state = { type: 'all', store: 'all' };
  function apply() {
    for (const card of cards) {
      const types = (card.dataset.types || '').split(' ');
      const store = card.dataset.store || '';
      const typeOk = state.type === 'all' || types.includes(state.type);
      const storeOk = state.store === 'all' || store.split(' ').includes(state.store);
      card.style.display = (typeOk && storeOk) ? '' : 'none';
    }
    for (const g of groups) {
      const visible = g.querySelectorAll('.deal-card:not([style*="none"])').length;
      g.style.display = visible === 0 ? 'none' : '';
    }
  }
  const typeSel = document.querySelector('[data-filter-type]');
  if (typeSel) typeSel.addEventListener('change', () => { state.type = typeSel.value; apply(); });
  const storeSel = document.querySelector('[data-filter-store]');
  if (storeSel) storeSel.addEventListener('change', () => { state.store = storeSel.value; apply(); });
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


def render(deals: List[Deal], generated_at: datetime, review_items=None) -> str:
    timestamp_et = _to_et_string(generated_at)

    review_html = _review_section_html(review_items or [])

    if not deals:
        body = _empty_state(timestamp_et) + review_html
    else:
        body = _filter_bar(deals) + _grouped_deals_html(deals) + review_html

    return (
        "<!doctype html>"
        '<html lang="en">'
        "<head>"
        '<meta charset="utf-8"/>'
        '<meta name="viewport" content="width=device-width,initial-scale=1"/>'
        '<meta name="color-scheme" content="dark"/>'
        f"<title>giftful deals — {html.escape(timestamp_et)}</title>"
        '<link rel="icon" type="image/png" href="giftful_logo.png"/>'
        '<link rel="preconnect" href="https://fonts.googleapis.com"/>'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>'
        '<link href="https://fonts.googleapis.com/css2?family=Quicksand:wght@600;700&display=swap" rel="stylesheet"/>'
        f"<style>{_CSS}</style>"
        "</head>"
        "<body>"
        '<header class="site">'
        f'<a href="{html.escape(GIFTFUL_URL)}" class="brand" target="_blank" rel="noopener noreferrer" aria-label="Open Giftful list">'
        '<img class="brand-mark" src="giftful_logo.png" alt="giftful" width="280" height="95"/>'
        '<span class="brand-tagline">Today\'s deals</span>'
        '</a>'
        '<div class="meta">'
        f'<span>Last updated {html.escape(timestamp_et)}</span>'
        "</div>"
        "</header>"
        f"<main>{body}</main>"
        '<footer class="site">'
        "Updated automatically every Monday. "
        '<a href="https://github.com/eirossum-source/giftful-deals/actions/workflows/run_deals.yml" '
        'target="_blank" rel="noopener noreferrer" style="color:var(--accent)">Run manually</a>.'
        "</footer>"
        f"<script>{_JS}</script>"
        "</body></html>"
    )
