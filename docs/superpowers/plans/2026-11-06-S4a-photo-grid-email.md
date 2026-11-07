# S4a — Photo-grid email by category

**Goal:** the deals email becomes a photo grid grouped by Giftful category. It mixes Isaac's own
list deals (tagged "Your list") with the finder's new finds, 2–4 items per category, about 16 in
all. Finds appear only when `on_sale: true` in a `tracked_finds.json` ledger whose `checked_at`
equals this run's date (a crashed finds check leaves last run's flags behind — those must not show).

**Out of scope:** the web page (S4b), like/dislike (S4c), any change to `finds.py` or the finder.

## Decisions

- Selection lives in `emailer.py` (email layout is its concern): `select_grid(deals, finds_ledger, today)`.
- Category order: `finds.CATEGORIES` order (Accessories, Athleisure, Casual, Jackets, Shoes, Tech),
  then `Other` for list deals with an empty/unknown category.
- Within a category: list deals first (in the order `deals` gives them), then finds by biggest
  discount fraction (`1 - current/list`).
- Caps: `PER_CATEGORY = 4`, `TOTAL = 16`. Fill round-robin — one card per category per round, in
  category order — until the total cap or nothing is left. A category with more than it shows
  gets a "+N more on the deals page →" link to `PAGE_URL`.
- Eligible find: ledger is a dict, `ledger["checked_at"] == today.isoformat()`, entry `on_sale`
  is True, has `url`, `name`, `image_url`, category in `CATEGORIES`, and
  `0 < current_price < list_price`. Anything else is skipped silently.
- Subject keeps today's format; the count is list deals + eligible finds. Zero of both keeps the
  existing "No deals found this week (date)" subject.
- Card content: photo (linked), "YOUR LIST" pill on list deals, store name, item name (linked),
  struck-through reference price + current price + "N% off" when lower, existing PROMO / BACK IN
  STOCK badges and promo-code boxes for list deals, and one small "Also at <store> $X" line per
  extra store for multi-store list deals. Missing image → plain grey placeholder block, card still shown.
- Email-safe markup only: nested tables, inline styles, two cells per row, `<img width="260"
  style="width:100%;max-width:260px;height:auto;display:block">`. No CSS grid/flex, no `<style>`.
- Text part mirrors the grid: category headings, `[Your list]` marker, price line, codes, URL.

## Task 1 — `emailer.py` grid (implementer: Sonnet 5 / high)

Tests first in `scraper/tests/test_emailer.py`, then implement. Tests to add:
1. Stale ledger (`checked_at` = yesterday) → no finds in HTML, text, or subject count.
2. Fresh ledger → only `on_sale: true` finds with a real discount appear; off-sale and
   `current >= list` entries do not.
3. Category order and headings follow `CATEGORIES`, list deals before finds within a category,
   finds sorted by discount.
4. Caps: 6 categories × 6 finds → 16 cards total, ≤4 per category, "+N more" link present with the
   right N for a category that was cut.
5. List deal shows "YOUR LIST"; a find does not. List deal's photo is `item.image_url`; multi-store
   deal links to the winner store.
6. HTML-escaping of names/URLs from the ledger (a `<script>` name renders escaped).
7. Uncategorised list deal lands in an "Other" section after the six categories.
8. Subject count = deals + eligible finds; `send()` accepts `finds=` (default None) and passes the
   grid to both html and text.
9. No deals and no finds → existing empty-state copy still shown.

Adjust existing emailer tests only where the old one-column layout is asserted; keep every
behaviour they check (promo code text, badges, alt stores, page link, prices).

Signatures: `build_html(deals, finds_ledger=None, today=None)`, `build_text(...)` same,
`build_subject(deals, today, finds_ledger=None)`, `send(deals, today, finds=None)`.
`today=None` means no finds (cannot prove freshness).

## Task 2 — wire `main.py` (main loop)

`run()` calls `send_email(deals=deals, today=now.date(), finds=finds_ledger)`. Test in
`test_main.py`: with a ledger path and incoming finds, the sender receives `finds` whose
`checked_at` is the run date; with no ledger path it receives `finds=None`.

## Verify

Full suite passes. Build a preview email from the real `state/finds.json` on `claude/finds`
(treated as a fresh ledger) plus a couple of list items from `state/inventory.json`, open it in
the browser pane, check photos load, tags and grouping are right, and it reads well at phone
width. The first real send with finds is Monday 2026-11-09 07:00 UTC.
