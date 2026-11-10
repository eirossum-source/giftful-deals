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


# --- S4b: finds on the page, grouped by category -------------------------------------

TODAY = date(2026, 11, 9)


def _find(name="Sale Tee", category="Casual", cur=20.0, lst=40.0, store="Shop.Example.com",
          url=None, image_url="https://shop.example.com/img.jpg", on_sale=True):
    return {
        "url": url or f"https://shop.example.com/p/{name.replace(' ', '-')}",
        "name": name, "store": store, "category": category,
        "image_url": image_url, "current_price": cur, "list_price": lst, "on_sale": on_sale,
    }


def _ledger(*entries, checked_at="2026-11-09"):
    return {"checked_at": checked_at, "items": {e["url"]: e for e in entries}, "dropped": []}


def _render_f(deals, ledger, today=TODAY):
    return render(deals, generated_at=NOW, finds=ledger, today=today)


def test_stale_ledger_or_no_today_renders_same_as_no_finds():
    deals = [_deal()]
    base = render(deals, generated_at=NOW)
    stale = _render_f(deals, _ledger(_find(), checked_at="2026-11-02"))
    no_today = _render_f(deals, _ledger(_find()), today=None)
    assert stale == base
    assert no_today == base


def test_only_confirmed_on_sale_finds_with_known_category_render():
    ledger = _ledger(
        _find("Good Tee"),
        _find("Off Sale Tee", on_sale=False),
        _find("Not Cheaper", cur=40.0, lst=40.0),
        _find("Bad Category", category="Hats"),
    )
    html = _render_f([_deal()], ledger)
    text = BeautifulSoup(html, "lxml").get_text()
    assert "Good Tee" in text
    assert "Off Sale Tee" not in text
    assert "Not Cheaper" not in text
    assert "Bad Category" not in text


def test_section_headings_only_when_finds_exist_and_list_first():
    plain = BeautifulSoup(render([_deal()], generated_at=NOW), "lxml")
    assert not plain.select(".section-title")

    soup = BeautifulSoup(_render_f([_deal()], _ledger(_find())), "lxml")
    titles = [t.get_text(strip=True) for t in soup.select(".section-title")]
    assert titles == ["Your list", "Suggestions for you"]
    assert len(soup.select(".section-block")) == 2
    names = [h.get_text(strip=True) for h in soup.select(".deal-name")]
    assert names == ["Wireless Headphones", "Sale Tee"]


def test_suggestions_grouped_by_categories_order_biggest_discount_first_no_cap():
    finds = [_find(f"Tech {i}", category="Tech", cur=40.0 - i, lst=50.0) for i in range(7)]
    finds += [
        _find("Shoe A", category="Shoes", cur=45.0, lst=50.0),
        _find("Acc Small", category="Accessories", cur=45.0, lst=50.0),
        _find("Acc Big", category="Accessories", cur=10.0, lst=50.0),
    ]
    soup = BeautifulSoup(_render_f([], _ledger(*finds)), "lxml")
    groups = soup.select(".category-group")
    assert [g["data-category"] for g in groups] == ["Accessories", "Shoes", "Tech"]
    acc = [h.get_text(strip=True) for h in groups[0].select(".deal-name")]
    assert acc == ["Acc Big", "Acc Small"]
    tech = [h.get_text(strip=True) for h in groups[2].select(".deal-name")]
    assert len(tech) == 7
    assert tech[0] == "Tech 6"


def test_find_card_contents():
    soup = BeautifulSoup(_render_f([], _ledger(_find("Sale Tee", cur=20.0, lst=40.0))), "lxml")
    card = soup.select_one(".deal-card")
    assert card["data-types"] == "price_drop"
    assert card["data-store"] == "shop.example.com"
    assert card.select_one("img")["src"] == "https://shop.example.com/img.jpg"
    link = card.select_one("a")
    assert link["href"] == "https://shop.example.com/p/Sale-Tee"
    assert link["target"] == "_blank"
    assert card.select_one(".deal-name").get_text(strip=True) == "Sale Tee"
    assert card.select_one(".price-listed").get_text() == "$40.00"
    assert card.select_one(".price-current").get_text() == "$20.00"
    assert card.select_one(".badge-drop").get_text() == "-50%"
    assert "price drop" in card.select_one(".tags").get_text()
    assert card.select_one(".store").get_text() == "Shop.Example.com"
    assert "Your list" not in card.get_text()


