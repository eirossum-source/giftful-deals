"""Guards for the deals workflow's S3b wiring (finds in, tracked finds out)."""
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "run_deals.yml"


def _text():
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_reads_finds_before_the_scraper_without_failing():
    text = _text()
    read = text.index("Read latest finds from claude/finds")
    scrape = text.index("Run deal scraper")
    assert read < scrape
    step = text[read:scrape]
    assert "origin/claude/finds:state/finds.json" in step
    assert 'rm -f "$RUNNER_TEMP/finds.json"' in step  # missing branch is not an error


def test_scraper_gets_finds_path_and_ledger_is_committed():
    text = _text()
    assert "FINDS_INCOMING: ${{ runner.temp }}/finds.json" in text
    assert "git add state/tracked_finds.json" in text
