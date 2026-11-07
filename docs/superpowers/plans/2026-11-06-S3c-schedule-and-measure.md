# S3c — Schedule the finder and measure its first run

No repo code changes; the work is a cloud routine plus a measurement. HARD STOP at the end: the
owner approves the measured usage before the routine is switched on and the box is ticked.

## Decisions

- **Runner:** Claude Code routine (cloud agent) on the Max plan, model `claude-sonnet-5-5`, default
  cloud environment, repo `eirossum-source/giftful-deals`. Routines may push `claude/`-prefixed
  branches, which matches `claude/finds`. Billed to the plan, not the API.
- **Prompt:** one line pointing at `finder/PROMPT.md` on `main`, so changing the instructions
  never means editing the routine.
- **Time:** cron `0 3 * * 1,4` (03:00 UTC, four hours before the 07:00 UTC deals run on Mon/Thu).
  The job's own limit is 15 minutes.
- **Created disabled.** It only starts on schedule after the owner approves the measured usage.
- **Allowance exhausted:** the routine simply fails to start or stops; no finds file is written;
  the deals run already treats a missing/old file as "no new finds" (S3b), so the email still sends.

## Steps

1. Read weekly usage (`get_usage`) immediately before.
2. Create the routine (disabled), run it once by hand.
3. Wait for it to finish; read weekly usage immediately after. Difference = cost of one run.
4. Check `claude/finds` on GitHub: `state/finds.json` exists, matches the contract, and only that
   file changed. Read the run log for blocked sites and limits hit.
5. Report to the owner: usage %, finds count, run stats. Stop.

## Owner gate

Target: under 3% of the weekly allowance per run (two runs a week, so about 6%). Over that: shrink
the job (fewer searches/pages) before enabling. After approval: enable the routine, tick S3c.

## Measurement log (2026-11-07, five by-hand runs)

| Run | Change | Result | Time |
|---|---|---|---|
| 1 | Default environment, limited network | 0 finds; store pages blocked | 32 s |
| 2 | Owner enabled full internet | 2 finds (Cotton On only); stopped at 6 searches | 56 s |
| 3 | Prompt: coverage floor, listing pages, real clock | 13 finds, all Nike; Casual skipped | 126 s |
| 4 | Prompt: store page per category | 0 finds, `blocked` after 3 skip-list stores failed | 38 s |
| 5 | Prompt: skip list by script, `blocked` needs 4 stores | 21 finds, all 6 categories, 11 searches, 14 pages, `done` | ~180 s |

Usage: weekly allowance read 6% at the start and 8% after all five runs plus this whole
working session (about 200k tokens), so each run is well under 1% (target: under 3%). A run
at full limits (20 searches, 30 pages) is untested but at most about twice run 5.
Run 5 checks: all 21 image URLs and product pages load (two product pages returned 429 from
rapid checking, not from the finder). Prompt commits: 6afdd6a, affcca6, 28eee76.
