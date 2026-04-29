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
from inventory import (
    is_back_in_stock,
    load_state,
    normalize_url,
    save_state,
    update_item,
)
from validator import check_identity, check_link_integrity, check_sold_out


_UNSET = object()


def _default_fetch(session=None):
    return fetch_list(session=session)


def _validate(item_name: str, html: Optional[str]):
    """Run patch-only validators on retailer HTML.

    Returns (status, reason) where status is one of:
      "ok"         — page is valid, item identity matches, in stock
      "review"     — page is dead or shows a different product
      "sold_out"   — page is valid but item is out of stock
      "skip"       — no html available; treat as before (fall through to deal logic)
    """
    if not html:
        return "skip", None
    is_dead, dead_reason = check_link_integrity(html)
    if is_dead:
        return "review", f"dead link ({dead_reason})"
    matches, score = check_identity(item_name, html)
    if not matches:
        return "review", f"product name mismatch (score {score:.2f})"
    if check_sold_out(html):
        return "sold_out", "out of stock"
    return "ok", None


def run(
    fetch_items: Callable = None,
    check_price: Callable = None,
    lookup_coupons: Callable = None,
    send_email: Callable = _UNSET,
    output_path: Optional[Path] = None,
    log_path: Optional[Path] = None,
    state_path: Optional[Path] = None,
    review_log_path: Optional[Path] = None,
    now: Optional[datetime] = None,
    session=None,
    page=None,
) -> dict:
    import requests

    repo_root = Path(__file__).resolve().parents[1]
    output_path = Path(output_path or repo_root / "docs" / "index.html")
    log_path = Path(log_path or repo_root / "errors.log")
    state_path = Path(state_path or repo_root / "state" / "inventory.json")
    review_log_path = Path(review_log_path or repo_root / "state" / "review_log.json")
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

    prev_state = load_state(state_path)
    new_state = {"items": {}}
    today = now.date()

    items = fetch_items(session=session) if _accepts_session(fetch_items) else fetch_items()

    deals: list[Deal] = []
    review_items: list[dict] = []
    review_log_entries: list[dict] = []
    price_samples: list[tuple[str, float, float | None]] = []

    for item in items:
        if item.store_urls:
            evaluations: list[StoreEvaluation] = []
            review_for_item: list[str] = []
            in_stock_any = False
            for store in item.store_urls:
                try:
                    price_result = check_price(
                        store.url, session=session, error_log=log, page=page
                    )
                    status, reason = _validate(item.name, price_result.html)

                    if status == "review":
                        review_for_item.append(f"{store.display_name}: {reason}")
                        review_log_entries.append({
                            "name": item.name,
                            "url": store.url,
                            "store": store.display_name,
                            "status": "review",
                            "reason": reason,
                        })
                        # Don't touch state for review items — they're "couldn't
                        # verify," not "sold out." Let prior state stand so we
                        # don't trigger spurious back-in-stock next run.
                        continue
                    if status == "sold_out":
                        review_log_entries.append({
                            "name": item.name,
                            "url": store.url,
                            "store": store.display_name,
                            "status": "sold_out",
                            "reason": reason or "out of stock",
                        })
                        update_item(
                            new_state,
                            url=normalize_url(store.url),
                            name=item.name,
                            in_stock=False,
                            current_price=price_result.current_price,
                            listed_price=store.listed_price,
                            today=today,
                        )
                        continue

                    review_log_entries.append({
                        "name": item.name,
                        "url": store.url,
                        "store": store.display_name,
                        "status": "ok",
                        "reason": None,
                    })
                    in_stock_any = True
                    promos = lookup_coupons(store.domain, session=session, error_log=log)
                    norm = normalize_url(store.url)
                    back_in_stock = is_back_in_stock(prev_state, norm, True)
                    ok, types = evaluate_store(store, price_result, promos, back_in_stock=back_in_stock)
                    evaluations.append(
                        StoreEvaluation(
                            store=store,
                            price_result=price_result,
                            promos=promos,
                            deal_types=types,
                        )
                    )
                    update_item(
                        new_state,
                        url=norm,
                        name=item.name,
                        in_stock=True,
                        current_price=price_result.current_price,
                        listed_price=store.listed_price,
                        today=today,
                    )
                    price_samples.append(
                        (item.name, store.listed_price, price_result.current_price)
                    )
                except Exception as exc:
                    log.error(f"{item.name} ({store.url}): {exc}")

            if review_for_item and not in_stock_any:
                review_items.append({"item": item, "reasons": review_for_item})
            if any(ev.deal_types for ev in evaluations):
                deals.append(Deal(item=item, store_evaluations=evaluations))
        else:
            try:
                price_result = check_price(
                    item.url, session=session, error_log=log, page=page
                )
                status, reason = _validate(item.name, price_result.html)
                norm = normalize_url(item.url)

                if status == "review":
                    review_items.append({"item": item, "reasons": [reason]})
                    review_log_entries.append({
                        "name": item.name,
                        "url": item.url,
                        "store": item.domain,
                        "status": "review",
                        "reason": reason,
                    })
                    # Don't touch state for review items — see comment above.
                    continue
                if status == "sold_out":
                    review_log_entries.append({
                        "name": item.name,
                        "url": item.url,
                        "store": item.domain,
                        "status": "sold_out",
                        "reason": reason or "out of stock",
                    })
                    update_item(
                        new_state,
                        url=norm,
                        name=item.name,
                        in_stock=False,
                        current_price=price_result.current_price,
                        listed_price=item.listed_price,
                        today=today,
                    )
                    continue

                review_log_entries.append({
                    "name": item.name,
                    "url": item.url,
                    "store": item.domain,
                    "status": "ok",
                    "reason": None,
                })
                promos = lookup_coupons(item.domain, session=session, error_log=log)
                back_in_stock = is_back_in_stock(prev_state, norm, True)
                ok, types = is_deal(item, price_result, promos, back_in_stock=back_in_stock)
                if ok:
                    deals.append(
                        Deal(
                            item=item,
                            price_result=price_result,
                            promos=promos,
                            deal_types=types,
                        )
                    )
                update_item(
                    new_state,
                    url=norm,
                    name=item.name,
                    in_stock=True,
                    current_price=price_result.current_price,
                    listed_price=item.listed_price,
                    today=today,
                )
                price_samples.append(
                    (item.name, item.listed_price, price_result.current_price)
                )
            except Exception as exc:
                log.error(f"{item.name} ({item.url}): {exc}")

    html = render(deals, generated_at=now, review_items=review_items)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    save_state(state_path, new_state)

    import json as _json
    review_log_path.parent.mkdir(parents=True, exist_ok=True)
    review_log_path.write_text(
        _json.dumps(
            {
                "run_at": now.isoformat(),
                "items": review_log_entries,
            },
            indent=2,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    if send_email is not None:
        send_email(deals=deals, today=now.date())

    summary = {
        "checked": len(items),
        "deals": len(deals),
        "errors": log.count,
        "review": len(review_items),
    }
    print(
        f"{summary['checked']} items checked | "
        f"{summary['deals']} deals found | "
        f"{summary['review']} flagged for review | "
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


_PRICE_CHECK_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)


if __name__ == "__main__":
    import argparse
    import requests as _requests

    parser = argparse.ArgumentParser(description="Scrape wishlist deals and publish.")
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Skip sending the Resend email (useful for local dry-runs).",
    )
    args = parser.parse_args()

    # giftful.fetch_list opens its own Playwright context and closes it.
    # sync_playwright contexts cannot nest, so we fetch first, then open a
    # fresh Playwright for the price-check fallback.
    cli_session = _requests.Session()
    items = fetch_list(session=cli_session)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=_PRICE_CHECK_USER_AGENT,
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        try:
            run(
                fetch_items=lambda **_: items,
                send_email=None if args.no_email else real_send,
                session=cli_session,
                page=page,
            )
        finally:
            browser.close()
