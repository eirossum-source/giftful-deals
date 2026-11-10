"""S4c — like / dislike votes travel as prefilled GitHub issues; read them back here."""
import json
from urllib.parse import parse_qs, urlparse

import feedback
from feedback import (
    fetch_open_issues,
    load_feedback,
    merge_votes,
    parse_issue,
    save_feedback,
    vote_keys,
    vote_link,
)
from finds import url_key

ENTRY = {
    "url": "https://shop.example.com/products/faith-tee?x=1&y=2",
    "name": "Faith Boxy Tee & Co",
    "category": "Casual",
    "store": "shop.example.com",
}
REPO = "someone/giftful-deals"


def _issue(vote="like", url="https://shop.example.com/p/tee", number=7, login="someone",
           created_at="2026-11-10T12:00:00Z", body=None, **extra):
    if body is None:
        body = (
            "Tap \"Submit new issue\" to send this to the giftful-deals finder.\r\n\r\n"
            "<!-- giftful-feedback v1 -->\r\n"
            f"vote: {vote}\r\nurl: {url}\r\nname: Faith Tee\r\ncategory: Casual\r\n"
            "store: shop.example.com\r\n"
        )
    issue = {
        "number": number,
        "user": {"login": login},
        "created_at": created_at,
        "body": body,
    }
    issue.update(extra)
    return issue


# --- vote_link ---------------------------------------------------------------------

def test_vote_link_prefills_title_and_body():
    link = vote_link("like", ENTRY, repo=REPO)
    parsed = urlparse(link)
    assert (parsed.scheme, parsed.netloc, parsed.path) == (
        "https", "github.com", "/someone/giftful-deals/issues/new")
    q = parse_qs(parsed.query)
    assert q["title"] == ["\U0001F44D Like: Faith Boxy Tee & Co"]
    body = q["body"][0]
    assert "<!-- giftful-feedback v1 -->" in body
    assert "vote: like" in body
    assert f"url: {ENTRY['url']}" in body
    assert "name: Faith Boxy Tee & Co" in body
    assert "category: Casual" in body
    assert "store: shop.example.com" in body
    assert "Submit new issue" in body


def test_vote_link_dislike_title_and_encoding():
    link = vote_link("dislike", ENTRY, repo=REPO)
    assert "+" not in link.split("?", 1)[1]  # spaces are %20, not +
    assert " " not in link
    q = parse_qs(urlparse(link).query)
    assert q["title"][0].startswith("\U0001F44E Dislike: ")
    assert "vote: dislike" in q["body"][0]


def test_vote_link_cuts_long_names_in_title():
    entry = dict(ENTRY, name="N" * 200)
    q = parse_qs(urlparse(vote_link("like", entry, repo=REPO)).query)
    assert q["title"][0] == "\U0001F44D Like: " + "N" * 80


def test_vote_link_defaults_to_module_repo():
    link = vote_link("like", ENTRY)
    assert f"https://github.com/{feedback.REPO}/issues/new?" in link


def test_vote_link_round_trips_through_parse_issue():
    q = parse_qs(urlparse(vote_link("dislike", ENTRY, repo=REPO)).query)
    parsed = parse_issue(_issue(body=q["body"][0]), "someone")
    assert parsed["vote"] == "dislike"
    assert parsed["url"] == ENTRY["url"]
    assert parsed["name"] == ENTRY["name"]
    assert parsed["category"] == "Casual"


def test_owner_is_part_before_slash():
    assert feedback.OWNER == feedback.REPO.split("/")[0]


# --- parse_issue -------------------------------------------------------------------

def test_parse_issue_reads_fields():
    out = parse_issue(_issue(), "someone")
    assert out == {
        "vote": "like",
        "url": "https://shop.example.com/p/tee",
        "name": "Faith Tee",
        "category": "Casual",
        "store": "shop.example.com",
        "voted_at": "2026-11-10",
        "issue": 7,
        "created_at": "2026-11-10T12:00:00Z",
    }


def test_parse_issue_owner_check_is_case_insensitive():
    assert parse_issue(_issue(login="SomeOne"), "someone") is not None


def test_parse_issue_rejects_other_authors():
    assert parse_issue(_issue(login="stranger"), "someone") is None


def test_parse_issue_rejects_pull_requests():
    assert parse_issue(_issue(pull_request={"url": "x"}), "someone") is None


def test_parse_issue_needs_marker():
    body = "vote: like\nurl: https://shop.example.com/p/tee\n"
    assert parse_issue(_issue(body=body), "someone") is None


def test_parse_issue_needs_valid_vote():
    assert parse_issue(_issue(vote="love"), "someone") is None


def test_parse_issue_needs_http_url():
    assert parse_issue(_issue(url="javascript:alert(1)"), "someone") is None
    assert parse_issue(_issue(url=""), "someone") is None


def test_parse_issue_tolerates_spacing_and_missing_optionals():
    body = "<!-- giftful-feedback v1 -->\r\n  vote:   Like  \r\nurl:  https://a.example.com/p \r\n"
    out = parse_issue(_issue(body=body), "someone")
    assert out["vote"] == "like"
    assert out["url"] == "https://a.example.com/p"
    assert out["name"] == "" and out["category"] == "" and out["store"] == ""


