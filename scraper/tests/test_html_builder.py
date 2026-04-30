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
    promos=None,
    types=None,
):
    item = Item(name=name, url=url, listed_price=listed, image_url="")
    price = PriceResult(current_price=current)
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


def _store_options(html: str) -> set:
    soup = BeautifulSoup(html, "lxml")
    sel = soup.select_one("[data-filter-store]")
    return {opt.get("value") for opt in sel.select("option")} if sel else set()


def _type_options(html: str) -> set:
    soup = BeautifulSoup(html, "lxml")
    sel = soup.select_one("[data-filter-type]")
    return {opt.get("value") for opt in sel.select("option")} if sel else set()


def test_renders_multiple_cards_with_unique_domains():
    deals = [
        _deal(name="A", url="https://shop.example.com/a"),
        _deal(name="B", url="https://store.example.net/b"),
        _deal(name="C", url="https://shop.example.com/c"),
    ]
    html = render(deals, generated_at=NOW)
    soup = BeautifulSoup(html, "lxml")

    assert len(soup.select(".deal-card")) == 3
    store_values = _store_options(html)
    assert "all" in store_values
    assert "shop.example.com" in store_values
    assert "store.example.net" in store_values


def test_renders_deal_type_filter_options():
    promo = [PromoCode(code="X", description="", expiry=date(2099, 1, 1))]
    deal = _deal(promos=promo, types=[DealType.PRICE_DROP, DealType.PROMO])
    html = render([deal], generated_at=NOW)
    types = _type_options(html)
    assert "all" in types
    assert "price_drop" in types
    assert "promo" in types


def test_filter_bar_hides_promo_when_no_promos():
    html = render([_deal()], generated_at=NOW)
    types = _type_options(html)
    assert "promo" not in types
    assert "all" in types
    assert "price_drop" in types


def test_filter_bar_shows_promo_when_a_deal_has_promo():
    promo = [PromoCode(code="SAVE10", description="", expiry=date(2099, 1, 1))]
    deal = _deal(promos=promo, types=[DealType.PROMO])
    html = render([deal], generated_at=NOW)
    assert "promo" in _type_options(html)


def test_filter_bar_shows_promo_for_multi_store_deal_with_promo():
    promo = [PromoCode(code="AMZN10", description="", expiry=date(2099, 1, 1))]
    item = Item(name="Widget", listed_price=200.0, image_url="")
    ev1 = _store_eval("https://amazon.com/p", "Amazon", 200.0, 149.0, promos=promo)
    ev2 = _store_eval("https://bestbuy.com/p", "Best Buy", 200.0, 169.0)
    deal = Deal(item=item, store_evaluations=[ev1, ev2])
    html_out = render([deal], generated_at=NOW)
    assert "promo" in _type_options(html_out)


def test_filter_bar_shows_back_in_stock_when_a_deal_has_it():
    deal = _deal(types=[DealType.BACK_IN_STOCK])
    html_out = render([deal], generated_at=NOW)
    assert "back_in_stock" in _type_options(html_out)


def test_renders_price_drop_badge():
    html = render([_deal(listed=200, current=150)], generated_at=NOW)
    soup = BeautifulSoup(html, "lxml")
    badge = soup.select_one(".deal-card .badge-drop")
    assert badge is not None
    assert "25%" in badge.get_text()


def test_renders_back_in_stock_badge():
    deal = _deal(types=[DealType.BACK_IN_STOCK])
    html = render([deal], generated_at=NOW)
    soup = BeautifulSoup(html, "lxml")
    assert soup.select_one(".deal-card .badge-stock") is not None


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
    # Timestamp shown in Eastern Time
    assert "ET" in empty.get_text()


def test_header_renders_giftful_wordmark_image_and_tagline():
    html_out = render([_deal()], generated_at=NOW)
    soup = BeautifulSoup(html_out, "lxml")
    header = soup.select_one("header.site")
    assert header is not None
    # Real giftful wordmark as PNG (embedded alongside index.html)
    logo = header.select_one("img.brand-mark")
    assert logo is not None
    assert logo.get("src") == "giftful_logo.png"
    assert "giftful" in (logo.get("alt") or "").lower()
    # Tagline beneath the wordmark
    tagline = header.select_one(".brand-tagline")
    assert tagline is not None
    assert "today" in tagline.get_text().lower()
    # ET timestamp still shown in meta
    assert "ET" in html_out


def test_header_is_centered():
    html_out = render([_deal()], generated_at=NOW)
    # Centered column layout on header.site
    assert "header.site" in html_out
    # Centering signals: flex column + text-align center
    assert "flex-direction:column" in html_out
    assert "text-align:center" in html_out


def test_dark_theme_in_css():
    html = render([_deal()], generated_at=NOW)
    assert "color-scheme" in html
    assert "background:#0e0f10" in html or "--bg:#0e0f10" in html


def test_giftful_link_in_header():
    html_out = render([_deal()], generated_at=NOW)
    soup = BeautifulSoup(html_out, "lxml")
    header = soup.select_one("header.site")
    assert header is not None
    # The wordmark image is now the link to the giftful list
    link = header.select_one("a[href*='giftful.com']")
    assert link is not None
    assert link.select_one("img.brand-mark") is not None


