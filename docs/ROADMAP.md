# Roadmap: giftful-deals — personal shopper revamp

## Status: PAUSED (2026-11-19) — replaced by the Claude Duet "Giftful Finds" dashboard

The deals job now runs in Claude Duet. The "Run deals" workflow and the "giftful-deals finder"
routine are switched off (not deleted). `/next-slice`: do not start anything; see "How to restart".

**What this is:** the Giftful deals email becomes a personal shopper. It still reports sales,
codes and restocks on Isaac's Giftful wishes, and adds similar on-sale items that aren't on his
list (grouped by category, photo grid) plus a search page that finds on-sale items similar to
what he's gotten and wants. Target: first full email by 2026-11-13, ready for Black Friday
(2026-11-27). Full design: `~/.claude/plans/this-session-will-be-shimmying-stallman.md`.

**Tools:** scheduled Claude job (Sonnet, medium, capped) finds new items; the GitHub run
price-checks them and sends the email; SerpApi Google Shopping (250/month, stops at 230),
Gemini free tier and Vercel free plan run live search. No credit cards on any free service.

## SWITCHOVER DONE (2026-11-19) — repo decommissioned, restartable

Side-by-side checks on Nov 16 and Nov 19 found the Duet dashboard more accurate than the Resend
email (which flagged code-only, full-price, sold-out and mispriced items). Isaac decided to
decommission the GitHub version:
- "Run deals" workflow **disabled** (`gh workflow disable`): no more email or page updates.
- "giftful-deals finder" routine (`trig_01GXWy7kpi3nyUqmAxiCLnZA`, Sun/Wed 10 PM ET) **disabled**
  (enabled false, not deleted).
- Code, workflow file, secrets and GitHub Pages setup are untouched. The page at
  `docs/index.html` stays up showing the last run's deals (stale).
- **S5a and S5b: superseded** by the Claude Duet dashboard (Like / Pass, live price checks).
  S4c's GitHub-issue votes are superseded the same way.
- **S5c, S6a, S6b: superseded too** (decided 2026-11-21). Every open item is now superseded.

### How to restart

1. Re-enable the workflow: `gh workflow enable "Run deals"`. Secrets (`RESEND_API_KEY`,
   `TO_EMAIL`) are unchanged; schedule stays Mon + Thu 07:00 UTC. Test with
   `gh workflow run "Run deals"` — a manual dispatch sends the real email.
2. Re-enable the finder routine: set `enabled: true` on `trig_01GXWy7kpi3nyUqmAxiCLnZA`
   (claude.ai/code/routines) so `state/finds.json` on `claude/finds` is refreshed again.
3. Pages needs nothing: still served from `main:/docs`; the next run rebuilds `docs/index.html`.
4. Expect a gap: `state/inventory.json` and `state/tracked_finds.json` are as of the last run, so
   the first run after a long pause may show stale "back in stock" / price-drop comparisons.
   Votes recorded in `state/feedback.json` stay valid; open vote issues are read on the next run.
5. If the Duet routines are still running, turn them off first, to avoid two competing feeds.

## GAME PLAN UPDATE (2026-11-15) — historical; superseded by the switchover above

Decided in Isaac's Claude Duet "giftful-deals" channel (Nov 11–15). **The repo's job is being
replaced** by a Claude Duet routine. Until the switchover is confirmed, this repo stays exactly as
it is and no new slice starts.

**The new setup (lives in Claude Duet, not in this repo)**
1. One Duet routine does both parts: checks his Giftful list items for sales (only items not
   checked off) and suggests new on-sale picks guided by the checked-off items.
2. Results go to a Claude dashboard, "Giftful Finds": his list deals on top, picks with
   Like / Pass underneath. **No email, no GitHub page.**
3. Schedule: Mon + Thu 12:47 PM ET, plus daily Nov 20 to Nov 30 (Black Friday / Cyber Monday).
4. Rules added there: a cheaper store in Giftful's price dialog (5%+ below, no marketplaces)
   counts as a price drop for items whose store page can't be read; Amazon and unreadable stores
   use Giftful's price.
