from unittest.mock import MagicMock

import pytest

from giftful import GiftfulEmptyListError, Item, parse_items, resolve_redirect


def test_parses_items_from_fixture(read_fixture):
    html = read_fixture("giftful_page.html")

    items = parse_items(html)

    assert len(items) == 3
    assert items[0] == Item(
        name="Wireless Headphones",
        url="https://shop.example.com/products/headphones",
        listed_price=199.00,
        image_url="https://cdn.example.com/img/headphones.jpg",
    )
    assert items[1].name == "Burr Coffee Grinder"
    assert items[1].listed_price == 249.99
    assert items[2].url == "https://gear.example.org/backpack-40l"


def test_parse_items_raises_on_empty():
    with pytest.raises(GiftfulEmptyListError, match="no items"):
        parse_items("<html><body></body></html>")


def test_item_exposes_domain():
    item = Item(
        name="x",
        url="https://shop.example.com/products/thing",
        listed_price=10.0,
        image_url="",
    )
    assert item.domain == "shop.example.com"


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