def test_rerun_workflow_link_in_footer():
    html = render([_deal()], generated_at=NOW)
    soup = BeautifulSoup(html, "lxml")
    footer = soup.select_one("footer.site")
    assert footer is not None
    link = footer.select_one("a[href*='actions']")
    assert link is not None
    assert "github.com" in link["href"]


def test_vanilla_js_filter_and_clipboard_hooks():
    promo = [PromoCode(code="X", description="", expiry=date(2099, 1, 1))]
    deal = _deal(promos=promo, types=[DealType.PROMO])
    html = render([deal], generated_at=NOW)
    assert "<script>" in html
    assert "data-filter-type" in html
    assert "data-filter-store" in html
    assert "navigator.clipboard" in html
    assert "Copied" in html


def test_category_grouping_renders_section_per_category():
    item_a = Item(name="A", url="https://shop.example.com/a", listed_price=100.0, image_url="", category="Tech")
    item_b = Item(name="B", url="https://shop.example.com/b", listed_price=50.0, image_url="", category="Athleisure")
    deal_a = Deal(item=item_a, price_result=PriceResult(current_price=80.0), promos=[], deal_types=[DealType.PRICE_DROP])
    deal_b = Deal(item=item_b, price_result=PriceResult(current_price=40.0), promos=[], deal_types=[DealType.PRICE_DROP])
    html_out = render([deal_a, deal_b], generated_at=NOW)
    soup = BeautifulSoup(html_out, "lxml")
    sections = soup.select(".category-group")
    assert len(sections) == 2
    headings = {s.select_one(".category-heading").get_text(strip=True) for s in sections}
    assert headings == {"Tech", "Athleisure"}


def test_price_unavailable_shows_listed_price_without_strikethrough():
    item = Item(name="Widget", url="https://shop.example.com/w", listed_price=199.0, image_url="")
    price = PriceResult(current_price=None)
    deal = Deal(item=item, price_result=price, promos=[], deal_types=[DealType.BACK_IN_STOCK])
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
    price = PriceResult(current_price=current)
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


def test_card_shows_retailer_strikethrough_when_higher_than_giftful_listed():
    # When retailer reports a higher list price than giftful, show the
    # retailer's list as the strikethrough so the savings reflect the
    # retailer-side sale (e.g. Amazon $99.99 -> $59.99 with giftful at $59.99).
    item = Item(
        name="Ring Battery Doorbell",
        url="https://www.amazon.com/dp/B0BZWRSRWV",
        listed_price=59.99,
        image_url="",
    )
    price = PriceResult(current_price=59.99, list_price=99.99)
    deal = Deal(item=item, price_result=price, promos=[], deal_types=[DealType.PRICE_DROP])
    html_out = render([deal], generated_at=NOW)
    soup = BeautifulSoup(html_out, "lxml")
    card = soup.select_one(".deal-card")
    listed = card.select_one(".price-listed")
    current = card.select_one(".price-current")
    assert listed is not None
    assert "$99.99" in listed.get_text()
    assert "$59.99" in current.get_text()
    # 40% discount badge expected
    badge = card.select_one(".badge-drop")
    assert badge is not None
    assert "40%" in badge.get_text()


def test_review_section_links_to_category_url_when_present():
    item = Item(
        name="Beats Powerbeats Pro 2",
        url="https://www.amazon.com/dp/B0DT2344N3?tag=giftful04-20",
        listed_price=199.0,
        image_url="",
        category="Tech",
        category_url="https://giftful.com/wishlists/tech",
    )
    review_items = [{"item": item, "reasons": ["product name mismatch (score 0.00)"]}]
    html_out = render([_deal()], generated_at=NOW, review_items=review_items)
    soup = BeautifulSoup(html_out, "lxml")

    row = soup.select_one(".review-section .review-row")
    assert row is not None
    link = row.select_one("a")
    assert link["href"] == "https://giftful.com/wishlists/tech"
    assert link["target"] == "_blank"
    assert "Beats Powerbeats Pro 2" in link.get_text()


def test_review_section_falls_back_to_item_url_when_no_category_url():
    item = Item(
        name="Some Item",
        url="https://retailer.example.com/x",
        listed_price=50.0,
        image_url="",
    )
    review_items = [{"item": item, "reasons": ["dead link (404)"]}]
    html_out = render([_deal()], generated_at=NOW, review_items=review_items)
    soup = BeautifulSoup(html_out, "lxml")

    link = soup.select_one(".review-section .review-row a")
    assert link["href"] == "https://retailer.example.com/x"


def test_review_section_shows_origin_retailer_domain():
    item = Item(
        name="Tom Ford FT5737-B",
        url="https://www.smartbuyglasses.com/designer-eyeglasses/Tom-Ford/FT5737.html",
        listed_price=300.0,
        image_url="",
        category_url="https://giftful.com/wishlists/eyewear",
    )
    review_items = [{"item": item, "reasons": ["product name mismatch (score 0.00)"]}]
    html_out = render([_deal()], generated_at=NOW, review_items=review_items)
    soup = BeautifulSoup(html_out, "lxml")

    origin = soup.select_one(".review-section .review-origin")
    assert origin is not None
    assert "smartbuyglasses.com" in origin.get_text()


def test_filter_bar_includes_all_store_domains_from_multi_store():
    deal = _multi_deal()
    html_out = render([deal], generated_at=NOW)
    store_values = _store_options(html_out)
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
