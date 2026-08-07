import base64
import json
import os
import time
from pathlib import Path

import requests
import websocket

DEBUG = os.environ.get("E2E_DEBUG", "http://127.0.0.1:9262")
WIDTH = int(os.environ.get("E2E_WIDTH", "390"))
HEIGHT = int(os.environ.get("E2E_HEIGHT", "844"))
SCREENSHOT = os.environ.get("E2E_SCREENSHOT", "")


def wait_for_tab():
    for _ in range(80):
        try:
            tabs = requests.get(DEBUG + "/json", timeout=2).json()
            for tab in tabs:
                if tab.get("type") == "page" and str(tab.get("url", "")).startswith(("http://", "https://")):
                    return tab["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.25)
    raise RuntimeError("Chrome DevTools tab not ready")


ws = websocket.create_connection(wait_for_tab(), timeout=15)
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
    result = command("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True})
    if result.get("exceptionDetails"):
        raise RuntimeError(result["exceptionDetails"])
    return result.get("result", {}).get("value")


def wait_js(expression, timeout=40):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = evaluate(expression)
        if last:
            return last
        time.sleep(0.25)
    raise AssertionError(f"Timed out waiting for {expression}; last={last!r}")


command("Runtime.enable")
command("Page.enable")
command("Emulation.setDeviceMetricsOverride", {
    "width": WIDTH, "height": HEIGHT, "deviceScaleFactor": 1,
    "mobile": WIDTH <= 680, "screenWidth": WIDTH, "screenHeight": HEIGHT,
})
command("Page.reload", {"ignoreCache": True})
wait_js("document.readyState === 'complete'")
evaluate("showView('sites'); true")
wait_js("document.getElementById('sitesView').classList.contains('active-view')")
wait_js("document.querySelectorAll('.site-card').length === 114")
evaluate("document.querySelectorAll('.site-category').forEach(function(s){s.style.display='block'});document.querySelectorAll('.site-logo').forEach(function(img){img.loading='eager'});true")
wait_js("Array.from(document.querySelectorAll('.site-logo')).every(function(img){return img.complete})")
evaluate("document.querySelectorAll('.site-category').forEach(function(s){s.style.display=''});filterSites('');true")

state = evaluate("""(function(){
 var sections=Array.from(document.querySelectorAll('.site-category'));
 var counts={};sections.forEach(function(s){counts[s.dataset.sitePanel]=s.querySelectorAll('.site-card').length});
 var imgs=Array.from(document.querySelectorAll('.site-logo'));
 var links=Array.from(document.querySelectorAll('.site-card a'));
 var first=document.querySelector('.site-card').getBoundingClientRect();
 var grid=getComputedStyle(document.querySelector('.site-grid')).gridTemplateColumns.split(' ').filter(Boolean).length;
 return {version:document.querySelector('meta[name=app-version]').content,total:document.querySelectorAll('.site-card').length,
 counts:counts,images:imgs.length,loaded:imgs.filter(function(x){return x.naturalWidth>0&&x.naturalHeight>0}).length,
 localIcons:imgs.every(function(x){return new URL(x.src).origin===location.origin&&x.src.indexOf('/assets/site-icons/')>=0}),
 safeLinks:links.every(function(a){return a.protocol==='https:'&&a.target==='_blank'&&a.rel.indexOf('noopener')>=0&&a.rel.indexOf('noreferrer')>=0}),
 overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth,gridColumns:grid,cardWidth:Math.round(first.width),
 countLabel:document.getElementById('siteSearchCount').textContent,hostname:location.hostname};
})()""")
assert state["version"] == "1.15.0-niche-sites-icons", state
assert state["total"] == 114 and state["images"] == 114 and state["loaded"] == 114 and state["localIcons"], state
assert state["counts"] == {"games": 24, "office": 18, "dev": 18, "design": 18, "media": 18, "utilities": 18}, state
assert state["safeLinks"] and state["overflow"] == 0 and state["countLabel"] == "114 款软件", state
if WIDTH > 900:
    assert state["gridColumns"] == 3, state
else:
    assert state["gridColumns"] == 1 and state["cardWidth"] >= WIDTH - 50, state

searches = {}
for query, expected, count in (("steem", "Steam", 1), ("flow launcher", "Flow Launcher", 1), ("像素画", "Aseprite", 1), ("minecraft", None, 4)):
    result = evaluate("(function(){var q=" + json.dumps(query) + ";var n=filterSites(q);var names=Array.from(document.querySelectorAll('.site-card:not([hidden]) h3')).map(function(x){return x.textContent});return {count:n,names:names,empty:document.getElementById('siteSearchEmpty').classList.contains('show')};})()")
    assert result["count"] == count, (query, result)
    if expected:
        assert result["names"] == [expected], (query, result)
    assert not result["empty"], (query, result)
    searches[query] = result

empty = evaluate("(function(){var n=filterSites('zzzz-no-match');return {count:n,shown:document.getElementById('siteSearchEmpty').classList.contains('show')};})()")
assert empty == {"count": 0, "shown": True}, empty
evaluate("(async function(){document.getElementById('siteSearch').value='';filterSites('');window.scrollTo(0,0);await new Promise(function(resolve){setTimeout(resolve,450)});return true})()")

if SCREENSHOT:
    shot = command("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    Path(SCREENSHOT).write_bytes(base64.b64decode(shot["data"]))

print(json.dumps({"directory": state, "searches": searches, "empty": empty, "screenshot": SCREENSHOT}, ensure_ascii=False))
ws.close()
