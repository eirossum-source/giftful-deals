from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple


class DealType(str, Enum):
    PRICE_DROP = "price_drop"
    PROMO = "promo"
    BACK_IN_STOCK = "back_in_stock"


@dataclass
class StoreEvaluation:
    store: "StoreLink"  # noqa: F821
    price_result: "PriceResult"  # noqa: F821
    promos: List["PromoCode"] = field(default_factory=list)  # noqa: F821
    deal_types: List[DealType] = field(default_factory=list)


class Deal:
    def __init__(
        self,
        item,
        store_evaluations: Optional[List[StoreEvaluation]] = None,
        price_result=None,
        promos=None,
        deal_types=None,
    ):
        self.item = item
        self._legacy = store_evaluations is None
        if self._legacy:
            self._price_result = price_result
            self._promos = promos or []
            self._deal_types = deal_types or []
            self._store_evaluations: List[StoreEvaluation] = []
        else:
            self._store_evaluations = list(store_evaluations)

    @property
    def store_evaluations(self) -> List[StoreEvaluation]:
        return self._store_evaluations

    @property
    def winner(self) -> Optional[StoreEvaluation]:
        if not self._store_evaluations:
            return None

        def _effective_price(ev: StoreEvaluation) -> float:
            if ev.price_result.current_price is not None:
                return ev.price_result.current_price
            return ev.store.listed_price

        return min(self._store_evaluations, key=_effective_price)

    @property
    def price_result(self):
        if self._legacy:
            return self._price_result
        w = self.winner
        return w.price_result if w else None

    @property
    def promos(self):
        if self._legacy:
            return self._promos
        w = self.winner
        return w.promos if w else []

    @property
    def deal_types(self):
        if self._legacy:
            return self._deal_types
        w = self.winner
        return w.deal_types if w else []


def evaluate_store(store, price_result, promos, back_in_stock: bool = False) -> Tuple[bool, List[DealType]]:
    types: List[DealType] = []

    if (
        not price_result.unavailable
        and price_result.current_price is not None
        and price_result.current_price < store.listed_price
    ):
        types.append(DealType.PRICE_DROP)

    if promos:
        types.append(DealType.PROMO)

    if back_in_stock:
        types.append(DealType.BACK_IN_STOCK)

    return (bool(types), types)


def is_deal(item, price_result, promos, back_in_stock: bool = False) -> Tuple[bool, List[DealType]]:
    types: List[DealType] = []

    if (
        not price_result.unavailable
        and price_result.current_price is not None
        and price_result.current_price < item.listed_price
    ):
        types.append(DealType.PRICE_DROP)

    if promos:
        types.append(DealType.PROMO)

    if back_in_stock:
        types.append(DealType.BACK_IN_STOCK)

    return (bool(types), types)
