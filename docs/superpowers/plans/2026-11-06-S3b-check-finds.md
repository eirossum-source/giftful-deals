# S3b — Check every find (plan)

**Goal:** every item the finder saved is re-checked at the store on each deals run. A find is
shown only when this run confirmed it: a crossed-out price above the current price, in stock, the
right product, and not already on Isaac's list or already given to him. Finds stay tracked across
runs until they are no longer on sale.

**Input:** `state/finds.json` on `claude/finds` (contract: `finder/PROMPT.md`).
**Output:** `state/tracked_finds.json` on `main` (committed by the workflow). Display is S4a/S4b.

## Decisions

1. **Reading the branch** — a workflow step before the scraper runs
   `git fetch --depth=1 origin claude/finds:refs/remotes/origin/claude/finds` and
   `git show origin/claude/finds:state/finds.json > $RUNNER_TEMP/finds.json`. A missing branch or
   file is not an error (the finder has not run yet). The path reaches Python via the
   `FINDS_INCOMING` env var. No git in Python.
2. **Ledger** — `state/tracked_finds.json`:
   `{"version": 1, "checked_at", "source_generated_at", "items": {normalized_url: entry}, "dropped": [...]}`.
   Entry: `url, name, store, category, image_url, similar_to, found_at, last_checked,
   current_price, list_price, on_sale, misses`. `dropped` lists this run's removals with a reason
   (debugging for S3c).
3. **Discount test** — page only: `list_price > current_price > 0`. The finder's `seen_*` prices
   are ignored.
4. **Outcomes per check**
   - on sale (ok + discount) → kept, `on_sale: true`, `misses: 0`
   - no crossed-out price / price not lower → dropped (`no longer on sale`)
   - sold out → dropped; wrong product with some name overlap (identity score > 0) → dropped
   - unreadable (fetch failed, no price, identity score 0.00 — which also covers dead links and
     zero-overlap pages, since the validator cannot tell them apart by score) → kept with
     `on_sale: false`, `misses + 1`; dropped after **2** misses in a row. Never shown meanwhile.
5. **Not already his** — dropped when the normalized URL matches a wish URL (this run's Giftful
   items, including every store link, plus last run's inventory keys) or the lower-cased,
   space-collapsed name matches a wish name or a `state/taste.json` name.
6. **Incoming validation** — a find needs `url`, `name`, `image_url` and a category among the six
   Giftful lists; otherwise dropped (`invalid find`). Incoming is skipped when its
   `generated_at` equals the ledger's `source_generated_at` (same finder output already merged).
7. **Cap** — at most **60** tracked finds, applied after the "already his" check; newest `found_at` kept. Bounds run time
   (60 × ~2–5 s fetch, Playwright fallback only when the plain fetch has no price).
8. **Shape** — plain dict entries, not `Item`/`Deal` (a find has no Giftful listed price).
9. **Integration** — `main.run()` checks finds after the wish loop, sharing the session and the
   Playwright page, using `_resolve_identity` (with no prior state). It runs only when
   `finds_ledger_path` is given (the CLI passes it), so tests never touch the real ledger. Any
   error is logged and never blocks the email.

## Tasks (test-first)

1. `scraper/finds.py` + `scraper/tests/test_finds.py`: `load_incoming`, `load_ledger`,
   `save_ledger`, `owned_keys`, `check_finds(ledger, incoming, check, resolve, owned, today)`.
2. `main.py`: `run(..., finds_incoming_path, finds_ledger_path, taste_path)`; summary gains
   `finds_on_sale` when finds ran; CLI reads `FINDS_INCOMING`. Tests in `test_main.py`.
3. Workflow: read-finds step, `FINDS_INCOMING` env, commit `state/tracked_finds.json`. Guard test.

## Verify

- Full suite passes.
- Workflow step simulated on a shallow clone with and without a `claude/finds` branch.
- Live check: two real product URLs through `check_finds` with a real session, ledger written to
  the scratchpad, outcomes match the pages.
