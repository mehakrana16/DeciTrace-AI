"""Capture screenshots of the running DeciTrace AI application.

Requires the backend on :8000 and the built frontend preview on :4173
(vite preview proxies /api to :8000).

    python scripts/screenshot.py [base_url]
"""
from __future__ import annotations

import pathlib
import sys
import time

from playwright.sync_api import sync_playwright

OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

PAGES = [
    ("dashboard", "/", 2500),
    ("customers", "/customers", 2100),
    ("decisions", "/decisions", 2300),
    ("evidence", "/evidence", 2300),
    ("analytics", "/analytics", 2900),
    ("ask", "/ask", 2400),
]


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:4173"
    failures = 0

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=2)
        page.set_default_timeout(60_000)
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        for name, path, height in PAGES:
            try:
                page.set_viewport_size({"width": 1440, "height": height})
                page.goto(base + path, wait_until="networkidle")
                if name == "ask":
                    page.fill(
                        "input[placeholder^='Which customers']",
                        "Which customers should the sales team prioritize today and why?",
                    )
                    page.click("button:has-text('Run decision workflow')")
                    page.wait_for_selector("text=Workflow executed", timeout=60_000)
                    page.wait_for_selector("text=Evidence retrieved", timeout=30_000)
                time.sleep(1.5)
                target = OUT / f"{name}.png"
                page.screenshot(path=str(target), full_page=True)
                print(f"  OK   {target.name:30} {target.stat().st_size // 1024:>5} KB")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {str(exc)[:140]}")

        # Extra capture: approve a decision for real, then screenshot the
        # persisted human-in-the-loop state.
        try:
            page.set_viewport_size({"width": 1440, "height": 2300})
            page.goto(base + "/decisions", wait_until="networkidle")
            page.wait_for_selector("button:has-text('Review')", timeout=45_000)
            page.click("button:has-text('Review')")
            page.wait_for_selector("button:has-text('Approve')", timeout=45_000)
            approve = page.locator("button:has-text('Approve')").first
            if approve.is_enabled():
                approve.click()
                page.wait_for_selector("text=human decision", timeout=40_000)
            time.sleep(1.5)
            target = OUT / "decision_card_approved.png"
            page.screenshot(path=str(target), full_page=True)
            print(f"  OK   {target.name:30} {target.stat().st_size // 1024:>5} KB")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  FAIL approve: {type(exc).__name__}: {str(exc)[:140]}")

        browser.close()
        if errors:
            print("  console errors observed:")
            for err in errors[:6]:
                print(f"    - {err[:160]}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