5. Its working files (list-check, taste, claimed items, price history, finds history) live in the
   dashboard's own database, **not in this repo**.

**Trial and switchover**
- Run both side by side through Mon Nov 16 and Thu Nov 19; compare the dashboard with the GitHub
  deals email.
- If they match, Isaac turns off the "Run deals" GitHub Actions workflow around Nov 19, and the
  old "giftful-deals finder" routine (Sun/Wed 10 PM ET, reads `finder/PROMPT.md`) is stopped.
  Both are Isaac's actions, not a slice.
- Known gap from the Nov 12 comparison: the repo caught a Tom Ford FT5737-B promo (code) that the
  new setup missed; the cheaper-store rule is meant to close most of that.

**Until the switchover: do not change** `.github/workflows/run_deals.yml`, `finder/PROMPT.md` or
any file in `state/`.

**Roadmap effect**
- **S5a (live search test) and S5b (Vercel votes/search service): PAUSED.** Do not start them.
  After the switchover they are marked **superseded**.
- The 👍 / 👎 GitHub-issue votes (S4c) are replaced by the dashboard's Like / Pass; mark S4c's
  vote mechanism superseded at switchover (the S4c checkbox stays ticked: it shipped).
- Not decided in the channel, held for Isaac: **S5c** (search box depends on S5b), **S6a** (daily
  runs by editing the Actions schedule, which would change the deals workflow) and **S6b** (check
  first real runs). The Duet routine already covers the daily Black Friday window, so these are
  likely superseded too; ask Isaac before touching them.
- `/next-slice`: stop and report this section instead of starting S5a.

## How to execute each milestone (copy-paste recipe)

Fresh session, auto-approve permission mode. Then:

```
/clear → /model <orchestrator model> → /effort <only if it differs> → /next-slice
```

The session orchestrates: one implementer sub-agent per plan task on the model below, an Explore
sub-agent for research, and a fresh-context verifier before Ship & Verify. The main loop
integrates and runs the real tests (`.venv/bin/python -m pytest scraper/tests/ -q`).

**`/goal` per milestone:** `<milestone-specific gate> AND all tests pass AND committed and pushed
to main AND the result verified in the real output AND the roadmap checkbox is ticked AND the
session summary is saved`.

**Plans are written just-in-time** by each `/next-slice` session into `docs/superpowers/plans/`;
do not pre-write plans for later slices.

**Hard stops `/next-slice` must not chain past:** the whole roadmap while the game plan update
above is active (S5a/S5b paused); S5a/S5b until the owner has created the free
SerpApi, Google AI Studio and Vercel accounts and added their keys as secrets; S3c until the
owner approves the first measured Claude-job usage; S5a if the quality test is poor (go/no-go).

### Model table (orchestrator / implementers / effort)

| Milestone | Orchestrator | Implementer sub-agents | Why |
|---|---|---|---|
| S1d PRODUCT.md | Sonnet 5 / medium | Sonnet 5 | one Impeccable init pass |
| S2a Read checked-off items | Sonnet 5 / medium | Sonnet 5 | scraper change with fixtures; follows existing giftful.py patterns |
| S3a Finder job instructions | Opus 5 / medium | Opus 5 | prompt quality decides taste matching and usage cost |
| S3b Check every find | Opus 5 / high | Opus 5 | reuses price checker and validator; repeat-until-off-sale rules are subtle |
| S3c Schedule and measure | Sonnet 5 / medium | Sonnet 5 | workflow edit plus a measurement; owner reviews usage |
| S4a Photo-grid email | Opus 5 / medium | Sonnet 5 / high | patterned email layout; image-heavy rendering to check |
| S4b Page by category | Sonnet 5 / high | Sonnet 5 | same data as S4a in html_builder.py |
| S4c Like / dislike | Opus 5 / medium | Sonnet 5 / high | storage choice for a static page and email; feedback must reach the finder |
| S5a Quality test | Sonnet 5 / medium | Sonnet 5 | about 10 searches and a go/no-go write-up |
| S5b Search service | Opus 5 / high | Opus 5 | passcode, search counter and fallback must not fail open |
| S5c Search box | Sonnet 5 / high | Sonnet 5 | small front-end addition |
| S6a Daily runs | Sonnet 5 / low | Sonnet 5 | schedule edit with a date window |
| S6b Check first real runs | Opus 5 / medium | Opus 5 | judgment on links, prices and usage |

