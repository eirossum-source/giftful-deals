from datetime import date

from coupon_checker import PromoCode
from filter import Deal, DealType, is_deal
from giftful import Item
from price_checker import PriceResult


ITEM = Item(
    name="Thing",
    url="https://shop.example.com/thing",
    listed_price=100.0,
    image_url="",
)


def test_price_drop_included():
    price = PriceResult(current_price=80.0)
    ok, types = is_deal(ITEM, price, [])
    assert ok is True
    assert DealType.PRICE_DROP in types


def test_back_in_stock_included():
    price = PriceResult(current_price=100.0)
    ok, types = is_deal(ITEM, price, [], back_in_stock=True)
    assert ok is True
    assert DealType.BACK_IN_STOCK in types


def test_promo_included():
    promo = [PromoCode(code="X", description="10% off", expiry=date(2099, 1, 1))]
    price = PriceResult(current_price=100.0)
    ok, types = is_deal(ITEM, price, promo)
    assert ok is True
    assert DealType.PROMO in types


def test_multiple_reasons_combine():
    promo = [PromoCode(code="X", description="", expiry=None)]
    price = PriceResult(current_price=50.0)
    ok, types = is_deal(ITEM, price, promo, back_in_stock=True)
    assert ok is True
    assert set(types) == {DealType.PRICE_DROP, DealType.PROMO, DealType.BACK_IN_STOCK}


def test_none_excluded():
    price = PriceResult(current_price=100.0)
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
    price = PriceResult(current_price=100.0)
    ok, types = is_deal(ITEM, price, [])
    assert ok is False


# --- Slice C: per-store evaluation ---

from filter import StoreEvaluation, evaluate_store
from giftful import StoreLink


STORE_A = StoreLink(url="https://shop-a.com/item", display_name="Shop A", listed_price=100.0)
STORE_B = StoreLink(url="https://shop-b.com/item", display_name="Shop B", listed_price=120.0)


def test_evaluate_store_price_drop():
    price = PriceResult(current_price=80.0)
    ok, types = evaluate_store(STORE_A, price, [])
    assert ok is True
    assert DealType.PRICE_DROP in types


def test_evaluate_store_back_in_stock():
    price = PriceResult(current_price=100.0)
    ok, types = evaluate_store(STORE_A, price, [], back_in_stock=True)
    assert ok is True
    assert DealType.BACK_IN_STOCK in types


def test_evaluate_store_promo():
    promo = [PromoCode(code="X", description="10% off", expiry=date(2099, 1, 1))]
    price = PriceResult(current_price=100.0)
    ok, types = evaluate_store(STORE_A, price, promo)
    assert ok is True
    assert DealType.PROMO in types


def test_evaluate_store_no_deal():
    price = PriceResult(current_price=100.0)
    ok, types = evaluate_store(STORE_A, price, [])
    assert ok is False
    assert types == []


def test_evaluate_store_unavailable_with_promo():
    promo = [PromoCode(code="X", description="", expiry=None)]
    price = PriceResult(unavailable=True, reason="blocked")
    ok, types = evaluate_store(STORE_A, price, promo)
    assert ok is True
    assert types == [DealType.PROMO]


def test_evaluate_store_equal_price_not_a_drop():
    price = PriceResult(current_price=100.0)
    ok, types = evaluate_store(STORE_A, price, [])
    assert ok is False


def test_store_evaluation_holds_per_store_results():
    price = PriceResult(current_price=80.0)
    ev = StoreEvaluation(
        store=STORE_A,
        price_result=price,
        promos=[],
        deal_types=[DealType.PRICE_DROP],
    )
    assert ev.store is STORE_A
    assert ev.price_result is price
    assert ev.deal_types == [DealType.PRICE_DROP]


def test_deal_winner_picks_lowest_current_price():
    ev_a = StoreEvaluation(
        store=STORE_A,
        price_result=PriceResult(current_price=90.0),
        promos=[],
        deal_types=[DealType.PRICE_DROP],
    )
    ev_b = StoreEvaluation(
        store=STORE_B,
        price_result=PriceResult(current_price=75.0),
        promos=[],
        deal_types=[DealType.PRICE_DROP],
    )
    deal = Deal(item=ITEM, store_evaluations=[ev_a, ev_b])
    assert deal.winner is ev_b


def test_deal_winner_falls_back_to_listed_when_current_unavailable():
    ev_a = StoreEvaluation(
        store=STORE_A,
        price_result=PriceResult(unavailable=True),
        promos=[],
        deal_types=[],
    )
    ev_b = StoreEvaluation(
        store=STORE_B,
        price_result=PriceResult(current_price=110.0),
        promos=[],
        deal_types=[DealType.PRICE_DROP],
    )
    deal = Deal(item=ITEM, store_evaluations=[ev_a, ev_b])
    # STORE_A effective = listed 100, STORE_B effective = current 110 → A wins
    assert deal.winner is ev_a


def test_deal_backcompat_properties_from_winner():
    promo = [PromoCode(code="X", description="", expiry=None)]
    ev = StoreEvaluation(
        store=STORE_A,
        price_result=PriceResult(current_price=80.0),
        promos=promo,
        deal_types=[DealType.PRICE_DROP, DealType.PROMO],
    )
    deal = Deal(item=ITEM, store_evaluations=[ev])
    assert deal.price_result.current_price == 80.0
    assert deal.promos == promo
    assert DealType.PRICE_DROP in deal.deal_types


def test_deal_legacy_construction_still_works():
    price = PriceResult(current_price=80.0)
    deal = Deal(
        item=ITEM,
        price_result=price,
        promos=[],
        deal_types=[DealType.PRICE_DROP],
    )
    assert deal.price_result is price
    assert deal.deal_types == [DealType.PRICE_DROP]
