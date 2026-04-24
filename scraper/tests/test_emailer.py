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
    price = PriceResult(current_price=149.0, sale_detected=False)
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
        price_result=PriceResult(current_price=149.0, sale_detected=False),
        promos=winner_promos or [],
        deal_types=[DealType.PRICE_DROP],
    )
    ev2 = StoreEvaluation(
        store=store2,
        price_result=PriceResult(current_price=189.0, sale_detected=False),
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
