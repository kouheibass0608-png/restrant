"""Read-only positive-case probe for 6 Ginzan portal reservation results."""
from playwright.sync_api import sync_playwright
import json

SITES = ["showakan","yanadaya","matsumoto","kozankaku","itouya","fujiya"]
JS=r"""() => ({
 title:document.title,
 url:location.href,
 bodyStart:(document.body?.innerText||'').slice(0,1300),
 bodyEnd:(document.body?.innerText||'').slice(-1200),
 detailCount:(document.body?.innerText||'').split('詳細を見る').length-1,
 emptyPlans:(document.body?.innerText||'').includes('設定された条件でご利用できるプランがございません'),
 detailNodes:[...document.querySelectorAll('a,button,input[type=submit]')]
   .filter(e=>/詳細を見る|予約する|このプラン|このお部屋/.test((e.innerText||e.value||''))).slice(0,6)
   .map(e=>({tag:e.tagName, text:(e.innerText||e.value||'').trim().slice(0,50),
     href:e.getAttribute('href'), outer:e.outerHTML.slice(0,400)})),
 pageDate:(document.body?.innerText||'').includes('2026年11月17日'),
})"""
with sync_playwright() as p:
  browser=p.chromium.launch(headless=True)
  for name in SITES:
    page=browser.new_page(locale="ja-JP",timezone_id="Asia/Tokyo")
    try:
      resp=page.goto(f"https://www.nj-yoyaku.net/{name}/plan.aspx?TDT=20261117&NZ=2",wait_until="domcontentloaded",timeout=30000)
      page.wait_for_timeout(400)
      print("POSITIVE_PROBE",name,resp.status if resp else None,json.dumps(page.evaluate(JS),ensure_ascii=False)[:5500],flush=True)
    except Exception as e:print("POSITIVE_FAILED",name,type(e).__name__,str(e)[:350],flush=True)
    finally:page.close()
  browser.close()
