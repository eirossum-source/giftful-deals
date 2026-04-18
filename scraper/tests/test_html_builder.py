from datetime import date, datetime

from bs4 import BeautifulSoup

from coupon_checker import PromoCode
from filter import Deal, DealType
from giftful import Item
from html_builder import render
from price_checker import PriceResult


NOW = datetime(2026, 4, 18, 7, 0, 0)


def _deal(
    name="Wireless Headphones",
    url="https://shop.example.com/products/headphones",
    listed=199.0,
    current=149.0,
    sale=False,
    promos=None,
    types=None,
):
    item = Item(name=name, url=url, listed_price=listed, image_url="")
    price = PriceResult(current_price=current, sale_detected=sale)
    return Deal(
        item=item,
        price_result=price,
        promos=promos or [],
        deal_types=types or [DealType.PRICE_DROP],
    )


def test_renders_one_deal_card():
    html = render([_deal()], generated_at=NOW)
    soup = BeautifulSoup(html, "lxml")

    cards = soup.select(".deal-card")
    assert len(cards) == 1
    assert "Wireless Headphones" in cards[0].get_text()
    assert cards[0].select_one("a")["href"] == (
        "https://shop.example.com/products/headphones"
    )
    assert cards[0].select_one("a")["target"] == "_blank"


def test_renders_multiple_cards_with_unique_domains():
    deals = [
        _deal(name="A", url="https://shop.example.com/a"),
        _deal(name="B", url="https://store.example.net/b"),
        _deal(name="C", url="https://shop.example.com/c"),
    ]
    html = render(deals, generated_at=NOW)
    soup = BeautifulSoup(html, "lxml")

    assert len(soup.select(".deal-card")) == 3
    store_buttons = soup.select("[data-filter-store]")
    store_values = {b["data-filter-store"] for b in store_buttons}
    # "all" plus two unique domains
    assert "all" in store_values
    assert "shop.example.com" in store_values
    assert "store.example.net" in store_values


def test_renders_deal_type_filter_buttons():
    html = render([_deal()], generated_at=NOW)
    soup = BeautifulSoup(html, "lxml")
    types = {b["data-filter-type"] for b in soup.select("[data-filter-type]")}
    assert {"all", "price_drop", "sale", "promo"} <= types


def test_renders_price_drop_badge():
    html = render([_deal(listed=200, current=150)], generated_at=NOW)
    soup = BeautifulSoup(html, "lxml")
    badge = soup.select_one(".deal-card .badge-drop")
    assert badge is not None
    assert "25%" in badge.get_text()


def test_renders_sale_badge():
    deal = _deal(sale=True, types=[DealType.SALE])
    html = render([deal], generated_at=NOW)
    soup = BeautifulSoup(html, "lxml")
    assert soup.select_one(".deal-card .badge-sale") is not None


def test_renders_promo_code_chips_with_copy_handler():
    promo = [PromoCode(code="SAVE20", description="20% off", expiry=date(2099, 1, 1))]
    deal = _deal(promos=promo, types=[DealType.PROMO])
    html = render([deal], generated_at=NOW)
    soup = BeautifulSoup(html, "lxml")

    chip = soup.select_one(".deal-card .promo-chip")
    assert chip is not None
    assert "SAVE20" in chip.get_text()
    # Copy hook is declarative; JS handler attaches via event delegation
    assert chip["data-code"] == "SAVE20"


def test_empty_state_rendered_when_zero_deals():
    html = render([], generated_at=NOW)
    soup = BeautifulSoup(html, "lxml")
    empty = soup.select_one(".empty-state")
    assert empty is not None
    assert "No deals this week" in empty.get_text()
    assert "2026-04-18" in html


def test_title_and_timestamp_present():
    html = render([_deal()], generated_at=NOW)
    assert "Isaac's Deals" in html
    assert "2026-04-18" in html


def test_accent_color_and_system_font():
    html = render([_deal()], generated_at=NOW)
    assert "#0f7a4a" in html
    assert "-apple-system" in html or "system-ui" in html


def test_vanilla_js_filter_and_clipboard_hooks():
    promo = [PromoCode(code="X", description="", expiry=date(2099, 1, 1))]
    deal = _deal(promos=promo, types=[DealType.PROMO])
    html = render([deal], generated_at=NOW)
    assert "<script>" in html
    assert "data-filter-type" in html
    assert "data-filter-store" in html
    assert "navigator.clipboard" in html
    assert "Copied" in html


def test_placeholder_image_used_when_missing():
    deal = _deal()
    html = render([deal], generated_at=NOW)
    soup = BeautifulSoup(html, "lxml")
    img = soup.select_one(".deal-card img")
    assert img is not None
    assert img.get("src")  # non-empty placeholder
