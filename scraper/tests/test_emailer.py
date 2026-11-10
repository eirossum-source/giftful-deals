from datetime import date

from coupon_checker import PromoCode
from emailer import (
    PAGE_URL,
    build_html,
    build_subject,
    build_text,
    send,
)
from filter import Deal, DealType, StoreEvaluation
from giftful import Item, StoreLink
from price_checker import PriceResult


def _deal(name="Headphones", domain="shop.example.com", promos=None):
    item = Item(
        name=name,
        url=f"https://{domain}/p",
        listed_price=199.0,
        image_url="",
    )
    price = PriceResult(current_price=149.0)
    return Deal(
        item=item,
        price_result=price,
        promos=promos or [],
        deal_types=[DealType.PRICE_DROP],
    )


def _multi_deal(name="Headphones", winner_promos=None):
    store1 = StoreLink(
        url="https://shop.example.com/p",
        display_name="Shop Example",
        listed_price=199.0,
    )
    store2 = StoreLink(
        url="https://store.other.net/p",
        display_name="Other Store",
        listed_price=219.0,
    )
    ev1 = StoreEvaluation(
        store=store1,
        price_result=PriceResult(current_price=149.0),
        promos=winner_promos or [],
        deal_types=[DealType.PRICE_DROP],
    )
    ev2 = StoreEvaluation(
        store=store2,
        price_result=PriceResult(current_price=189.0),
        promos=[],
        deal_types=[DealType.PRICE_DROP],
    )
    item = Item(name=name, listed_price=199.0, image_url="", store_urls=[store1, store2])
    return Deal(item=item, store_evaluations=[ev1, ev2])


def test_subject_with_deals():
    subject = build_subject(deals=[_deal(), _deal()], today=date(2026, 4, 18))
    assert subject == "\U0001F381 Isaac's Deals — 2 items on sale (2026-04-18)"


def test_subject_with_one_deal_is_singular():
    subject = build_subject(deals=[_deal()], today=date(2026, 4, 18))
    assert subject == "\U0001F381 Isaac's Deals — 1 item on sale (2026-04-18)"


def test_subject_zero_deals():
    subject = build_subject(deals=[], today=date(2026, 4, 18))
    assert subject == "No deals found this week (2026-04-18)"


def test_html_body_contains_summary_cta_and_cards():
    promo = [PromoCode(code="SAVE20", description="20% off", expiry=None)]
    deals = [
        _deal(name="Headphones", domain="shop.example.com", promos=promo),
        _deal(name="Grinder", domain="store.example.net"),
    ]

    html = build_html(deals)

    # Strip tags for the plain-text-like assertion
    from bs4 import BeautifulSoup
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    assert "2 deals found across 2 stores" in text
    assert PAGE_URL in html
    assert "View Full Deals Page" in html
    assert "Headphones" in html and "Grinder" in html
    assert "SAVE20" in html
    assert "https://shop.example.com/p" in html
    assert "https://github.com/eirossum-source/giftful-deals/actions" in html


def test_html_body_empty_state_when_zero_deals():
    html = build_html([])
    assert "No deals" in html
    assert PAGE_URL in html  # CTA still present


def test_plain_text_fallback_nonempty_and_contains_details():
    promo = [PromoCode(code="SAVE20", description="20% off", expiry=None)]
    deals = [_deal(promos=promo)]

    text = build_text(deals)

    assert text.strip()
    assert "Headphones" in text
    assert "https://shop.example.com/p" in text
    assert "SAVE20" in text
    assert PAGE_URL in text


def test_plain_text_empty_state():
    text = build_text([])
    assert "No deals" in text
    assert PAGE_URL in text