## Completion checklist

### Stage 0 — Original deals tool
- [x] **S0a — Deals email and page** — twice-weekly price drops, codes and restocks for Giftful wishes (April–October 2026)

### Stage 1 — Setup
- [x] **S1a — Repair local Python** — Homebrew Python was gone; rebuilt on Apple Python 3.9, all 254 tests pass
- [x] **S1b — Pull latest and log corrections**
- [x] **S1c — Roadmap and hub tracking**
- [x] **S1d — PRODUCT.md** — design context via Impeccable

### Stage 2 — Taste data
- [x] **S2a — Read checked-off items** — claimed items from all six lists, de-duplicated, saved to `state/taste.json`, kept out of deal tracking

### Stage 3 — New finds
- [x] **S3a — Finder job instructions** — `finder/PROMPT.md` with limits; results to `state/finds.json` on the `claude/finds` branch (plan: `docs/superpowers/plans/2026-11-05-S3a-finder-prompt.md`)
- [x] **S3b — Check every find** — `scraper/finds.py`: store price check, any discount (crossed-out price), in stock, not already on the list; repeats until no longer on sale (plan: `docs/superpowers/plans/2026-11-06-S3b-check-finds.md`)
- [x] **S3c — Schedule and measure** — job runs Mon/Thu 03:00 UTC (4 hours before the email) as a Claude routine; measured at well under 1% of weekly allowance per run (plan: `docs/superpowers/plans/2026-11-06-S3c-schedule-and-measure.md`)

### Stage 4 — Email and page
- [x] **S4a — Photo-grid email by category** — his own list's deals first (all of them, owner request 2026-11-06), then "Suggestions for you": 2–4 finds per category, about 16; show only finds with `on_sale: true` from a `state/tracked_finds.json` whose `checked_at` is this run's date (a crashed finds check leaves last run's flags behind) (plan: `docs/superpowers/plans/2026-11-06-S4a-photo-grid-email.md`)
- [x] **S4b — Page by category** — his list first, then "Suggestions for you" by category, every on-sale find, no cap (plan: `docs/superpowers/plans/2026-11-07-S4b-page-by-category.md`)
- [x] **S4c — Like / dislike on new finds** — 👍 / 👎 on each suggestion in the email and page. 👍 = keep showing this item and find more like it; 👎 = stop showing this item and find less like it. Likes teach the finder; votes are prefilled GitHub issues read into `state/feedback.json` (plan: `docs/superpowers/plans/2026-11-10-S4c-like-dislike.md`). *Vote mechanism to be superseded by the dashboard's Like / Pass at switchover (game plan 2026-11-15).*

### Stage 5 — Live search
- [ ] **S5a — SUPERSEDED by the Claude Duet dashboard (2026-11-19) — Quality test** — about 10 Google Shopping searches incl. "swim trunks" and "christian tees"; read Gemini daily limit; stop if poor
- [ ] **S5b — SUPERSEDED by the Claude Duet dashboard (2026-11-19) — Search service on Vercel** — passcode, search counter (stops at 230), Gemini ranking with fallback
- [ ] **S5c — SUPERSEDED by the Claude Duet dashboard (2026-11-21) — Search box on the page** — on sale by default, all-prices switch

### Stage 6 — Black Friday
- [ ] **S6a — SUPERSEDED by the Claude Duet routines (daily Nov 20–30) (2026-11-21) — Daily runs 2026-11-23 to 2026-12-01**, then back to twice weekly
- [ ] **S6b — SUPERSEDED (2026-11-21; checked in the Duet side-by-side trial instead) — Check first real runs** — links, prices, usage
