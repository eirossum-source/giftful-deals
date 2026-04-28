"""Render a sample deals page using realistic mock data.

Useful for eyeballing the HTML design without hitting live sites.

Usage:
    python3.11 scraper/tools/demo_html.py
    open docs/index.html   # macOS
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coupon_checker import PromoCode
from filter import Deal, DealType
from giftful import Item
from html_builder import render
from price_checker import PriceResult


def build_demo_deals() -> list[Deal]:
    return [
        Deal(
            item=Item(
                name="Wireless Over-Ear Headphones",
                url="https://shop.example.com/products/headphones",
                listed_price=299.00,
                image_url="",
            ),
            price_result=PriceResult(current_price=199.00),
            promos=[],
            deal_types=[DealType.PRICE_DROP],
        ),
        Deal(
            item=Item(
                name="Burr Coffee Grinder",
                url="https://store.example.net/coffee-grinder",
                listed_price=249.99,
                image_url="",
            ),
            price_result=PriceResult(current_price=249.99),
            promos=[
                PromoCode(
                    code="SAVE20",
                    description="20% off your order",
                    expiry=date(2099, 12, 31),
                ),
                PromoCode(
                    code="FREESHIP",
                    description="Free shipping",
                    expiry=date(2099, 6, 15),
                ),
            ],
            deal_types=[DealType.PROMO],
        ),
        Deal(
            item=Item(
                name="40L Travel Backpack",
                url="https://gear.example.org/backpack-40l",
                listed_price=129.50,
                image_url="",
            ),
            price_result=PriceResult(current_price=89.00),
            promos=[
                PromoCode(code="ADVENTURE10", description="10% off", expiry=None),
            ],
            deal_types=[DealType.PRICE_DROP, DealType.PROMO],
        ),
        Deal(
            item=Item(
                name="Mechanical Keyboard (TKL)",
                url="https://keys.example.io/tkl",
                listed_price=169.00,
                image_url="",
            ),
            price_result=PriceResult(current_price=169.00),
            promos=[],
            deal_types=[DealType.BACK_IN_STOCK],
        ),
    ]


def main() -> None:
    out = Path(__file__).resolve().parents[2] / "docs" / "index.html"
    html = render(build_demo_deals(), generated_at=datetime.utcnow())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Wrote demo page to {out}")


if __name__ == "__main__":
    main()
