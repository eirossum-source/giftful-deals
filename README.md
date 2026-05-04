# giftful-deals

Automated deal tracker for [Giftful](https://giftful.com) wishlists. Runs weekly, checks retailer prices and stock, and publishes a deals page.

## Live output

[View today's deals →](https://eirossum-source.github.io/giftful-deals/)

## What it does

1. Scrapes your Giftful list for gift items and retailer links
2. Fetches current prices and stock status from each retailer
3. Checks for promo codes
4. Identifies deals: price drops, promos, and back-in-stock items
5. Builds `docs/index.html` (published via GitHub Pages)
6. Sends a deal summary email via Resend

## Architecture

| File | Responsibility |
|------|---------------|
| `scraper/main.py` | Orchestrator — runs the full pipeline |
| `scraper/giftful.py` | Scrapes Giftful profile, categories, and item modals |
| `scraper/price_checker.py` | Fetches retailer prices (requests → Playwright fallback) |
| `scraper/coupon_checker.py` | Looks up promo codes for each retailer |
| `scraper/validator.py` | Validates link integrity, product identity, sold-out status |
| `scraper/inventory.py` | Reads/writes `state/inventory.json` (price + stock history) |
| `scraper/filter.py` | Evaluates deal types: `PRICE_DROP`, `PROMO`, `BACK_IN_STOCK` |
| `scraper/html_builder.py` | Renders `docs/index.html` (dark theme, category sections) |
| `scraper/emailer.py` | Sends deal email via Resend HTTP API |
| `scraper/error_log.py` | Structured diagnostic logging |

## Setup

```bash
git clone https://github.com/eirossum-source/giftful-deals.git
cd giftful-deals

python3 -m venv .venv
source .venv/bin/activate
pip install -r scraper/requirements.txt
playwright install chromium
```

Copy `.env.example` to `.env` and fill in your secrets (see [Secrets](#secrets) below).

## Running locally

```bash
PYTHONPATH=scraper .venv/bin/python scraper/main.py
```

## Running tests

```bash
.venv/bin/python -m pytest scraper/tests/ -q
```

## Secrets

| Variable | Required | Description |
|----------|----------|-------------|
| `RESEND_API_KEY` | Yes | Resend API key for email delivery |
| `TO_EMAIL` | Yes | Recipient email address for deal alerts |
| `ANTHROPIC_API_KEY` | No | Enables LLM validation gate (currently unused) |

Set these as GitHub repo secrets for CI, or in a local `.env` file for development.

## CI/CD

`.github/workflows/run_deals.yml` runs automatically every **Monday at 7 AM UTC** and supports manual dispatch.

Steps:
1. Set up Python 3.11 + Playwright Chromium
2. Run `scraper/main.py` with injected secrets
3. Auto-commit updated `docs/index.html`, `state/inventory.json`, `state/review_log.json`
4. Upload `errors.log` as a workflow artifact

## State files

| File | Purpose |
|------|---------|
| `state/inventory.json` | Per-URL price and stock history across runs |
| `state/review_log.json` | Per-run diagnostic log — inspect with `jq` to triage false positives |
