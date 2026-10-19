"""Read-only search interaction probe for remaining six Ginzan inns."""
from playwright.sync_api import sync_playwright
import json

SITES = ["showakan", "yanadaya", "matsumoto", "kozankaku", "itouya", "fujiya"]
JS = r"""() => ({
 url:location.href,
 date:document.querySelector('#date')?.value,
 party:document.querySelector('#ddnin')?.value,
 text:(document.body?.innerText||'').slice(-2400),
 searchNodes:[...document.querySelectorAll('button,a,input[type=submit],input[type=button]')]
    .filter(e=>/検索|空室|詳細|予約/.test((e.innerText||e.value||''))).slice(0,12)
    .map(e=>({tag:e.tagName,txt:(e.innerText||e.value||'').trim().slice(0,60),href:e.getAttribute('href'),html:e.outerHTML.slice(0,300)})),
 calendar:document.querySelector('table')?.outerHTML.slice(0,800),
})"""
with sync_playwright() as p:
  browser=p.chromium.launch(headless=True)
  for slug in SITES:
    page=browser.new_page(locale="ja-JP",timezone_id="Asia/Tokyo")
    try:
      response=page.goto(f"https://www.nj-yoyaku.net/{slug}/plan.aspx?PID=-1",wait_until="domcontentloaded",timeout=30000)
      if not response or response.status!=200:raise RuntimeError(f"HTTP {response.status if response else 'none'}")
      page.locator("#date").fill("2026-12-13")
      page.locator("#ddnin").select_option(index=2)
      page.wait_for_timeout(250)
      print("SET_FIELDS",slug,json.dumps(page.evaluate(JS),ensure_ascii=False)[:1900],flush=True)
      page.get_by_text("検索",exact=True).first.click(timeout=6000)
      page.wait_for_load_state("domcontentloaded",timeout=9000)
      page.wait_for_timeout(700)
      print("SEARCH_RESULT",slug,json.dumps(page.evaluate(JS),ensure_ascii=False)[:4500],flush=True)
    except Exception as e:
      print("SEARCH_FAILED",slug,type(e).__name__,str(e)[:400],flush=True)
    finally:page.close()
  browser.close()
