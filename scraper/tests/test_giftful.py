from unittest.mock import MagicMock

import pytest

from giftful import (
    Category,
    GiftfulEmptyListError,
    Item,
    StoreLink,
    parse_categories,
    parse_items,
    parse_modal,
    resolve_redirect,
)


# ---------- StoreLink ----------


def test_storelink_exposes_url_display_name_listed_price():
    s = StoreLink(
        url="https://shop.example/p",
        display_name="shop.example",
        listed_price=12.5,
    )
    assert s.url == "https://shop.example/p"
    assert s.display_name == "shop.example"
    assert s.listed_price == 12.5


def test_storelink_domain_extracts_from_url():
    s = StoreLink(
        url="https://www.example.com/product/123",
        display_name="example",
        listed_price=10.0,
    )
    assert s.domain == "www.example.com"


# ---------- Category ----------


def test_category_exposes_name_url_item_count():
    c = Category(
        name="Accessories",
        url="https://giftful.com/wishlists/abc",
        item_count=12,
    )
    assert c.name == "Accessories"
    assert c.url == "https://giftful.com/wishlists/abc"
    assert c.item_count == 12


# ---------- Item (legacy + new shape) ----------


def test_item_accepts_legacy_url_kwarg():
    item = Item(
        name="Thing",
        url="https://shop.example.com/thing",
        listed_price=10.0,
        image_url="i.jpg",
    )
    assert item.name == "Thing"
    assert item.url == "https://shop.example.com/thing"
    assert item.domain == "shop.example.com"
    assert item.listed_price == 10.0
    assert item.image_url == "i.jpg"


def test_item_url_falls_back_to_first_store_when_legacy_empty():
    stores = [
        StoreLink(url="https://a.com/p", display_name="a", listed_price=10.0),
        StoreLink(url="https://b.com/p", display_name="b", listed_price=11.0),
    ]
    item = Item(name="X", listed_price=10.0, store_urls=stores)
    assert item.url == "https://a.com/p"
    assert item.domain == "a.com"


def test_item_domain_works_for_legacy_and_new_construction():
    legacy = Item(name="L", url="https://legacy.com/p", listed_price=1.0)
    new = Item(
        name="N",
        listed_price=1.0,
        store_urls=[StoreLink("https://new.com/p", "new.com", 1.0)],
    )
    assert legacy.domain == "legacy.com"
    assert new.domain == "new.com"


# ---------- parse_categories ----------


def test_parse_categories_extracts_three_entries_with_name_and_count(read_fixture):
    html = read_fixture("giftful_profile.html")
    cats = parse_categories(html, base_url="https://giftful.com/isaacrossum")

    assert [c.name for c in cats] == ["Athleisure", "Accessories", "Tech"]
    assert [c.item_count for c in cats] == [25, 12, 3]


def test_parse_categories_resolves_relative_hrefs_against_base_url(read_fixture):
    html = read_fixture("giftful_profile.html")
    cats = parse_categories(html, base_url="https://giftful.com/isaacrossum")

    assert cats[0].url == "https://giftful.com/wishlists/iU4fssUTAYgfsXJZunIs"
    assert cats[1].url == "https://giftful.com/wishlists/QBJFkBAfyvWxRFlpEKGU"
    assert cats[2].url == "https://giftful.com/wishlists/I20ImZMQzD2YbLcexYYW"


def test_parse_categories_on_empty_html_returns_empty_list():
    assert parse_categories("", base_url="https://giftful.com/x") == []
    assert parse_categories(
        "<html><body></body></html>", base_url="https://giftful.com/x"
    ) == []


# ---------- parse_items ----------


def test_parse_items_extracts_three_items_with_name_price_image(read_fixture):
    html = read_fixture("giftful_category.html")
    items = parse_items(html)

    assert len(items) == 3
    assert items[0].name == "Nike Club washed shorts in brown"
    assert items[0].listed_price == 65.0
    assert items[0].image_url == "https://cdn.example.test/items/shorts-light.jpg"
    assert items[1].name == "Museum Classic Watch"
    assert items[2].name == "Good Quality Human Cap"
    assert items[2].listed_price == 45.0


