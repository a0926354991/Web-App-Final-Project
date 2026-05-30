#!/usr/bin/env python3
"""
NTU course recommendation app — E2E smoke driver.

Pre-req: backend (uvicorn) on :8000 and frontend static server on :5500
must already be running. See SKILL.md for the launch commands.

Usage:
    .venv/bin/python .claude/skills/run-ntu-course-app/driver.py
    .venv/bin/python .claude/skills/run-ntu-course-app/driver.py --headed
    .claude/skills/run-ntu-course-app/driver.py screenshot dashboard

What it covers:
    smoke (default) — load homepage, register, login, search, drawer,
                      profile save, recommendations, dark mode toggle.
                      Saves screenshots to .claude/skills/.../screenshots/.
    screenshot      — load page, optionally login, screenshot one view.

Exit code 0 on full pass; non-zero on any assertion failure.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, expect, Page

ROOT = Path(__file__).resolve().parents[3]
SHOTS = Path(__file__).resolve().parent / "screenshots"
SHOTS.mkdir(exist_ok=True)

FRONTEND = "http://127.0.0.1:5500"
BACKEND = "http://127.0.0.1:8000"


def boot(p, headed: bool):
    """Launch chromium, return (browser, page). Slow_mo helps when --headed."""
    browser = p.chromium.launch(headless=not headed, slow_mo=200 if headed else 0)
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    return browser, ctx.new_page()


def screenshot(page: Page, name: str) -> Path:
    out = SHOTS / f"{name}.png"
    page.screenshot(path=out, full_page=False)
    print(f"  📸 {out.relative_to(ROOT)}")
    return out


def wait_for_servers(page: Page) -> None:
    """Probe both servers before doing anything else."""
    try:
        r = page.request.get(f"{BACKEND}/health", timeout=5000)
        assert r.ok, f"backend health failed: {r.status}"
    except Exception as e:
        print(f"❌ backend not reachable on {BACKEND}: {e}", file=sys.stderr)
        print(f"   start it with:  source .venv/bin/activate && uvicorn backend.api.main:app", file=sys.stderr)
        sys.exit(2)
    try:
        r = page.request.get(f"{FRONTEND}/", timeout=5000)
        assert r.ok, f"frontend serve failed: {r.status}"
    except Exception as e:
        print(f"❌ frontend not reachable on {FRONTEND}: {e}", file=sys.stderr)
        print(f"   start it with:  python3 -m http.server 5500 --directory frontend/src", file=sys.stderr)
        sys.exit(2)


def smoke(headed: bool = False) -> None:
    """Full happy-path: register → login → search → drawer → profile → recommend."""
    with sync_playwright() as p:
        browser, page = boot(p, headed)
        page_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("console", lambda m: m.type == "error" and page_errors.append(f"console: {m.text}")
                if "favicon" not in m.text and ".map" not in m.text else None)

        wait_for_servers(page)

        # 1. Homepage loads, radar chart canvas renders
        print("→ load homepage")
        page.goto(FRONTEND + "/", wait_until="networkidle")
        expect(page.locator("#radarChart")).to_be_visible()
        expect(page.locator(".zh-title")).to_contain_text("台大個性化選課推薦")
        screenshot(page, "01-dashboard-anon")

        # 2. Register a fresh user (timestamped to avoid 409)
        username = f"smoke_{int(time.time())}"
        password = "smoke1234"
        print(f"→ register {username}")
        page.click("#btn-login")
        page.click("#auth-switch-link")  # switch to register
        page.fill("#auth-username", username)
        page.fill("#auth-password", password)
        page.click("#auth-submit")
        expect(page.locator("#header-username")).to_contain_text("已登入", timeout=5000)
        screenshot(page, "02-after-login")

        # 3. Course discovery — search & open drawer
        print("→ discover view: search for 微積分")
        page.click('.sidebar-item[data-target="discover"]')
        page.fill("#search-input", "微積分")
        page.click("#search-btn")
        page.wait_for_selector("#results-body tr[data-id]", timeout=10000)
        row_count = page.locator("#results-body tr[data-id]").count()
        assert row_count > 0, "expected at least one search result"
        print(f"   got {row_count} results")
        screenshot(page, "03-discover-results")

        print("→ open course drawer")
        page.locator("#results-body tr[data-id]").first.click()
        expect(page.locator("#detail-drawer.open")).to_be_visible(timeout=5000)
        # drawer should have at least the fit box OR drawer-section
        expect(page.locator("#drawer-body .drawer-section").first).to_be_visible()
        screenshot(page, "04-drawer-open")
        page.click("#drawer-close")

        # 4. Profile save
        print("→ profile: save preferences")
        page.click('.sidebar-item[data-target="userinfo"]')
        page.wait_for_selector("#profile-form:not([hidden])", timeout=5000)
        # tap an interest tag
        page.locator(".interest-tag", has_text="程式").click()
        page.click("#profile-save")
        expect(page.locator("#profile-saved")).to_be_visible(timeout=3000)
        screenshot(page, "05-profile-saved")

        # 5. Fit analysis view (Top 20 recommendations)
        print("→ fit analysis: top recommendations")
        page.click('.sidebar-item[data-target="fit"]')
        page.wait_for_selector("#fit-list .fit-list-item[data-id]", timeout=15000)
        n_recs = page.locator("#fit-list .fit-list-item[data-id]").count()
        assert n_recs > 0, "expected at least one recommendation"
        print(f"   got {n_recs} recommendations")
        screenshot(page, "06-fit-analysis")

        # 6. Theme toggle — assert the theme class actually FLIPS, whatever the
        #    default is. (App now defaults to the 'tech' dark theme, so clicking
        #    once goes dark→light; don't hard-assert one specific end state.)
        print("→ theme toggle")
        before = page.locator("body").evaluate("b => b.classList.contains('theme-dark')")
        page.click("#theme-toggle")
        page.wait_for_function(
            "prev => document.body.classList.contains('theme-dark') !== prev",
            arg=before,
            timeout=3000,
        )
        after = page.locator("body").evaluate("b => b.classList.contains('theme-dark')")
        assert after != before, f"theme did not flip (before={before}, after={after})"
        # screenshot whichever state shows the toggle worked; flip back to dark for a
        # consistent dark-mode shot if we landed on light
        if not after:
            page.click("#theme-toggle")
            page.wait_for_function(
                "() => document.body.classList.contains('theme-dark')", timeout=3000
            )
        screenshot(page, "07-dark-mode")

        # 7. Confirm no uncaught JS errors hit the page
        # (we deliberately ignore source-map 404s)
        real_errors = [e for e in page_errors if "Failed to load resource" not in e]
        if real_errors:
            print("\n❌ JS errors during smoke:")
            for e in real_errors:
                print(f"   {e}")
            sys.exit(3)

        browser.close()
        print(f"\n✅ smoke pass — {len(list(SHOTS.glob('*.png')))} screenshots in {SHOTS.relative_to(ROOT)}")


def shot_only(view: str, headed: bool = False) -> None:
    """Just screenshot one view (no register). For quick visual checks."""
    with sync_playwright() as p:
        browser, page = boot(p, headed)
        wait_for_servers(page)
        page.goto(FRONTEND + "/", wait_until="networkidle")
        if view != "dashboard":
            page.click(f'.sidebar-item[data-target="{view}"]')
            page.wait_for_timeout(800)
        screenshot(page, f"adhoc-{view}")
        browser.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="NTU course app E2E driver")
    ap.add_argument("cmd", nargs="?", default="smoke", choices=["smoke", "screenshot"])
    ap.add_argument("view", nargs="?", default="dashboard",
                    help="for screenshot: dashboard | discover | userinfo | history | schedule | wishlist | fit")
    ap.add_argument("--headed", action="store_true", help="show the browser window (debug)")
    args = ap.parse_args()

    if args.cmd == "smoke":
        smoke(headed=args.headed)
    else:
        shot_only(args.view, headed=args.headed)


if __name__ == "__main__":
    main()
