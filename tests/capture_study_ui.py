import base64
import json
import time
from pathlib import Path

import requests
import websocket


def capture(port, path, prepare=None):
    tabs = requests.get(f"http://127.0.0.1:{port}/json", timeout=5).json()
    tab = next(x for x in tabs if x.get("type") == "page" and x.get("url", "").startswith("http"))
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=10)
    msg_id = 0

    def call(method, params=None):
        nonlocal msg_id
        msg_id += 1
        ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            response = json.loads(ws.recv())
            if response.get("id") == msg_id:
                return response

    call("Runtime.enable")
    call("Page.enable")
    if port == 9242:
        call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True, "screenWidth": 390, "screenHeight": 844})
    call("Page.reload", {"ignoreCache": True})
    time.sleep(2)
    if prepare:
        call("Runtime.evaluate", {"expression": prepare, "awaitPromise": True, "returnByValue": True})
        time.sleep(2)
    if port == 9243:
        inspected = call("Runtime.evaluate", {"expression": "(function(){var f=document.getElementById('studyFrame'),d=f.contentDocument,sh=d.querySelector('.section-header'),st=d.querySelector('.section-title'),sec=d.querySelector('.section'),main=d.querySelector('.main');function r(x){var b=x.getBoundingClientRect();return {x:b.x,y:b.y,w:b.width,h:b.height,display:getComputedStyle(x).display,overflow:getComputedStyle(x).overflow}}return {inner:[innerWidth,innerHeight],frame:r(f),main:r(main),section:r(sec),header:r(sh),title:r(st),text:st.textContent,innerScrollHeight:d.documentElement.scrollHeight,innerScrollY:f.contentWindow.scrollY,parentScrollHeight:document.documentElement.scrollHeight}})()", "returnByValue": True})
        layout = inspected["result"]["result"]["value"]
        print("DESKTOP_LAYOUT", layout)
        assert abs(layout["frame"]["h"] - layout["innerScrollHeight"]) <= 3, layout
        assert layout["innerScrollY"] == 0 and layout["parentScrollHeight"] > layout["inner"][1], layout
        assert layout["title"]["h"] < 30 and layout["title"]["w"] > 100, layout
    result = call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    Path(path).write_bytes(base64.b64decode(result["result"]["data"]))
    ws.close()
    print(path)


capture(9242, r"F:\Hermes\weather_app\study-ui-mobile.png", "(async()=>{showView('study');let f=document.getElementById('studyFrame');for(let i=0;i<50&&!f.contentDocument?.getElementById('tab-today');i++)await new Promise(r=>setTimeout(r,100));return true})()")
capture(
    9243,
    r"F:\Hermes\weather_app\study-ui-desktop.png",
    """(async()=>{showView('study');let f=document.getElementById('studyFrame');for(let i=0;i<50&&!f.contentDocument?.getElementById('tab-today');i++)await new Promise(r=>setTimeout(r,100));let w=f.contentWindow,d=f.contentDocument,s=JSON.parse(w.localStorage.getItem('wb_study_goal_tracker_data')||'null');if(!s||!s.goals.length){w.openGoalModal();d.getElementById('g-name').value='深度学习课程';d.getElementById('g-unit').value='节';d.getElementById('g-total').value='40';d.getElementById('g-deadline').value=w.dateToStr(w.addDays(new Date(),45));w.saveGoal(null);}return true})()""",
)
