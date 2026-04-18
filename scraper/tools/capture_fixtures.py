"""Optional dev helper: capture real HTML snapshots for sanity-checking parsers.

Tests do NOT depend on this script. Fixtures in scraper/tests/fixtures are
hand-authored and represent the structural patterns each parser targets.
Run this script only when you want to verify parsers against live sites.

Usage:
    python3.11 scraper/tools/capture_fixtures.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright not installed. Run: python3.11 -m playwright install chromium")
    sys.exit(1)

import requests


GIFTFUL_URL = "https://giftful.com/isaacrossum"
OUT_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "captured"


def capture_giftful(out: Path) -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(GIFTFUL_URL, wait_until="networkidle", timeout=60_000)
        html = page.content()
        browser.close()
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}")


def capture_url(url: str, out: Path) -> None:
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    try:
        resp = requests.get(url, headers={"User-Agent": ua}, timeout=30)
        resp.raise_for_status()
    except Exception as exc:
        print(f"FAILED {url}: {exc}")
        return
    out.write_text(resp.text, encoding="utf-8")
    print(f"Wrote {out}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    capture_giftful(OUT_DIR / "giftful_real.html")
    if len(sys.argv) > 1:
        for i, url in enumerate(sys.argv[1:], 1):
            capture_url(url, OUT_DIR / f"retailer_real_{i}.html")


if __name__ == "__main__":
    main()
