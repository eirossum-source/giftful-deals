"""3-level Giftful walk: profile -> category -> item modal.

Captures raw rendered HTML at each level so we can design parsers against the
real DOM. Not run by tests -- one-off diagnostic. Discovers categories
dynamically (a[href*="/wishlists/"]) so it works for any Giftful profile.

Usage:
    python3 scraper/tools/capture_giftful_walk.py
    python3 scraper/tools/capture_giftful_walk.py --url https://giftful.com/<user>

Output (gitignored): scraper/tools/captures/{profile,category,item_modal}.html
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    print("Playwright not installed. Run: python -m playwright install chromium")
    sys.exit(1)


DEFAULT_PROFILE = "https://giftful.com/isaacrossum"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
OUT = Path(__file__).resolve().parent / "captures"


def _save(path: Path, html: str) -> None:
    path.write_text(html, encoding="utf-8")
    try:
        rel = path.relative_to(Path.cwd())
    except ValueError:
        rel = path
    print(f"   saved {rel}  ({len(html):,} bytes)")


def _probe(page, label: str, selectors: list[str]) -> None:
    print(f"   --- {label} ---")
    for sel in selectors:
        try:
            n = page.locator(sel).count()
        except Exception as exc:
            n = f"ERR {exc!r}"
        print(f"   {sel:55s} -> {n}")


def _dedupe_by_href(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for it in items:
        href = it.get("href") or ""
        if href and href not in seen:
            seen.add(href)
            out.append(it)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_PROFILE, help="profile URL to walk")
    ap.add_argument("--headful", action="store_true",
                    help="run a visible browser (for debugging)")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headful)
        ctx = browser.new_context(
            user_agent=UA, viewport={"width": 1280, "height": 900}
        )
        page = ctx.new_page()

        # ---- Level 1: profile ----
        print(f"-> GET {args.url}")
        page.goto(args.url, wait_until="networkidle", timeout=60_000)
        _save(OUT / "profile.html", page.content())

        categories = page.evaluate(
            """() => Array.from(document.querySelectorAll('a[href*="/wishlists/"]'))
                .map(a => ({
                    href: a.href,
                    text: ((a.innerText || a.textContent || '').trim().split('\\n')[0] || '').slice(0, 120)
                }))"""
        )
        categories = _dedupe_by_href(categories)
        print(f"   discovered {len(categories)} /wishlists/ links:")
        for c in categories:
            print(f"     - {c['text']!r:40s}  {c['href']}")

        if not categories:
            print("!! no category links on profile -- parser needs a different selector.")
            browser.close()
            return 1

        # ---- Level 2: first category ----
        first = categories[0]
        print(f"-> GET {first['href']}   (category: {first['text']!r})")
        page.goto(first["href"], wait_until="networkidle", timeout=60_000)
        _save(OUT / "category.html", page.content())

        _probe(page, "category-page item-card candidates", [
            'button:has(img[alt="Feature Image"])',
            "button.break-inside-avoid",
            'img[alt="Feature Image"]',
            'img[alt="Brand Icon"]',
            "main img",
            "[data-item-id]",
            "article",
        ])

        # ---- Level 3: open modal for first item ----
        item_btn = page.locator('button:has(img[alt="Feature Image"])').first
        n_cards = page.locator('button:has(img[alt="Feature Image"])').count()
        print(f"   item-card count on this category: {n_cards}")
        if item_btn.count() == 0:
            print("!! no item-card buttons on category page -- can't open modal")
            browser.close()
            return 1

        print("-> clicking first item-card button")
        try:
            item_btn.scroll_into_view_if_needed(timeout=3_000)
            item_btn.click(timeout=5_000)
        except Exception as exc:
            print(f"   click failed: {exc!r}")
            browser.close()
            return 1

        modal_sel = None
        for sel in ['[role="dialog"]', '[aria-modal="true"]',
                    '[class*="modal" i]', '[class*="overlay" i]']:
            try:
                page.wait_for_selector(sel, timeout=4_000, state="visible")
                modal_sel = sel
                print(f"   modal detected via {sel!r}")
                break
            except PWTimeout:
                continue
        if not modal_sel:
            print("   no known modal selector matched -- waiting 2s for async render")
            page.wait_for_timeout(2_000)

        _save(OUT / "item_modal.html", page.content())

        _probe(page, "modal retailer-link candidates", [
            'a[href^="http"]:not([href*="giftful.com"])',
            'a[target="_blank"]',
            '[role="dialog"] a',
            '[role="dialog"] a[href^="http"]',
        ])

        links = page.eval_on_selector_all(
            'a[href^="http"]',
            "els => els.map(a => ({"
            "  href: a.href,"
            "  text: ((a.innerText || '').trim().split('\\n')[0] || '').slice(0, 80)"
            "}))",
        )
        external = [l for l in links if "giftful.com" not in l["href"]]
        print(f"   first {min(10, len(external))} external links now on page:")
        for l in external[:10]:
            print(f"     - {l['text']!r}  {l['href']}")

        browser.close()

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