def test_parse_items_handles_missing_brand_icon(read_fixture):
    html = read_fixture("giftful_category.html")
    items = parse_items(html)

    # 3rd fixture item intentionally has no <img alt="Brand Icon"> — parser
    # must still succeed and keep the item in the list.
    assert items[2].name == "Good Quality Human Cap"


def test_parse_items_handles_comma_in_price(read_fixture):
    html = read_fixture("giftful_category.html")
    items = parse_items(html)

    # "$1,095" must parse to 1095.0 (not 1.095 or raise)
    assert items[1].listed_price == 1095.0


def test_parse_items_sets_category_name_when_provided(read_fixture):
    html = read_fixture("giftful_category.html")
    items = parse_items(html, category_name="Accessories")

    assert all(i.category == "Accessories" for i in items)


def test_parse_items_skips_claimed_items(read_fixture):
    html = read_fixture("giftful_category_claimed.html")
    items = parse_items(html)

    assert len(items) == 2
    names = [i.name for i in items]
    assert "Nike Club washed shorts in brown" in names
    assert "Good Quality Human Cap" in names
    assert "Nike Tech Fleece Hoodie" not in names


def test_parse_items_all_claimed_returns_empty():
    html = """
    <div>
      <button type="button">
        <div>
          <img alt="Feature Image" src="x.jpg" />
          <div style="position: absolute;"><img alt="Claimed" src="/images/claimed.jpg" /></div>
        </div>
        <div class="ml-1 mt-2">
          <div class="leading-5 text-sm">Already Bought Item</div>
          <div class="text-sm flex items-center"><div>$50</div></div>
        </div>
      </button>
    </div>
    """
    assert parse_items(html) == []


def test_parse_items_on_empty_html_returns_empty_list():
    assert parse_items("") == []
    assert parse_items("<html><body></body></html>") == []


# ---------- parse_modal ----------


def test_parse_modal_extracts_item_name_and_listed_price(read_fixture):
    html = read_fixture("giftful_item_modal.html")
    name, listed_price, _url = parse_modal(html)

    assert name == "Nike Club washed shorts in brown"
    assert listed_price == 65.0


def test_parse_modal_extracts_view_online_url(read_fixture):
    html = read_fixture("giftful_item_modal.html")
    _name, _price, view_online_url = parse_modal(html)

    assert view_online_url is not None
    assert "skimresources.com" in view_online_url


def test_parse_modal_ignores_retailer_cards(read_fixture):
    html = read_fixture("giftful_item_modal.html")
    _name, _price, view_online_url = parse_modal(html)

    assert isinstance(view_online_url, str)


def test_parse_modal_returns_none_url_when_no_btn_submit():
    html = """
    <div role="dialog">
      <h3>Some Item</h3>
      <div class="text-xl"><div>$20</div></div>
      <a href="https://example.com"><div class="flex-1">example.com</div><div>$20</div></a>
    </div>
    """
    _name, _price, view_online_url = parse_modal(html)
    assert view_online_url is None


def test_parse_modal_on_empty_html_returns_none_none_none():
    name, listed_price, view_online_url = parse_modal("")
    assert name is None
    assert listed_price is None
    assert view_online_url is None


# ---------- resolve_redirect (preserved) ----------


def test_resolve_redirect_follows_final_url():
    session = MagicMock()
    response = MagicMock()
    response.url = "https://final.example.com/product/123"
    session.head.return_value = response

    assert (
        resolve_redirect("https://bit.ly/xyz", session)
        == "https://final.example.com/product/123"
    )
    session.head.assert_called_once_with(
        "https://bit.ly/xyz", allow_redirects=True, timeout=15
    )


def test_resolve_redirect_returns_original_on_failure():
    session = MagicMock()
    session.head.side_effect = Exception("network")

    assert (
        resolve_redirect("https://bit.ly/xyz", session) == "https://bit.ly/xyz"
    )


# ---------- GiftfulEmptyListError ----------


def test_giftful_empty_list_error_can_be_raised():
    with pytest.raises(GiftfulEmptyListError, match="no items"):
        raise GiftfulEmptyListError("no items")