def test_parse_issue_handles_missing_body_and_user():
    assert parse_issue({"number": 1, "user": None, "body": None}, "someone") is None
    assert parse_issue({}, "someone") is None


# --- fetch_open_issues -------------------------------------------------------------

class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else []

    def json(self):
        return self._payload


def test_fetch_open_issues_calls_api_with_token():
    seen = {}

    def get(url, headers=None, params=None, timeout=None):
        seen.update(url=url, headers=headers, params=params)
        return _Resp(200, [{"number": 1}])

    out = fetch_open_issues("someone/giftful-deals", "tok123", get=get)
    assert out == [{"number": 1}]
    assert seen["url"].startswith("https://api.github.com/repos/someone/giftful-deals/issues")
    assert "state=open" in seen["url"] + str(seen["params"]) or seen["params"]["state"] == "open"
    blob = seen["url"] + json.dumps(seen["params"] or {})
    assert "creator" in blob and "someone" in blob
    assert "tok123" in seen["headers"]["Authorization"]


def test_fetch_open_issues_no_token_returns_empty_without_calling():
    def get(*a, **k):
        raise AssertionError("must not be called")

    assert fetch_open_issues(REPO, "", get=get) == []
    assert fetch_open_issues(REPO, None, get=get) == []


def test_fetch_open_issues_non_200_or_error_returns_empty():
    assert fetch_open_issues(REPO, "t", get=lambda *a, **k: _Resp(403)) == []

    def boom(*a, **k):
        raise OSError("network down")

    assert fetch_open_issues(REPO, "t", get=boom) == []


def test_fetch_open_issues_non_list_payload_returns_empty():
    assert fetch_open_issues(REPO, "t", get=lambda *a, **k: _Resp(200, {"message": "x"})) == []


# --- load / save -------------------------------------------------------------------

def test_load_feedback_missing_or_bad_file_is_empty(tmp_path):
    assert load_feedback(tmp_path / "nope.json") == {"version": 1, "items": {}}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert load_feedback(bad) == {"version": 1, "items": {}}
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"items": []}))
    assert load_feedback(wrong) == {"version": 1, "items": {}}
    assert load_feedback(None) == {"version": 1, "items": {}}


def test_save_then_load_round_trips_sorted_and_indented(tmp_path):
    path = tmp_path / "state" / "feedback.json"
    state = {"version": 1, "items": {"b.com/x": {"vote": "like"}, "a.com/y": {"vote": "dislike"}}}
    save_feedback(path, state)
    text = path.read_text()
    assert text.index("a.com/y") < text.index("b.com/x")
    assert "\n  " in text
    assert load_feedback(path) == state


# --- merge_votes / vote_keys -------------------------------------------------------

def _vote(vote, url="https://shop.example.com/p/tee", number=1, created_at="2026-11-10T10:00:00Z"):
    return {"vote": vote, "url": url, "name": "Tee", "category": "Casual",
            "store": "shop.example.com", "voted_at": created_at[:10], "issue": number,
            "created_at": created_at}


def test_merge_votes_records_entry_under_url_key():
    out = merge_votes({"version": 1, "items": {}}, [_vote("like", number=5)])
    key = url_key("https://shop.example.com/p/tee")
    assert out["items"][key] == {
        "vote": "like", "url": "https://shop.example.com/p/tee", "name": "Tee",
        "category": "Casual", "store": "shop.example.com",
        "voted_at": "2026-11-10", "issue": 5,
    }


def test_merge_votes_latest_wins_regardless_of_input_order():
    votes = [
        _vote("dislike", number=3, created_at="2026-11-11T09:00:00Z"),
        _vote("like", number=2, created_at="2026-11-10T09:00:00Z"),
    ]
    out = merge_votes({"version": 1, "items": {}}, votes)
    assert list(out["items"].values())[0]["vote"] == "dislike"
    assert list(out["items"].values())[0]["issue"] == 3


def test_merge_votes_new_vote_overrides_stored_one():
    state = merge_votes({"version": 1, "items": {}}, [_vote("like", number=1)])
    state = merge_votes(state, [_vote("dislike", number=2, created_at="2026-11-12T10:00:00Z")])
    assert list(state["items"].values())[0]["vote"] == "dislike"


def test_merge_votes_same_item_different_tracking_params_is_one_key():
    votes = [
        _vote("like", url="https://www.shop.example.com/p/tee/?utm_source=x", number=1),
        _vote("dislike", url="https://shop.example.com/p/tee", number=2,
              created_at="2026-11-10T11:00:00Z"),
    ]
    out = merge_votes({"version": 1, "items": {}}, votes)
    assert len(out["items"]) == 1


def test_merge_votes_does_not_mutate_input():
    state = {"version": 1, "items": {}}
    merge_votes(state, [_vote("like")])
    assert state["items"] == {}


def test_vote_keys_splits_liked_and_disliked():
    state = merge_votes({"version": 1, "items": {}}, [
        _vote("like", url="https://a.example.com/1", number=1),
        _vote("dislike", url="https://b.example.com/2", number=2),
    ])
    liked, disliked = vote_keys(state)
    assert liked == {url_key("https://a.example.com/1")}
    assert disliked == {url_key("https://b.example.com/2")}