def test_send_calls_resend_with_expected_payload(mocker):
    api_send = mocker.patch("emailer.resend.Emails.send", return_value={"id": "abc"})
    mocker.patch.dict(
        "os.environ",
        {"RESEND_API_KEY": "re_test", "TO_EMAIL": "you@example.com"},
    )

    result = send(deals=[_deal()], today=date(2026, 4, 18))

    assert result == {"id": "abc"}
    assert api_send.call_count == 1
    payload = api_send.call_args[0][0]
    assert payload["from"] == "onboarding@resend.dev"
    assert payload["to"] == ["you@example.com"]
    assert payload["subject"].startswith("\U0001F381 Isaac's Deals")
    assert "<html" in payload["html"].lower() or "<a " in payload["html"].lower()
    assert payload["text"].strip()


def test_send_raises_on_missing_env(mocker):
    mocker.patch("emailer.resend.Emails.send")
    mocker.patch.dict("os.environ", {}, clear=True)

    import pytest

    with pytest.raises(RuntimeError, match="RESEND_API_KEY"):
        send(deals=[_deal()], today=date(2026, 4, 18))


# --- Slice E: multi-store email rendering ---


def test_multi_store_html_shows_winner_and_secondary():
    html = build_html([_multi_deal()])

    from bs4 import BeautifulSoup

    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)

    assert "Shop Example" in text
    assert "Other Store" in text
    assert "$149.00" in html
    assert "https://shop.example.com/p" in html
    assert "https://store.other.net/p" in html


def test_multi_store_html_winner_promos_shown():
    promo = [PromoCode(code="BEST10", description="10% off", expiry=None)]
    html = build_html([_multi_deal(winner_promos=promo)])

    assert "BEST10" in html
    assert "10% off" in html


def test_multi_store_store_count_in_summary():
    html = build_html([_multi_deal()])

    from bs4 import BeautifulSoup

    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    assert "2 stores" in text


def test_multi_store_text_shows_all_stores():
    promo = [PromoCode(code="SAVE5", description="$5 off", expiry=None)]
    text = build_text([_multi_deal(winner_promos=promo)])

    assert "Shop Example" in text
    assert "Other Store" in text
    assert "$149.00" in text
    assert "$189.00" in text
    assert "SAVE5" in text
    assert "https://shop.example.com/p" in text
    assert "https://store.other.net/p" in text


def test_multi_store_text_mixed_with_legacy():
    deals = [_deal(name="Legacy Item"), _multi_deal(name="Multi Item")]
    text = build_text(deals)

    assert "Legacy Item" in text
    assert "Multi Item" in text
    assert "Shop Example" in text
    assert "shop.example.com" in text


def test_html_strikes_retailer_list_price_when_above_giftful_baseline():
    # Anker: Giftful baseline $33.99, Amazon list $39.99, live $35.99.
    item = Item(
        name="Anker MagSafe Charger",
        url="https://www.amazon.com/dp/B0D8PN1GBP",
        listed_price=33.99,
        image_url="",
    )
    deal = Deal(
        item=item,
        price_result=PriceResult(current_price=35.99, list_price=39.99),
        promos=[],
        deal_types=[DealType.PRICE_DROP],
    )
    html = build_html([deal])
    assert "line-through" in html and "$39.99" in html


def test_multi_store_html_strikes_retailer_list_price():
    store = StoreLink(
        url="https://www.amazon.com/dp/B0D8PN1GBP",
        display_name="Amazon",
        listed_price=33.99,
    )
    ev = StoreEvaluation(
        store=store,
        price_result=PriceResult(current_price=35.99, list_price=39.99),
        promos=[],
        deal_types=[DealType.PRICE_DROP],
    )
    item = Item(
        name="Anker MagSafe Charger",
        url=store.url,
        listed_price=33.99,
        image_url="",
    )
    deal = Deal(
        item=item,
        price_result=ev.price_result,
        promos=[],
        deal_types=[DealType.PRICE_DROP],
        store_evaluations=[ev],
    )
    html = build_html([deal])
    assert "line-through" in html and "$39.99" in html


