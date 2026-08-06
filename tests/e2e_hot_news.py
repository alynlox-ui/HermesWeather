import json
import os
import time

import requests
import websocket

DEBUG = os.environ.get("E2E_DEBUG", "http://127.0.0.1:9224")


def wait_for_tab():
    for _ in range(40):
        try:
            tabs = requests.get(DEBUG + "/json", timeout=2).json()
            for tab in tabs:
                if tab.get("type") == "page":
                    return tab["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.25)
    raise RuntimeError("Chrome DevTools tab not ready")


ws = websocket.create_connection(wait_for_tab(), timeout=10)
next_id = 0


def command(method, params=None):
    global next_id
    next_id += 1
    ident = next_id
    ws.send(json.dumps({"id": ident, "method": method, "params": params or {}}))
    while True:
        message = json.loads(ws.recv())
        if message.get("id") == ident:
            if "error" in message:
                raise RuntimeError(message["error"])
            return message.get("result", {})


def evaluate(expression):
    result = command("Runtime.evaluate", {
        "expression": expression,
        "awaitPromise": True,
        "returnByValue": True,
    })
    if result.get("exceptionDetails"):
        raise RuntimeError(result["exceptionDetails"])
    return result.get("result", {}).get("value")


def wait_js(expression, timeout=30):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = evaluate(expression)
        if last:
            return last
        time.sleep(0.25)
    raise AssertionError(f"Timed out waiting for: {expression}; last={last!r}")


command("Runtime.enable")
wait_js("document.readyState === 'complete'")
# Local regression runs can force the same-origin snapshot to fail and exercise CDN fallback.
if os.environ.get("E2E_FORCE_FALLBACK", "1") == "1":
    evaluate("NEWS_SNAPSHOT_URLS[0]='./missing-hot-news.json'; newsSnapshot=null; true")
evaluate("showView('news'); document.querySelector('[data-news-source=ai]').click(); true")
count = wait_js("document.querySelectorAll('#newsList .news-item').length", timeout=45)
state = evaluate("({count:newsItems.length, visible:document.querySelectorAll('#newsList .news-item').length, source:document.getElementById('newsSourceLabel').textContent, first:document.querySelector('#newsList .news-copy b').textContent, firstCover:newsItems[0]&&newsItems[0].cover, articleApi:NEWS_ARTICLE_API, hostname:location.hostname})")
assert state["count"] >= 30, state
assert state["visible"] == 10, state
assert state["source"] == "AI专区", state
assert state["firstCover"].startswith("http"), state
if state["hostname"].endswith("edgeone.cool"):
    assert state["articleApi"] == "https://hermes-weather-news-alynlox-ui.onrender.com/api/news/article", state

evaluate("document.querySelector('#newsList .news-item').click(); true")
wait_js("document.getElementById('newsReaderModal').classList.contains('open')")
wait_js("!document.querySelector('#newsArticleBody .news-reader-placeholder') && (document.querySelectorAll('#newsArticleBody .news-article-cover,#newsArticleBody .news-article-image').length || document.querySelectorAll('#newsArticleBody p').length)", timeout=60)
wait_js("Array.from(document.querySelectorAll('#newsArticleBody .news-article-cover,#newsArticleBody .news-article-image')).some(function(img){return img.complete&&img.naturalWidth>0})", timeout=45)
modal = evaluate("(function(){let body=document.getElementById('newsArticleBody'),img=body.querySelector('.news-article-image'),paragraphs=Array.from(body.querySelectorAll('p'));return {open:document.getElementById('newsReaderModal').classList.contains('open'),hidden:document.getElementById('newsReaderModal').getAttribute('aria-hidden'),title:document.getElementById('newsArticleTitle').textContent,locked:document.body.classList.contains('news-reader-open'),imageCount:body.querySelectorAll('.news-article-cover,.news-article-image').length,loadedImages:Array.from(body.querySelectorAll('.news-article-cover,.news-article-image')).filter(function(node){return node.complete&&node.naturalWidth>0}).length,paragraphs:paragraphs.length,imageInline:!!img&&paragraphs.some(function(p){return p.compareDocumentPosition(img)&Node.DOCUMENT_POSITION_FOLLOWING})&&paragraphs.some(function(p){return p.compareDocumentPosition(img)&Node.DOCUMENT_POSITION_PRECEDING})}})()")
assert modal["open"] and modal["hidden"] == "false" and modal["locked"], modal
assert modal["title"] == state["first"], (modal, state)
assert modal["imageCount"] >= 1 and modal["loadedImages"] >= 1 and modal["paragraphs"] >= 1 and modal["imageInline"], modal

evaluate("document.getElementById('newsReaderClose').click(); true")
closed = evaluate("({open:document.getElementById('newsReaderModal').classList.contains('open'), hidden:document.getElementById('newsReaderModal').getAttribute('aria-hidden'), body:document.getElementById('newsArticleBody').innerHTML})")
assert not closed["open"] and closed["hidden"] == "true" and closed["body"] == "", closed

evaluate("document.querySelector('[data-news-source=\"36kr\"]').click(); true")
wait_js("document.getElementById('newsSourceLabel').textContent==='36氪' && document.querySelectorAll('#newsList .news-item').length")
k36 = evaluate("({count:newsItems.length, first:newsItems[0].title, cover:newsItems[0].cover})")
assert k36["count"] >= 20 and k36["cover"].startswith("http"), k36
evaluate("document.querySelector('#newsList .news-item').click(); true")
wait_js("!document.querySelector('#newsArticleBody .news-reader-placeholder') && document.querySelectorAll('#newsArticleBody .news-article-cover,#newsArticleBody .news-article-image').length", timeout=60)
wait_js("Array.from(document.querySelectorAll('#newsArticleBody .news-article-cover,#newsArticleBody .news-article-image')).some(function(img){return img.complete&&img.naturalWidth>0})", timeout=45)
k36_reader = evaluate("({title:document.getElementById('newsArticleTitle').textContent, images:document.querySelectorAll('#newsArticleBody .news-article-cover,#newsArticleBody .news-article-image').length, loadedImages:Array.from(document.querySelectorAll('#newsArticleBody .news-article-cover,#newsArticleBody .news-article-image')).filter(function(img){return img.complete&&img.naturalWidth>0}).length, paragraphs:document.querySelectorAll('#newsArticleBody p').length})")
assert k36_reader["title"] == k36["first"] and k36_reader["images"] >= 1 and k36_reader["loadedImages"] >= 1 and k36_reader["paragraphs"] >= 1, (k36, k36_reader)
evaluate("document.getElementById('newsReaderClose').click(); true")

print(json.dumps({"ai_zone": state, "qbitai_reader": modal, "reader_closed": closed, "kr36": k36, "kr36_reader": k36_reader}, ensure_ascii=False))
ws.close()
