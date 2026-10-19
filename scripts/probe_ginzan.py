"""Read-only 489ban grid status probe. No hidden values or personal data logged."""
from playwright.sync_api import sync_playwright
import json

SITES = {
    "ginzanso": "ginzanso", "kosekiya": "kosekiya",
    "kosekikan": "kosekikan", "notoya": "notoyaryokan", "takimikan": "takimikan",
}
SCRIPT = r"""() => {
 const tables=[...document.querySelectorAll('table')].filter(t=>[...t.querySelectorAll('th')]
     .some(h=> (h.innerText||'').replace(/\s+/g,'')==='13日'));
 const rows=tables.flatMap(t=>[...t.querySelectorAll('tr')].filter(r=>r.querySelectorAll('td').length===14)
     .map(r=>[...r.querySelectorAll('td')]));
 const cell = e => ({txt:(e.innerText||'').trim().slice(0,30),
    icons:[...e.querySelectorAll('i')].map(x=>x.className),
    links:[...e.querySelectorAll('a')].map(x=>({href:x.getAttribute('href'),title:x.getAttribute('title')})),
    classes:[...e.querySelectorAll('div,span')].map(x=>x.className).filter(Boolean).slice(0,4),
    html:e.outerHTML.replace(/\s+/g,' ').slice(0,900)
 });
 const all=rows.flat(),samples=new Map();
 for(const c of all){
    const result=cell(c);
    const key=JSON.stringify({icons:result.icons,links:result.links.length,txt:result.txt,classes:result.classes});
    if(!samples.has(key))samples.set(key,result);
 }
 return {title:document.title,rowCount:rows.length,
   day13:rows.map(r=>cell(r[12])).slice(0,12),
   uniqueSamples:[...samples.values()].slice(0,16)};
}"""
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    for name,client in SITES.items():
        for start in ("2026-12-01","2026-10-20"):
            url=f"https://reserve.489ban.net/client/{client}/0/plan/availability/room/stay?date={start}"
            page=browser.new_page(locale="ja-JP")
            try:
                resp=page.goto(url,wait_until="domcontentloaded",timeout=25000)
                page.wait_for_timeout(500)
                print("SIGNATURE",name,start,resp.status if resp else "-",json.dumps(page.evaluate(SCRIPT),ensure_ascii=False)[:12000],flush=True)
            except Exception as e:
                print("SIGNATURE_FAILED",name,start,type(e).__name__,str(e)[:250],flush=True)
            finally:page.close()
    browser.close()
