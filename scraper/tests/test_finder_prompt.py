"""Guards for finder/PROMPT.md — the scheduled Claude job's instructions.

The prompt is the contract between the finder job and the S3b checker, so its limits
and its finds.json example are checked here.
"""
import json
import re
from pathlib import Path

PROMPT = Path(__file__).resolve().parents[2] / "finder" / "PROMPT.md"

CATEGORIES = {"Accessories", "Athleisure", "Casual", "Jackets", "Shoes", "Tech"}
FIND_FIELDS = {
    "url", "name", "store", "category", "image_url",
    "seen_price", "seen_list_price", "similar_to", "found_at",
}


def _text():
    return PROMPT.read_text(encoding="utf-8")


def _example():
    blocks = re.findall(r"```json\n(.*?)```", _text(), re.S)
    assert len(blocks) == 1, "expected exactly one ```json example block"
    return json.loads(blocks[0])


def test_prompt_exists():
    assert PROMPT.is_file()


def test_prompt_states_every_limit():
    text = _text()
    for limit in ("20 web searches", "30 page reads", "15 minutes",
                  "30 finds", "6 per category"):
        assert limit in text, limit


def test_prompt_names_branch_and_forbids_main():
    text = _text()
    assert "claude/finds" in text
    assert "state/finds.json" in text
    assert "Never push to `main`" in text


def test_prompt_excludes_unreadable_stores_and_list_items():
    text = _text()
    assert "asos.com" in text
    assert "state/inventory.json" in text
    assert "state/taste.json" in text


def test_prompt_demands_coverage_but_never_padding():
    text = _text()
    assert "at least 2 searches" in text      # coverage floor before it may say "done"
    assert "Never pad" in text                # scarce sales mean fewer finds, not loose ones
    assert "sale listing page" in text        # one page read can surface several sales
    assert "at least one store page" in text  # a search alone (news, blogs) is not coverage
    assert "unused searches or page reads" in text  # no early "done" with budget left


def test_prompt_computes_skip_list_with_a_script_and_limits_blocked():
    text = _text()
    assert "SKIP:" in text and "READABLE:" in text   # script prints both lists; skip is checkable
    assert "Never fetch a SKIP store" in text
    assert "at least 4 different readable stores" in text   # `blocked` needs real evidence


def test_prompt_takes_timestamp_from_clock_and_reports_blocked():
    text = _text()
    assert "date -u +%Y-%m-%dT%H:%M:%SZ" in text   # generated_at must be read, not guessed
    assert "`blocked`" in text                     # a network/store block must not read as "done"


def test_example_parses_with_all_fields():
    data = _example()
    assert data["version"] == 1
    assert set(data["run"]) == {"searches_used", "pages_read", "stopped_because",
                                "categories_searched"}
    assert set(data["run"]["categories_searched"]) <= CATEGORIES
    assert data["finds"], "example should show at least one find"
    for find in data["finds"]:
        assert set(find) == FIND_FIELDS
        assert find["category"] in CATEGORIES
        assert find["url"].startswith("https://")
        assert find["seen_price"] < find["seen_list_price"]