def test_plain_text_shows_retailer_list_price():
    item = Item(
        name="Anker MagSafe Charger",
        url="https://www.amazon.com/dp/B0D8PN1GBP",
        listed_price=33.99,
        image_url="",
    )
    deal = Deal(
        item=item,
        price_result=PriceResult(current_price=35.99, list_price=39.99),
        promos=[],
        deal_types=[DealType.PRICE_DROP],
    )
    assert "$39.99 -> $35.99" in build_text([deal])


# --- S4a: photo grid by category ---

from datetime import timedelta  # noqa: E402

from emailer import PER_CATEGORY, TOTAL, select_grid  # noqa: E402
from finds import CATEGORIES  # noqa: E402

TODAY = date(2026, 11, 9)


def _find(name, category="Shoes", current=50.0, list_price=100.0, on_sale=True,
          store="shoestore.com", image="https://img.example.com/x.jpg", url=None):
    return {
        "url": url or f"https://{store}/{name.replace(' ', '-')}",
        "name": name,
        "store": store,
        "category": category,
        "image_url": image,
        "current_price": current,
        "list_price": list_price,
        "on_sale": on_sale,
        "misses": 0,
    }


def _ledger(entries, checked_at=None):
    return {
        "version": 1,
        "checked_at": (checked_at or TODAY).isoformat(),
        "items": {e["url"]: e for e in entries},
        "dropped": [],
    }


def _list_deal(name="Listed Thing", category="Shoes", image="https://img.example.com/list.jpg"):
    item = Item(name=name, url="https://shop.example.com/p", listed_price=199.0,
                image_url=image, category=category)
    return Deal(item=item, price_result=PriceResult(current_price=149.0),
                promos=[], deal_types=[DealType.PRICE_DROP])


def _count_cards(html):
    return html.count('data-card="1"')


def test_stale_ledger_shows_no_finds():
    ledger = _ledger([_find("Old Sneaker")], checked_at=TODAY - timedelta(days=1))
    html = build_html([], ledger, TODAY)
    assert "Old Sneaker" not in html
    assert "Old Sneaker" not in build_text([], ledger, TODAY)
    assert build_subject([], TODAY, ledger).startswith("No deals found")


def test_missing_today_means_no_finds():
    ledger = _ledger([_find("Sneaker")])
    assert "Sneaker" not in build_html([], ledger, None)


def test_fresh_ledger_only_on_sale_with_real_discount():
    ledger = _ledger([
        _find("Good Sneaker"),
        _find("Off Sale Sneaker", on_sale=False),
        _find("Same Price Sneaker", current=100.0, list_price=100.0),
        _find("Pricier Sneaker", current=120.0, list_price=100.0),
        _find("No Image Sneaker", image=""),
        _find("Bad Cat Sneaker", category="Hats"),
    ])
    html = build_html([], ledger, TODAY)
    assert "Good Sneaker" in html
    for bad in ("Off Sale", "Same Price", "Pricier", "No Image", "Bad Cat"):
        assert bad not in html
    assert "50% off" in html


def test_category_order_and_within_category_order():
    ledger = _ledger([
        _find("Small Tech", category="Tech", current=90.0),
        _find("Big Shoe", category="Shoes", current=40.0),
        _find("Small Shoe", category="Shoes", current=80.0),
        _find("Acc Thing", category="Accessories", current=70.0),
    ])
    deals = [_list_deal("Mine Shoe", category="Shoes")]
    html = build_html(deals, ledger, TODAY)
    positions = [html.index(f">{c}<") for c in ("Accessories", "Shoes", "Tech")]
    assert positions == sorted(positions)
    assert html.index("Mine Shoe") < html.index("Big Shoe") < html.index("Small Shoe")
    # select_grid ordering too
    sections = select_grid(deals, ledger, TODAY)
    assert [s["category"] for s in sections] == ["Your list", "Accessories", "Shoes", "Tech"]


