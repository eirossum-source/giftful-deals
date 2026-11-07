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
