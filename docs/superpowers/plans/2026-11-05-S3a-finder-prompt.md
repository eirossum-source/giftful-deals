# S3a — Finder job instructions — plan

Goal: `finder/PROMPT.md` — the instructions a scheduled Claude job (Sonnet, medium) follows to
find on-sale items similar to Isaac's taste, with hard limits, writing `state/finds.json` to the
`claude/finds` branch only.

## Decisions (answers to the research brief's open questions)
1. **Per-find fields:** `url`, `name`, `store`, `category`, `image_url`, `seen_price`,
   `seen_list_price`, `similar_to`, `found_at`. `seen_*` prices are the finder's claim only —
   S3b re-checks everything at the store and ignores them for display. `similar_to` is internal
   (debugging and S4c), never shown (PRODUCT.md: no "because you got X").
2. **Checker results** do not live in `finds.json`. The finder owns that file; S3b keeps its own
   state on `main`.
3. **Retirement** is S3b's job (repeat until off sale). The finder overwrites `finds.json` each
   run and does not repeat URLs from the previous run's file.
4. **Categories** = the Giftful list names (today: Accessories, Athleisure, Casual, Jackets,
   Shoes, Tech). A candidate that fits none is skipped.
5. **Limits:** ≤ 20 web searches, ≤ 30 page reads, stop by 15 minutes, ≤ 30 finds total,
   ≤ 6 per category. Stop at the first limit hit and save what is found.
6. **Branch:** read inputs from `main` first, then switch to `claude/finds` (create it from main
   if missing), write, commit, push that branch only. S3b/S3c read it with
   `git show origin/claude/finds:state/finds.json`.
7. **Feedback (S4c):** not defined yet; the prompt names the hook only (a future feedback file).

Unreadable stores are derived at run time from `state/inventory.json` (a store whose every entry
has `current_price: null`) plus ASOS, so the list never goes stale.

## Tasks (test first)
1. `scraper/tests/test_finder_prompt.py` — the prompt exists; states every limit; names the
   branch and forbids `main`; its JSON example parses and every find has all fields with a valid
   category.
2. `finder/PROMPT.md` — written to pass the tests.
