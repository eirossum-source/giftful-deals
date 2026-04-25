from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from error_log import ErrorLog
from filter import Deal, StoreEvaluation, evaluate_store, is_deal
from giftful import StoreLink, fetch_list
from html_builder import render
from price_checker import check_price as real_check_price
from coupon_checker import lookup as real_lookup
from emailer import send as real_send


_UNSET = object()


def _default_fetch(session=None):
    return fetch_list(session=session)


def run(
    fetch_items: Callable = None,
    check_price: Callable = None,
    lookup_coupons: Callable = None,
    send_email: Callable = _UNSET,
    output_path: Optional[Path] = None,
    log_path: Optional[Path] = None,
    now: Optional[datetime] = None,
    session=None,
) -> dict:
    import requests

    repo_root = Path(__file__).resolve().parents[1]
    output_path = Path(output_path or repo_root / "docs" / "index.html")
    log_path = Path(log_path or repo_root / "errors.log")
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    session = session or requests.Session()

    fetch_items = fetch_items or _default_fetch
    check_price = check_price or real_check_price
    lookup_coupons = lookup_coupons or real_lookup
    if send_email is _UNSET:
        send_email = real_send

    log = ErrorLog(log_path)

    # Start with a clean errors.log for this run
    if log_path.exists():
        log_path.unlink()

    items = fetch_items(session=session) if _accepts_session(fetch_items) else fetch_items()

    deals: list[Deal] = []
    price_samples: list[tuple[str, float, float | None]] = []
    for item in items:
        if item.store_urls:
            evaluations: list[StoreEvaluation] = []
            for store in item.store_urls:
                try:
                    price_result = check_price(store.url, session=session, error_log=log)
                    promos = lookup_coupons(store.domain, session=session, error_log=log)
                    ok, types = evaluate_store(store, price_result, promos)
                    evaluations.append(
                        StoreEvaluation(
                            store=store,
                            price_result=price_result,
                            promos=promos,
                            deal_types=types,
                        )
                    )
                    price_samples.append(
                        (item.name, store.listed_price, price_result.current_price)
                    )
                except Exception as exc:
                    log.error(f"{item.name} ({store.url}): {exc}")
            if any(ev.deal_types for ev in evaluations):
                deals.append(Deal(item=item, store_evaluations=evaluations))
        else:
            try:
                price_result = check_price(item.url, session=session, error_log=log)
                promos = lookup_coupons(item.domain, session=session, error_log=log)
                ok, types = is_deal(item, price_result, promos)
                if ok:
                    deals.append(
                        Deal(
                            item=item,
                            price_result=price_result,
                            promos=promos,
                            deal_types=types,
                        )
                    )
                price_samples.append(
                    (item.name, item.listed_price, price_result.current_price)
                )
            except Exception as exc:
                log.error(f"{item.name} ({item.url}): {exc}")

    html = render(deals, generated_at=now)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    if send_email is not None:
        send_email(deals=deals, today=now.date())

    summary = {"checked": len(items), "deals": len(deals), "errors": log.count}
    print(
        f"{summary['checked']} items checked | "
        f"{summary['deals']} deals found | "
        f"{summary['errors']} errors — see errors.log"
    )

    if not deals and price_samples:
        print(f"0 deals from {len(items)} items — price samples:")
        for name, listed, current in price_samples[:5]:
            cur = f"${current:.2f}" if current is not None else "unavailable"
            print(f"  {name}: listed ${listed:.2f}, current {cur}")

    return summary


def _accepts_session(fn) -> bool:
    try:
        import inspect

        return "session" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scrape wishlist deals and publish.")
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Skip sending the Resend email (useful for local dry-runs).",
    )
    args = parser.parse_args()
    run(send_email=None if args.no_email else real_send)
