# Roadmap: giftful-deals — personal shopper revamp

## Status: IN PROGRESS

**What this is:** the Giftful deals email becomes a personal shopper. It still reports sales,
codes and restocks on Isaac's Giftful wishes, and adds similar on-sale items that aren't on his
list (grouped by category, photo grid) plus a search page that finds on-sale items similar to
what he's gotten and wants. Target: first full email by 2026-11-13, ready for Black Friday
(2026-11-27). Full design: `~/.claude/plans/this-session-will-be-shimmying-stallman.md`.

**Tools:** scheduled Claude job (Sonnet, medium, capped) finds new items; the GitHub run
price-checks them and sends the email; SerpApi Google Shopping (250/month, stops at 230),
Gemini free tier and Vercel free plan run live search. No credit cards on any free service.

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

**Hard stops `/next-slice` must not chain past:** S5a/S5b until the owner has created the free
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
- [ ] **S1d — PRODUCT.md** — design context via Impeccable

### Stage 2 — Taste data
- [ ] **S2a — Read checked-off items** — claimed items from all six lists, de-duplicated, saved to `state/taste.json`, kept out of deal tracking

### Stage 3 — New finds
- [ ] **S3a — Finder job instructions** — `finder/PROMPT.md` with limits; results to `state/finds.json` on the `claude/finds` branch
- [ ] **S3b — Check every find** — `scraper/finds.py`: store price check, any discount (crossed-out price), in stock, not already on the list; repeats until no longer on sale
- [ ] **S3c — Schedule and measure** — job runs before each email; first run measured and reported (target under 3% of weekly allowance)

### Stage 4 — Email and page
- [ ] **S4a — Photo-grid email by category** — 2–4 items per category, "Your list" tag, about 16 items
- [ ] **S4b — Page by category** — everything on sale, same tags

### Stage 5 — Live search
- [ ] **S5a — Quality test** — about 10 Google Shopping searches incl. "swim trunks" and "christian tees"; read Gemini daily limit; stop if poor
- [ ] **S5b — Search service on Vercel** — passcode, search counter (stops at 230), Gemini ranking with fallback
- [ ] **S5c — Search box on the page** — on sale by default, all-prices switch

### Stage 6 — Black Friday
- [ ] **S6a — Daily runs 2026-11-23 to 2026-12-01**, then back to twice weekly
- [ ] **S6b — Check first real runs** — links, prices, usage
