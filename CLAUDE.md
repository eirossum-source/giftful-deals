# Project: giftful-deals

## Project Root
/Users/isaacrossum/claude/claude_code/projects/giftful-deals

## Stack
- Language: Python 3
- Scraping: Playwright (JS-rendered content on Giftful.com)
- Email: Resend HTTP API (secret: RESEND_API_KEY; no SMTP)
- Testing: pytest with HTML fixture files (TDD style)
- CI/CD: GitHub Actions (.github/workflows/run_deals.yml — Monday 7 AM UTC + manual dispatch)
- Static site: GitHub Pages from main:/docs (docs/index.html built by html_builder.py)
- External services: Giftful.com (scraped), Resend (email delivery)

## Conventions
- Secrets via GitHub repo secrets and .env — never inline; reference by name only
- Module responsibilities stay separated: one file per concern
  (giftful.py, price_checker.py, coupon_checker.py, filter.py, html_builder.py, emailer.py, main.py, error_log.py)
- Tests live in scraper/tests/ with HTML fixtures in scraper/tests/fixtures/
- TDD: write tests before implementation code
- No git commands without explicit request

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
