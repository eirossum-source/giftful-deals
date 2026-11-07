# S4b — Page by category

**Goal:** `docs/index.html` shows everything on sale: his list's deals (as today, grouped by
category) and, below them, the finder's on-sale finds under "Suggestions for you", grouped by the
six finds categories. No caps on the page. Same freshness rule as the email.

**Out of scope:** like/dislike (S4c), search box (S5), any change to `finds.py`, `emailer.py`
logic, or the finder. No refactors of existing html_builder code.

## Decisions

- `render(deals, generated_at, review_items=None, finds=None, today=None)`. `today=None` means no
  finds (freshness cannot be proven), same as the email.
- Eligibility reuses `emailer._eligible_finds(ledger, today)` (import it; do not copy the rule).
- Finds sort: `finds.CATEGORIES` order; within a category biggest discount fraction first.
- Page structure (finds present): filter bar, then block "Your list" (heading + existing category
  groups; omitted if there are no deals), then block "Suggestions for you" (heading + one
  `.category-group` per category that has finds, `data-category` set). With NO eligible finds the
  output must be unchanged from today (no extra headings) so existing tests keep passing.
- No deals but finds exist: skip the empty state, show only the suggestions block. No deals and no
  finds: existing empty state.
- Find card: same `.deal-card` markup shape as the legacy card. `data-types="price_drop"`,
  `data-store` = the find's `store` string (lower-cased, HTML-escaped). Badge `-N%` (badge-drop),
  tag `price drop`, store line shows the store name, image or `PLACEHOLDER_SVG`. Name linked.
  No "Your list" pill. Everything escaped.
- Filter bar: Store dropdown also lists find stores (sorted, de-duplicated with deal domains,
  lower-cased). Type dropdown unchanged (finds only count as Price Drop).
- JS: hide a block's heading when none of its cards are visible (wrap each block in
  `<div class="section-block">` carrying the heading; group-hiding logic stays).
- CSS: a `.section-title` style consistent with `.category-heading` but larger; no new colours.
- `main.py`: `render(..., finds=finds_ledger, today=today)` (variables already in scope; confirm
  `today` is the run date used for `send_email`).
- Footer text unchanged.

## Task 1 — html_builder + main wiring (implementer: Sonnet 5)

Tests first in `scraper/tests/test_html_builder.py` (and one in `test_main.py`):
1. Stale ledger (`checked_at` ≠ today) or `today=None` → output identical to rendering without finds.
2. Fresh ledger → only `on_sale` finds with real discount and known category render; off-sale and
   `current >= list` do not.
3. "Your list" and "Suggestions for you" headings appear only when finds exist; list deals come first.
4. Suggestions grouped by CATEGORIES order, biggest discount first; no cap (7 finds in one category
   all render).
5. Find card: image, linked name, struck list price + current price, `-N%` badge, store; missing
   image → placeholder; a `<script>` in name/url/store renders escaped.
6. Store filter includes find stores; find cards carry `data-store`/`data-types="price_drop"`.
7. No deals + fresh finds → no empty-state, suggestions shown. No deals, no finds → empty state.
8. `main.run` passes the ledger and run date to `render` (follow how existing tests inject/monkeypatch).

Keep every existing test passing unmodified unless it asserts the exact old output.
Run: `.venv/bin/python -m pytest scraper/tests/ -q` (Python 3.9: no `match`, no `X | Y` types).

## Verify

Full suite passes. Build a preview page from the real `state/finds.json` on `claude/finds`
(treated as a fresh on-sale ledger) plus a couple of real list items, open it in the browser pane
at desktop and phone width: headings, grouping, photos load, filters hide/show blocks and headings.
First real page with finds ships with Monday 2026-11-09's run.