def test_caps_total_and_per_category_with_more_link():
    entries = []
    for cat in CATEGORIES:
        for i in range(6):
            entries.append(_find(f"{cat} Item {i}", category=cat, current=50.0 - i))
    ledger = _ledger(entries)
    html = build_html([], ledger, TODAY)
    assert _count_cards(html) == TOTAL == 16
    sections = select_grid([], ledger, TODAY)
    assert all(len(s["cards"]) <= PER_CATEGORY for s in sections)
    assert sum(len(s["cards"]) for s in sections) == 16
    # round robin: first four categories get 3, last... check "more" counts add up
    for s in sections:
        assert s["more"] == 6 - len(s["cards"])
    cut = [s for s in sections if s["more"]][0]
    assert f"+{cut['more']} more on the deals page" in html
    assert PAGE_URL in html


def test_list_deal_tagged_and_find_not_and_photo_and_winner_link():
    deal = _multi_deal()
    deal.item.image_url = "https://img.example.com/mine.jpg"
    deal.item.category = "Tech"
    html = build_html([deal], _ledger([_find("Found Sneaker")]), TODAY)
    assert ">Your list<" in html
    assert "https://img.example.com/mine.jpg" in html
    assert 'href="https://shop.example.com/p"' in html  # winner store link
    assert html.index(">Your list<") < html.index("Headphones") < html.index("Found Sneaker")
    only_find = build_html([], _ledger([_find("Found Sneaker")]), TODAY)
    assert ">Your list<" not in only_find


def test_ledger_strings_are_escaped():
    ledger = _ledger([_find("<script>alert(1)</script>", store="a<b>.com",
                            url="https://x.com/?a=1&b=<2>",
                            image="https://i.com/a.jpg?x=\"y\"")])
    html = build_html([], ledger, TODAY)
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html
    assert "<2>" not in html
    assert 'x="y"' not in html


def test_list_deals_sorted_by_category_with_uncategorised_last():
    deals = [_list_deal("Mystery", category=""), _list_deal("Shoe Deal", category="Shoes"),
             _list_deal("Acc Deal", category="Accessories")]
    sections = select_grid(deals, None, TODAY)
    assert [s["category"] for s in sections] == ["Your list"]
    assert [c["name"] for c in sections[0]["cards"]] == ["Acc Deal", "Shoe Deal", "Mystery"]


def test_your_list_comes_first_uncapped_then_suggestions():
    deals = [_list_deal(f"Mine {i}", category=CATEGORIES[i % 6]) for i in range(20)]
    entries = [_find(f"{cat} Find {i}", category=cat) for cat in CATEGORIES for i in range(6)]
    sections = select_grid(deals, _ledger(entries), TODAY)
    assert sections[0]["category"] == "Your list"
    assert len(sections[0]["cards"]) == 20 and sections[0]["more"] == 0
    assert sum(len(s["cards"]) for s in sections[1:]) == TOTAL
    html = build_html(deals, _ledger(entries), TODAY)
    assert _count_cards(html) == 20 + TOTAL
    assert html.index(">Your list<") < html.index(">Suggestions for you<")
    assert html.index("Mine 19") < html.index("Suggestions for you")
    text = build_text(deals, _ledger(entries), TODAY)
    assert text.index("== Your list ==") < text.index("Suggestions for you")


def test_no_suggestions_heading_without_finds():
    html = build_html([_list_deal("Mine")], None, TODAY)
    assert "Suggestions for you" not in html


def test_subject_counts_deals_plus_eligible_finds():
    ledger = _ledger([_find("A"), _find("B"), _find("C", on_sale=False)])
    subject = build_subject([_deal()], TODAY, ledger)
    assert subject == "\U0001F381 Isaac's Deals — 3 items on sale (2026-11-09)"
    assert build_subject([], TODAY, _ledger([_find("A")])).endswith("1 item on sale (2026-11-09)")


