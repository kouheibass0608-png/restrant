"""Read-only structural probe, without printing hidden tokens or personal data."""
import json
from playwright.sync_api import sync_playwright

SITES = {
    "portal": "https://www.nj-yoyaku.net/portal/main",
    "ginzanso": "https://reserve.489ban.net/client/ginzanso/0/plan/availability/room/stay?date=2026-12-01",
    "kosekiya": "https://reserve.489ban.net/client/kosekiya/0/plan/availability/room/stay?date=2026-12-01",
    "kosekikan": "https://reserve.489ban.net/client/kosekikan/0/plan/availability/room/stay?date=2026-12-01",
    "notoya": "https://reserve.489ban.net/client/notoyaryokan/0/plan/availability/room/stay?date=2026-12-01",
    "takimikan": "https://reserve.489ban.net/client/takimikan/0/plan/availability/room/stay?date=2026-12-01",
}
JS = r"""() => {
 const tables = [...document.querySelectorAll('table')].filter(t=>
    [...t.querySelectorAll('th')].some(h=> /^(?:13|13\s*日)$/.test((h.innerText||'').replace(/\s+/g,'')))
 );
 return {
   title: document.title,
   url: location.href,
   tables: tables.slice(0, 3).map(t=>{
     const trs=[...t.querySelectorAll('tr')];
     const heads=trs.filter(tr=>[...tr.querySelectorAll('th')].some(h=>/^13(?:日)?$/.test((h.innerText||'').replace(/\s+/g,''))));
     return {
       tableClass: t.className,
       tableOuterStart: t.outerHTML.slice(0,1700),
       rows: trs.slice(0,4).map(r=>({class:r.className,
         heads:[...r.querySelectorAll('th')].map(h=>h.innerText.trim()).slice(0,20),
         cells:[...r.querySelectorAll('td')].map(c=>({txt:(c.innerText||'').trim(),class:c.className,
           title:c.getAttribute('title'),
           html:c.outerHTML.slice(0,650)})).slice(10,14)
       })),
       headerRows:heads.map(r=>({class:r.className,html:r.outerHTML.slice(0,1800)}))
     }
   }),
   portalTargets:[...document.querySelectorAll('a,button,input[type=submit]')]
      .filter(e=>/全プランを見る/.test(e.innerText||e.value||'')).slice(0,14)
      .map(e=>({tag:e.tagName,href:e.getAttribute('href'),onclick:e.getAttribute('onclick'),
        outer:e.outerHTML.slice(0,500)}))
 };
}"""
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for name, url in SITES.items():
        page = browser.new_page(locale="ja-JP", timezone_id="Asia/Tokyo")
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(700)
            info = page.evaluate(JS)
            print("DETAIL", name, "HTTP", resp.status if resp else "none", json.dumps(info, ensure_ascii=False)[:14000], flush=True)
        except Exception as e:
            print("DETAIL_FAILED", name, type(e).__name__, str(e)[:500], flush=True)
        finally:
            page.close()
    browser.close()
