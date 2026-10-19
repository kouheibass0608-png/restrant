"""Read-only probe of non-489ban Ginzan reservation sites (no booking, no login)."""
from playwright.sync_api import sync_playwright
import json

SITES = ["showakan", "yanadaya", "matsumoto", "kozankaku", "itouya", "fujiya"]
JS = r"""() => ({
 title:document.title,
 url:location.href,
 text:(document.body?.innerText||'').slice(0,1900),
 forms:[...document.querySelectorAll('form')].map(f=>({action:f.getAttribute('action'),method:f.method})).slice(0,3),
 editable:[...document.querySelectorAll('input:not([type=hidden]),select,button')]
    .slice(0,35).map(e=>({tag:e.tagName,name:e.name,id:e.id,type:e.type,
      placeholder:e.getAttribute('placeholder'),label:(e.innerText||e.value||'').trim().slice(0,70)})),
 links:[...document.querySelectorAll('a[href]')].filter(a=>/空室|予約|月|カレンダー|詳しく|プラン/.test(a.innerText||''))
    .slice(0,30).map(a=>({text:(a.innerText||'').trim().slice(0,60),href:a.href})),
 tables:[...document.querySelectorAll('table')].slice(0,4).map(t=>({class:t.className,
   rows:t.querySelectorAll('tr').length,sample:(t.innerText||'').slice(0,300)}))
})"""
with sync_playwright() as p:
  browser=p.chromium.launch(headless=True)
  for slug in SITES:
    url=f"https://www.nj-yoyaku.net/{slug}/plan.aspx?PID=-1"
    page=browser.new_page(locale="ja-JP",timezone_id="Asia/Tokyo")
    try:
      response=page.goto(url,wait_until="domcontentloaded",timeout=30000)
      page.wait_for_timeout(500)
      info=page.evaluate(JS)
      print("EXTRA",slug,response.status if response else None,json.dumps(info,ensure_ascii=False)[:10000],flush=True)
    except Exception as e:
      print("EXTRA_FAILED",slug,type(e).__name__,str(e)[:300],flush=True)
    finally:page.close()
  browser.close()
