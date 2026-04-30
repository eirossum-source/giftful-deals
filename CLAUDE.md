# Project: giftful-deals

## Project Root
/Users/isaacrossum/claude/claude_code/projects/giftful-deals

## Stack
- Language: Python 3 (project venv at `.venv/`; system has no `python` alias — use `.venv/bin/python`)
- Scraping: Playwright (JS-rendered content on Giftful.com and JS-heavy retailers)
- Validation: patch-only (HTML signal extraction); LLM gate via `ANTHROPIC_API_KEY` env var, currently unused
- Email: Resend HTTP API (secret: `RESEND_API_KEY`; no SMTP)
- Testing: pytest with HTML fixture files (TDD style); 197 tests
- CI/CD: GitHub Actions (`.github/workflows/run_deals.yml` — Monday 7 AM UTC + manual dispatch)
- Static site: GitHub Pages from `main:/docs` (`docs/index.html` built by `html_builder.py`, plus `docs/giftful_logo.png` static asset)
- External services: Giftful.com (scraped), Resend (email delivery)
- Dependencies (`scraper/requirements.txt`): playwright, requests, beautifulsoup4, lxml, resend, python-dateutil

## Conventions
- Secrets via GitHub repo secrets and `.env` — never inline; reference by name only
- Module responsibilities stay separated: one file per concern
  - `giftful.py` — Giftful.com profile + category + modal scrape; `Item`, `StoreLink`, `Category` dataclasses
  - `price_checker.py` — retailer price fetch (requests then Playwright fallback); `extract_price` chain (jsonld → meta → amazon → css)
  - `coupon_checker.py` — promo-code lookup
  - `validator.py` — patch-only validators: `check_link_integrity`, `check_identity`, `check_sold_out` (`_CHALLENGE_PHRASES` is the bot-interstitial substring list)
  - `inventory.py` — committed JSON state at `state/inventory.json` (sold-out tracking + back-in-stock detection)
  - `filter.py` — `Deal`, `StoreEvaluation`, deal-type evaluation (`PRICE_DROP`, `PROMO`, `BACK_IN_STOCK`)
  - `html_builder.py` — render `docs/index.html` (dark theme, category sections, dropdown filters, ET timestamps, branded centered header)
  - `emailer.py` — Resend HTTP delivery
  - `main.py` — orchestrator
  - `error_log.py` — diagnostic log
- Tests live in `scraper/tests/` with HTML fixtures in `scraper/tests/fixtures/`
- Run tests from project root: `.venv/bin/python -m pytest scraper/tests/ -q`
- Direct script runs of scraper modules need `PYTHONPATH=scraper` (modules import each other unqualified)
- TDD: write tests before implementation code
- No git commands without explicit request

## State Files (committed)
- `state/inventory.json` — per-URL: `name`, `last_seen`, `in_stock`, `prev_in_stock`, `current_price`, `listed_price`, `sold_out_since`. `prev_in_stock` is the previous run's `in_stock` value (used for 2-run BACK_IN_STOCK persistence).
- `state/review_log.json` — per-run diagnostic: each item with `status` (`ok` / `review` / `sold_out`) and `reason`. Inspect with `jq` to triage false positives.

## Architecture Decisions (non-obvious)
- **Patch-only validation, no LLM** — `validator.py` uses substring + token-overlap heuristics. `llm_validate` is a stub gated on `ANTHROPIC_API_KEY`.
- **Identity score 0.00 ≠ wrong product** — when a page has no usable title/h1/og or is too short, `check_identity` returns `(True, 0.0)` (couldn't read). Only returns `False` when there's substantial page content with zero token overlap. This avoids treating bot-blocked pages as "wrong product."
- **Bot-challenge detection** — `_CHALLENGE_PHRASES` in `validator.py` is the substring list. Add new phrases here when retailers introduce new anti-bot wording.
- **Deal types are PRICE_DROP / PROMO / BACK_IN_STOCK only** — `SALE` was dropped (too noisy).
- **BACK_IN_STOCK persists for 2 runs** — driven by `prev_in_stock` field. Trace: `oos → in (BIS) → in (BIS, prev_in_stock=False) → in (no BIS, prev_in_stock=True)`.
- **Sold-out detection is conservative** — Schema.org `OutOfStock` OR (no buy CTA + explicit "sold out" text). Avoids false positives from size-variant buttons.
- **URL normalization for inventory keys** — `inventory.normalize_url` strips tracking/affiliate params so the same product across runs maps to one entry.
- **Eastern Time timestamps** — `zoneinfo.ZoneInfo("America/New_York")`.
- **Branded header** — centered `<a class="brand">` wrapping `docs/giftful_logo.png` (the real giftful wordmark) + `Today's deals` tagline. The wordmark image is the link to the Giftful list.
- **Review-section anchors deep-link** to per-category Giftful page (`Item.category_url`) so the user can edit/remove the broken item in one click.

## Stack Detection
If ## Stack or ## Conventions contains [fill in] and I attempt to
write code or create files, stop and say:
"Project config is incomplete. Run /init-project before we proceed."

## What NOT To Do
- Do not refactor working code unless explicitly asked
- Do not overwrite files without confirming first
- Do not add packages without asking first

## Secrets
Never write credentials, tokens, or API keys inline.
Always use .env and reference variables by name.
Never read .env contents aloud or print them in output.

## Git
Do not run git commands unless explicitly asked.
When asked, state what the command will do before running it.

## Init
If ## Stack or ## Conventions was just written by /init-project,
remind me to run /save-summary before restarting the session.

## Session State
Do not load session state automatically.
Always run /load-summary explicitly at session start and after /clear.