def test_find_card_without_image_uses_placeholder():
    from html_builder import _find_card_html, PLACEHOLDER_SVG
    html = _find_card_html(_find(image_url=""))
    assert PLACEHOLDER_SVG in html


def test_find_card_escapes_script_in_name_url_store():
    evil = "<script>alert(1)</script>"
    ledger = _ledger(_find(name=evil, store=evil, url='https://x.example/?a="><script>alert(2)</script>'))
    html = _render_f([], ledger)
    assert "<script>alert" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_store_filter_includes_find_stores_deduped_lowercased():
    ledger = _ledger(_find("A", store="Other.Store.com"), _find("B", store="shop.example.com"))
    html = _render_f([_deal()], ledger)
    assert _store_options(html) == {"all", "shop.example.com", "other.store.com"}


def test_no_deals_with_finds_shows_suggestions_without_empty_state():
    soup = BeautifulSoup(_render_f([], _ledger(_find())), "lxml")
    assert not soup.select(".empty-state")
    assert [t.get_text(strip=True) for t in soup.select(".section-title")] == ["Suggestions for you"]
    assert soup.select_one("[data-filter-store]") is not None
    assert len(soup.select(".deal-card")) == 1


def test_no_deals_and_no_finds_still_shows_empty_state():
    soup = BeautifulSoup(_render_f([], _ledger(_find(on_sale=False))), "lxml")
    assert soup.select_one(".empty-state") is not None
    assert not soup.select(".section-title")


def test_js_hides_empty_section_blocks():
    html = _render_f([_deal()], _ledger(_find()))
    assert ".section-block" in html


# --- S4c: like / dislike buttons on suggestions ---------------------------------------

def test_find_card_has_vote_buttons_escaped():
    from feedback import vote_link
    entry = _find("Fancy Tee", url="https://shop.example.com/p?a=1&b=2")
    html = _render_f([_deal()], _ledger(entry))
    soup = BeautifulSoup(html, "html.parser")
    fb = soup.select("div.feedback")
    assert len(fb) == 1
    like = fb[0].select_one("a.vote.vote-like")
    dislike = fb[0].select_one("a.vote.vote-dislike")
    assert like["href"] == vote_link("like", entry)
    assert dislike["href"] == vote_link("dislike", entry)
    assert like["aria-label"] == "More like this" and dislike["aria-label"] == "Not for me"
    assert like["target"] == "_blank" and like["rel"] == ["noopener", "noreferrer"]
    assert like.get_text() == "\U0001F44D" and dislike.get_text() == "\U0001F44E"
    assert like["title"] == "More like this" and dislike["title"] == "Not for me"
    assert "&amp;" in html and 'href="' + vote_link("like", entry) + '"' not in html


def test_feedback_comes_after_store_line():
    html = _render_f([_deal()], _ledger(_find()))
    assert html.index('class="store"') < html.index('class="feedback"')


def test_deal_cards_have_no_vote_buttons():
    soup = BeautifulSoup(render([_deal()], generated_at=NOW), "html.parser")
    assert not soup.select("div.feedback")
    assert "vote-like" not in soup.get_text()


def test_section_hint_under_suggestions_title():
    soup = BeautifulSoup(_render_f([_deal()], _ledger(_find())), "html.parser")
    title = soup.find("h2", class_="section-title", string="Suggestions for you")
    hint = title.find_next_sibling("p")
    assert "section-hint" in hint["class"]
    assert 'opens GitHub — tap "Submit new issue" to send it.' in hint.get_text()


def test_no_finds_no_hint_or_buttons():
    html = render([_deal()], generated_at=NOW)
    body = html.split("</style>", 1)[1]
    assert 'class="feedback"' not in body and "section-hint" not in body


def test_vote_css_present():
    html = _render_f([_deal()], _ledger(_find()))
    assert ".feedback" in html and ".vote" in html and ".section-hint" in html
