"""Read-only diagnosis of the Ginzan 489ban HTTP 503. No bypass, credentials or automated retry."""
from playwright.sync_api import sync_playwright
import json

targets = [
    ("489ban", "https://reserve.489ban.net/client/ginzanso/0/plan/availability/room/stay?date=2026-12-01"),
    ("ryokan-portal", "https://www.nj-yoyaku.net/ginzanso/plan.aspx?TDT=20261213&NZ=2"),
]
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for label, url in targets:
        page = browser.new_page(locale="ja-JP", timezone_id="Asia/Tokyo")
        try:
            r = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if r is None:
                print("DIAGNOSTIC", label, "no-response", flush=True)
                continue
            headers = r.headers
            title = page.title()[:130]
            visible = page.locator("body").inner_text(timeout=4000)[:300]
            print("DIAGNOSTIC", json.dumps({
                "site":label,
                "status":r.status,
                "title":title,
                "content_type":headers.get("content-type"),
                "server":headers.get("server"),
                "retry_after":headers.get("retry-after"),
                "visible_text_excerpt":visible,
            }, ensure_ascii=False), flush=True)
        except Exception as exc:
            print("DIAGNOSTIC_ERROR",label,type(exc).__name__,str(exc)[:200], flush=True)
        finally:
            page.close()
    browser.close()
