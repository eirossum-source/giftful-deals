# S2a — Read checked-off items — plan

Goal: claimed ("checked-off") items from every Giftful list, de-duplicated, saved to
`state/taste.json`, never fed into deal tracking.

## Decisions
- `giftful.parse_claimed_items(html, category_name, category_url)` — new function; `parse_items`
  is untouched, so deal tracking never sees claimed items.
- `giftful.fetch_claimed(profile_url)` — own light Playwright walk (profile → categories →
  `page.content()`); no modal clicks (taste needs name/price/category, not store URLs).
- New `scraper/taste.py` — `merge_claimed(state, items, today)`, `load_taste`, `save_taste`.
  De-dup key = lowercased, whitespace-collapsed name. Accumulates across runs (an item stays once
  seen, even if Giftful later drops it); an item on several lists keeps one entry with all lists.
- `main.py` `__main__` block: fetch claimed before the price-check Playwright (contexts cannot
  nest), refresh taste inside try/except so a taste failure never blocks the deals email. `run()`
  is unchanged.
- Workflow commit step also commits `state/taste.json`.
- "Six lists" = whatever the profile shows; no count assertion.

## Tasks (test first)
1. `parse_claimed_items` + fixture `giftful_category_claimed.html` (1 claimed) and a multi-list
   duplicate case in tests.
2. `taste.py` merge/load/save + tests (dedupe across lists, accumulate, bad file → empty).
3. `fetch_claimed`, `__main__` wiring, workflow commit step.
