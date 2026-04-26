from datetime import date, datetime

from bs4 import BeautifulSoup

from coupon_checker import PromoCode
from filter import Deal, DealType, StoreEvaluation
from giftful import Item, StoreLink
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
    promo = [PromoCode(code="X", description="", expiry=date(2099, 1, 1))]
    deal = _deal(promos=promo, types=[DealType.PRICE_DROP, DealType.PROMO])
    html = render([deal], generated_at=NOW)
    soup = BeautifulSoup(html, "lxml")
    types = {b["data-filter-type"] for b in soup.select("[data-filter-type]")}
    assert {"all", "price_drop", "sale", "promo"} <= types


def test_filter_bar_hides_promo_when_no_promos():
    # No deal in this set has DealType.PROMO; the Promo Code filter button
    # should be omitted to avoid an empty-result filter.
    html = render([_deal()], generated_at=NOW)
    soup = BeautifulSoup(html, "lxml")
    types = {b["data-filter-type"] for b in soup.select("[data-filter-type]")}
    assert "promo" not in types
    assert {"all", "price_drop", "sale"} <= types


def test_filter_bar_shows_promo_when_a_deal_has_promo():
    promo = [PromoCode(code="SAVE10", description="", expiry=date(2099, 1, 1))]
    deal = _deal(promos=promo, types=[DealType.PROMO])
    html = render([deal], generated_at=NOW)
    soup = BeautifulSoup(html, "lxml")
    types = {b["data-filter-type"] for b in soup.select("[data-filter-type]")}
    assert "promo" in types


def test_filter_bar_shows_promo_for_multi_store_deal_with_promo():
    promo = [PromoCode(code="AMZN10", description="", expiry=date(2099, 1, 1))]
    item = Item(name="Widget", listed_price=200.0, image_url="")
    ev1 = _store_eval("https://amazon.com/p", "Amazon", 200.0, 149.0, promos=promo)
    ev2 = _store_eval("https://bestbuy.com/p", "Best Buy", 200.0, 169.0)
    deal = Deal(item=item, store_evaluations=[ev1, ev2])
    html_out = render([deal], generated_at=NOW)
    soup = BeautifulSoup(html_out, "lxml")
    types = {b["data-filter-type"] for b in soup.select("[data-filter-type]")}
    assert "promo" in types


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


def test_price_unavailable_shows_listed_price_without_strikethrough():
    item = Item(name="Widget", url="https://shop.example.com/w", listed_price=199.0, image_url="")
    price = PriceResult(current_price=None, sale_detected=True)
    deal = Deal(item=item, price_result=price, promos=[], deal_types=[DealType.SALE])
    html_out = render([deal], generated_at=NOW)
    soup = BeautifulSoup(html_out, "lxml")
    card = soup.select_one(".deal-card")
    block = card.select_one(".price-block")
    # No strikethrough listed-price, no "unavailable" message
    assert block.select_one(".price-listed") is None
    assert block.select_one(".price-unavailable") is None
    # Listed price shown as the current price
    current = block.select_one(".price-current")
    assert current is not None
    assert "$199" in current.get_text()


def test_placeholder_image_used_when_missing():
    deal = _deal()
    html = render([deal], generated_at=NOW)
    soup = BeautifulSoup(html, "lxml")
    img = soup.select_one(".deal-card img")
    assert img is not None
    assert img.get("src")  # non-empty placeholder


# --- Slice D: multi-store card rendering ---


def _store_eval(url, display_name, listed, current, promos=None):
    store = StoreLink(url=url, display_name=display_name, listed_price=listed)
    price = PriceResult(current_price=current, sale_detected=False)
    types = []
    if current < listed:
        types.append(DealType.PRICE_DROP)
    if promos:
        types.append(DealType.PROMO)
    return StoreEvaluation(store=store, price_result=price, promos=promos or [], deal_types=types)


def _multi_deal(name="Widget", image_url=""):
    item = Item(name=name, listed_price=200.0, image_url=image_url)
    ev1 = _store_eval("https://amazon.com/p/widget", "Amazon", 200.0, 149.0)
    ev2 = _store_eval("https://bestbuy.com/p/widget", "Best Buy", 200.0, 169.0)
    return Deal(item=item, store_evaluations=[ev1, ev2])


def test_multi_store_card_shows_winner_section():
    deal = _multi_deal()
    html_out = render([deal], generated_at=NOW)
    soup = BeautifulSoup(html_out, "lxml")
    card = soup.select_one(".deal-card")
    winner_section = card.select_one(".store-winner")
    assert winner_section is not None
    assert "Amazon" in winner_section.get_text()


def test_multi_store_card_shows_secondary_stores():
    deal = _multi_deal()
    html_out = render([deal], generated_at=NOW)
    soup = BeautifulSoup(html_out, "lxml")
    card = soup.select_one(".deal-card")
    secondary = card.select(".store-alt")
    assert len(secondary) == 1
    assert "Best Buy" in secondary[0].get_text()


def test_multi_store_card_winner_link_is_shop_url():
    deal = _multi_deal()
    html_out = render([deal], generated_at=NOW)
    soup = BeautifulSoup(html_out, "lxml")
    card = soup.select_one(".deal-card")
    link = card.select_one("a")
    assert "amazon.com" in link["href"]


def test_multi_store_card_data_store_includes_all_domains():
    deal = _multi_deal()
    html_out = render([deal], generated_at=NOW)
    soup = BeautifulSoup(html_out, "lxml")
    card = soup.select_one(".deal-card")
    domains = card["data-store"].split()
    assert "amazon.com" in domains
    assert "bestbuy.com" in domains


def test_filter_bar_includes_all_store_domains_from_multi_store():
    deal = _multi_deal()
    html_out = render([deal], generated_at=NOW)
    soup = BeautifulSoup(html_out, "lxml")
    store_buttons = soup.select("[data-filter-store]")
    store_values = {b["data-filter-store"] for b in store_buttons}
    assert "amazon.com" in store_values
    assert "bestbuy.com" in store_values


def test_multi_store_winner_promos_in_winner_section():
    promo = [PromoCode(code="AMZN10", description="10% off", expiry=date(2099, 1, 1))]
    item = Item(name="Widget", listed_price=200.0, image_url="")
    ev1 = _store_eval("https://amazon.com/p/w", "Amazon", 200.0, 149.0, promos=promo)
    ev2 = _store_eval("https://bestbuy.com/p/w", "Best Buy", 200.0, 169.0)
    deal = Deal(item=item, store_evaluations=[ev1, ev2])
    html_out = render([deal], generated_at=NOW)
    soup = BeautifulSoup(html_out, "lxml")
    card = soup.select_one(".deal-card")
    winner_section = card.select_one(".store-winner")
    chip = winner_section.select_one(".promo-chip")
    assert chip is not None
    assert chip["data-code"] == "AMZN10"