def test_send_accepts_finds_and_passes_to_html_and_text(mocker):
    api_send = mocker.patch("emailer.resend.Emails.send", return_value={"id": "x"})
    mocker.patch.dict("os.environ", {"RESEND_API_KEY": "re_test", "TO_EMAIL": "you@example.com"})
    send(deals=[], today=TODAY, finds=_ledger([_find("Found Sneaker")]))
    payload = api_send.call_args[0][0]
    assert "Found Sneaker" in payload["html"]
    assert "Found Sneaker" in payload["text"]
    assert "1 item on sale" in payload["subject"]


def test_text_mirrors_grid():
    ledger = _ledger([_find("Found Sneaker")])
    text = build_text([_list_deal("Mine Shoe")], ledger, TODAY)
    assert "Shoes" in text
    assert text.index("== Your list ==") < text.index("Mine Shoe") < text.index("Found Sneaker")
    assert "Found Sneaker" in text
    assert "$100.00 -> $50.00" in text
    assert "https://shoestore.com/Found-Sneaker" in text
    assert PAGE_URL in text


def test_empty_state_with_empty_fresh_ledger():
    html = build_html([], _ledger([]), TODAY)
    assert "No deals this week" in html
    assert "No deals" in build_text([], _ledger([]), TODAY)
    assert build_subject([], TODAY, _ledger([])).startswith("No deals found")


def test_email_sets_phone_viewport():
    html = build_html([])
    assert '<meta name="viewport" content="width=device-width,initial-scale=1">' in html


# --- S4c: like / dislike buttons on suggestions ---------------------------------------

def _fb_html(entries=None, deals=None):
    entries = entries if entries is not None else [_find("Fancy Sneaker", url="https://shoestore.com/a?x=1&y=2")]
    return build_html(deals or [_list_deal()], _ledger(entries), TODAY)


def _fb_text(entries=None):
    entries = entries if entries is not None else [_find("Fancy Sneaker", url="https://shoestore.com/a?x=1&y=2")]
    return build_text([_list_deal()], _ledger(entries), TODAY)


def test_find_card_has_feedback_links():
    from emailer import _find_card
    from feedback import vote_link
    entry = _find("Fancy Sneaker")
    card = _find_card(entry)
    assert card["feedback"] == {"like": vote_link("like", entry), "dislike": vote_link("dislike", entry)}


def test_deal_cards_have_no_feedback():
    from emailer import _deal_card
    assert "feedback" not in _deal_card(_list_deal())


def test_html_find_has_vote_links_escaped():
    from emailer import _find_card
    html = _fb_html()
    assert "More like this" in html and "Not for me" in html
    like = _find_card(_find("Fancy Sneaker", url="https://shoestore.com/a?x=1&y=2"))["feedback"]["like"]
    assert f'href="{like.replace("&", "&amp;")}"' in html
    assert f'href="{like}"' not in html or "&" not in like


def test_html_only_find_card_gets_buttons():
    html = _fb_html()
    assert html.count("More like this") == 1
    assert html.count("Not for me") == 1


def test_html_hint_under_suggestions_heading():
    html = _fb_html()
    hint = "opens GitHub"
    assert hint in html
    assert html.index("Suggestions for you") < html.index(hint)


def test_no_finds_no_feedback_in_html_or_text():
    html = build_html([_list_deal()], _ledger([]), TODAY)
    text = build_text([_list_deal()], _ledger([]), TODAY)
    for out in (html, text):
        assert "More like this" not in out and "Not for me" not in out and "opens GitHub" not in out


def test_text_find_has_vote_links_and_hint():
    from emailer import _find_card
    text = _fb_text()
    card = _find_card(_find("Fancy Sneaker", url="https://shoestore.com/a?x=1&y=2"))["feedback"]
    assert f"  More like this: {card['like']}" in text
    assert f"  Not for me: {card['dislike']}" in text
    assert 'opens GitHub — tap "Submit new issue" to send it.' in text
    assert text.index("Suggestions for you") < text.index("opens GitHub")


def test_text_deal_has_no_vote_lines():
    text = build_text([_list_deal()], _ledger([]), TODAY)
    assert "More like this" not in text
