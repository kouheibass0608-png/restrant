"""Manual/CI read-only probe of public Ginzan booking pages. No booking actions."""
from playwright.sync_api import sync_playwright
import json

SITES = {
    "portal": "https://www.nj-yoyaku.net/portal/main",
    "ginzanso": "https://reserve.489ban.net/client/ginzanso/0/plan/availability/room/stay?date=2026-12-01",
    "kosekiya": "https://reserve.489ban.net/client/kosekiya/0/plan/availability/room/stay?date=2026-12-01",
    "kosekikan": "https://reserve.489ban.net/client/kosekikan/0/plan/availability/room/stay?date=2026-12-01",
    "notoya": "https://reserve.489ban.net/client/notoyaryokan/0/plan/availability/room/stay?date=2026-12-01",
}
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for name, url in SITES.items():
        page = browser.new_page(locale="ja-JP", timezone_id="Asia/Tokyo")
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(1500)
            info = page.evaluate("""() => ({
                title: document.title,
                text: document.body?.innerText?.slice(0, 1700),
                url: location.href,
                forms: [...document.querySelectorAll('form')].slice(0, 3).map(f => ({ action: f.action, method: f.method })),
                inputs: [...document.querySelectorAll('input,select')].slice(0, 25).map(e => ({
                    tag: e.tagName, type: e.type, id: e.id, name: e.name, value: e.value,
                    placeholder: e.getAttribute('placeholder'),
                    outer: e.outerHTML.slice(0, 230)
                })),
                dateElems: [...document.querySelectorAll('td,th,[data-date]')]
                    .filter(e => /(^|\D)13(\D|$)/.test((e.innerText||'').trim()) || (e.getAttribute('data-date')||'').includes('2026-12-13'))
                    .slice(0, 16).map(e => e.outerHTML.slice(0, 500)),
                links: [...document.querySelectorAll('a')].filter(x => /全プラン|検索|空室/.test(x.innerText||''))
                    .slice(0, 8).map(x => ({text: x.innerText, href: x.href}))
            })""")
            print("PROBE",name,response.status if response else None, json.dumps(info,ensure_ascii=False)[:12000],flush=True)
        except Exception as e:
            print("PROBE_FAILED",name,type(e).__name__,str(e)[:600],flush=True)
        finally:
            page.close()
    browser.close()
