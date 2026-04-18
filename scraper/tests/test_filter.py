from datetime import date

from coupon_checker import PromoCode
from filter import DealType, is_deal
from giftful import Item
from price_checker import PriceResult


ITEM = Item(
    name="Thing",
    url="https://shop.example.com/thing",
    listed_price=100.0,
    image_url="",
)


def test_price_drop_included():
    price = PriceResult(current_price=80.0, sale_detected=False)
    ok, types = is_deal(ITEM, price, [])
    assert ok is True
    assert DealType.PRICE_DROP in types


def test_sale_detected_included():
    price = PriceResult(current_price=100.0, sale_detected=True)
    ok, types = is_deal(ITEM, price, [])
    assert ok is True
    assert DealType.SALE in types


def test_promo_included():
    promo = [PromoCode(code="X", description="10% off", expiry=date(2099, 1, 1))]
    price = PriceResult(current_price=100.0, sale_detected=False)
    ok, types = is_deal(ITEM, price, promo)
    assert ok is True
    assert DealType.PROMO in types


def test_multiple_reasons_combine():
    promo = [PromoCode(code="X", description="", expiry=None)]
    price = PriceResult(current_price=50.0, sale_detected=True)
    ok, types = is_deal(ITEM, price, promo)
    assert ok is True
    assert set(types) == {DealType.PRICE_DROP, DealType.SALE, DealType.PROMO}


def test_none_excluded():
    price = PriceResult(current_price=100.0, sale_detected=False)
    ok, types = is_deal(ITEM, price, [])
    assert ok is False
    assert types == []


def test_unavailable_price_with_promo_still_deal():
    promo = [PromoCode(code="X", description="", expiry=None)]
    price = PriceResult(unavailable=True, reason="blocked")
    ok, types = is_deal(ITEM, price, promo)
    assert ok is True
    assert types == [DealType.PROMO]


def test_unavailable_price_no_promo_excluded():
    price = PriceResult(unavailable=True, reason="blocked")
    ok, types = is_deal(ITEM, price, [])
    assert ok is False
    assert types == []


def test_equal_price_not_a_drop():
    price = PriceResult(current_price=100.0, sale_detected=False)
    ok, types = is_deal(ITEM, price, [])
    assert ok is False
