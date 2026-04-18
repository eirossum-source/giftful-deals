from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple


class DealType(str, Enum):
    PRICE_DROP = "price_drop"
    SALE = "sale"
    PROMO = "promo"


@dataclass
class Deal:
    item: "Item"  # noqa: F821
    price_result: "PriceResult"  # noqa: F821
    promos: List["PromoCode"] = field(default_factory=list)  # noqa: F821
    deal_types: List[DealType] = field(default_factory=list)


def is_deal(item, price_result, promos) -> Tuple[bool, List[DealType]]:
    types: List[DealType] = []

    if (
        not price_result.unavailable
        and price_result.current_price is not None
        and price_result.current_price < item.listed_price
    ):
        types.append(DealType.PRICE_DROP)

    if not price_result.unavailable and price_result.sale_detected:
        types.append(DealType.SALE)

    if promos:
        types.append(DealType.PROMO)

    return (bool(types), types)
