# S4c — Like / dislike on new finds

**Goal:** every suggestion in the email and on the page has 👍 / 👎. 👍 = keep showing this item
(stays tracked when it goes off sale or sells out, shows again when back on sale) and find more
like it. 👎 = stop showing it (dropped, never re-added) and find less like it. The finder reads
the votes.

**Out of scope:** search (S5), any change to deal (his list) cards, showing past votes on cards,
refactors.

## Storage decision

Votes travel as **prefilled GitHub issues** on the (public) repo: each button is a
`https://github.com/<repo>/issues/new?title=…&body=…` link; he taps it, then "Submit new issue".
The deals run reads open feedback issues with the built-in `GITHUB_TOKEN`, records them in
`state/feedback.json` (committed), and closes them after the push.

Why: no new service, account or secret; works from a static page and from email; only the repo
owner's issues count, so strangers cannot vote. Cost: two taps instead of one, and votes are
public (the deals page already is). Rejected for now: a Vercel endpoint (one tap, but needs a
GitHub token or Blob store wired up; can replace the link target in S5b without touching the
rest, since links come from one function).

## Formats

Issue title: `👍 Like: <name>` / `👎 Dislike: <name>` (name cut to 80 chars). Body:

```
Tap "Submit new issue" to send this to the giftful-deals finder.

<!-- giftful-feedback v1 -->
vote: like
url: <find url>
name: <name>
category: <category>
store: <store>
```

`state/feedback.json`:
`{"version": 1, "items": {<finds.url_key(url)>: {"vote", "url", "name", "category", "store",
"voted_at": "YYYY-MM-DD", "issue": N}}}`. Latest vote per item wins (by issue `created_at`).

## Task 1 — `scraper/feedback.py`, finds rules, main + workflow wiring (implementer: Sonnet 5 / high)

Tests first: new `scraper/tests/test_feedback.py`, plus additions to `test_finds.py`, `test_main.py`.

`feedback.py`:
- `REPO = os.environ.get("GITHUB_REPOSITORY") or "eirossum-source/giftful-deals"`; owner = part
  before `/`.
- `vote_link(vote, entry, repo=None) -> str` — vote is `"like"`/`"dislike"`; entry has
  url/name/category/store. Query values URL-encoded (`urllib.parse.urlencode`, `quote_via=quote`).
- `parse_issue(issue, owner) -> Optional[dict]` — None unless: not a pull request, author login
  equals owner (case-insensitive), body has the marker, `vote` in like/dislike, `url` is http(s).
  Returns `{vote, url, name, category, store, voted_at (created_at date), issue (number),
  created_at}`. Tolerates `\r\n`, extra spaces, missing optional fields.
- `fetch_open_issues(repo, token, get=requests.get) -> list` — `GET
  https://api.github.com/repos/{repo}/issues?state=open&creator={owner}&per_page=100`, auth
  header from token. Any error or non-200 → `[]` (caller logs). No token → `[]`.
- `load_feedback(path)` / `save_feedback(path, state)` — missing/bad file → empty state; save
  sorted, indented.
- `merge_votes(state, votes) -> state` — apply in `created_at` order; key `finds.url_key(url)`.
- `vote_keys(state) -> (liked: set, disliked: set)`.

`finds.check_finds(..., liked=frozenset(), disliked=frozenset())` (defaults keep old behaviour):
- Disliked key: incoming find skipped and tracked find removed, `dropped` reason
  `"you said 👎"`.
- Liked key: outcome "no longer on sale" or "sold out" → kept with `on_sale: False`, `misses: 0`,
  prices updated when the page gave them. Wrong product and repeated misses still drop. Liked
  finds are exempt from the `MAX_TRACKED` cap (cap trims only unliked, oldest first).

`main.run(..., feedback_path=None, fetch_feedback=None, feedback_processed_path=None)`:
- Before the finds check (only when `finds_ledger_path` is set): load feedback; if
  `fetch_feedback` given, call it, parse with owner, merge, save; pass liked/disliked into
  `check_finds`. Write processed issue numbers (one per line) to `feedback_processed_path` when
  set. Any feedback error is logged and never blocks the run (same as finds).
- `__main__` wiring: `feedback_path=repo_root/"state"/"feedback.json"`, `fetch_feedback` uses
  `GITHUB_TOKEN` + `REPO` (None when no token), processed path from env `FEEDBACK_PROCESSED`.

Workflow `.github/workflows/run_deals.yml`:
- `permissions: contents: write, issues: write`.
- Scraper step env: `GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}`,
  `FEEDBACK_PROCESSED: ${{ runner.temp }}/feedback_issues.txt`.
- Commit step also adds `state/feedback.json`.
- New step after the commit step: if the processed file exists, `gh issue close <n> --comment
  "Recorded in state/feedback.json."` for each (env `GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}`);
  failures do not fail the run (`|| true` per issue). Runs only when earlier steps succeeded,
  so an unpushed vote stays open and is re-read next run.

## Task 2 — buttons in email and page (implementer: Sonnet 5 / high; after Task 1)

Tests first in `test_emailer.py` and `test_html_builder.py`.
- Email (`emailer._find_card` adds `"feedback": {"like": url, "dislike": url}` via
  `feedback.vote_link`; deal cards none). `_card_html` renders, only when present, a row under
  the price: `👍 More like this` and `👎 Not for me` as links (inline styles, `ACCENT` colour,
  13px). Text part: after each find, `  More like this: <url>` / `  Not for me: <url>`.
  Under the "Suggestions for you" heading (HTML and text), one line:
  `👍 / 👎 opens GitHub — tap "Submit new issue" to send it.`
- Page (`html_builder._find_card_html`): after the store line,
  `<div class="feedback">` with two `<a class="vote vote-like|vote-dislike" target="_blank"
  rel="noopener noreferrer" aria-label="More like this|Not for me" title=…>👍|👎</a>`. Same hint
  line under the "Suggestions for you" title (`<p class="section-hint">`). CSS for `.feedback`,
  `.vote`, `.section-hint` using existing colours only.
- All hrefs HTML-escaped. Deal (his list) cards unchanged. No finds → output unchanged.

## Task 3 — finder reads votes (implementer: Sonnet 5 / high; parallel with Task 2)

Tests first in `test_finder_prompt.py`. In `finder/PROMPT.md` §1 replace the "not available yet"
bullet: read `state/feedback.json` from `main` (missing → no votes). `vote: like` items are a
strong taste signal — search for more like them (same brand, style, category). `vote: dislike`
items: never suggest that URL again and avoid close look-alikes (same brand and style). §4 "not
already his" also excludes disliked URLs. Keep every existing rule; tests assert the file name and
both meanings.

## Verify

Full suite passes (Python 3.9 locally; no `match`, no `X | Y`). Build a preview page and email
HTML from the current `state/tracked_finds.json` treated as fresh; open in the browser pane,
check buttons show on suggestions only, and that a 👍 link opens GitHub's new-issue form with the
title and body filled in (do not submit). After push, confirm the workflow file parses (manual
dispatch not required; it sends the real email). First real votes are read by Thursday
2026-11-12's run.
