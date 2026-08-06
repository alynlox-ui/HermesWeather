import json
import os
import time

import requests
import websocket

DEBUG = os.environ.get("E2E_DEBUG", "http://127.0.0.1:9236")


def wait_for_tab():
    for _ in range(60):
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
evaluate("document.querySelector('[data-view=study]').click(); true")
wait_js("document.getElementById('studyView').classList.contains('active-view')")
wait_js("document.getElementById('studyFrame').contentDocument && document.getElementById('studyFrame').contentDocument.readyState === 'complete'")
wait_js("!!(document.getElementById('studyFrame').contentDocument && document.getElementById('studyFrame').contentDocument.getElementById('tab-today'))")

initial = evaluate("(function(){var f=document.getElementById('studyFrame'),w=f.contentWindow,d=f.contentDocument,r=f.getBoundingClientRect(),outer=document.querySelector('.sidebar').getBoundingClientRect(),saved=JSON.parse(w.localStorage.getItem('wb_study_goal_tracker_data'));return {version:document.querySelector('meta[name=app-version]').content,active:document.getElementById('studyView').classList.contains('active-view'),crumb:document.querySelector('.crumb b').textContent,status:document.querySelector('.online').textContent.trim(),navCount:document.querySelectorAll('.nav .nav-item').length,frameTitle:d.title,goalCount:saved.goals.length,today:d.getElementById('tab-today').classList.contains('active'),frameBottom:Math.round(r.bottom),outerTop:Math.round(outer.top),viewport:innerHeight}})()")
assert initial["version"] == "1.9.0-study-goals", initial
assert initial["active"] and initial["crumb"] == "学习目标", initial
assert initial["navCount"] == 4 and initial["frameTitle"] == "学习目标管理台", initial
assert initial["goalCount"] >= 3 and initial["today"], initial
assert initial["frameBottom"] <= initial["outerTop"] + 2, initial

created = evaluate("(function(){var f=document.getElementById('studyFrame'),w=f.contentWindow,d=f.contentDocument;w.openGoalModal();d.getElementById('g-name').value='E2E 学习目标';d.getElementById('g-unit').value='章';d.getElementById('g-total').value='30';d.getElementById('g-deadline').value=w.dateToStr(w.addDays(new Date(),30));w.saveGoal(null);var saved=JSON.parse(w.localStorage.getItem('wb_study_goal_tracker_data')),matches=saved.goals.filter(function(x){return x.name==='E2E 学习目标'}),g=matches[matches.length-1];w.addRecord(g.id,w.todayStr(),5,25,false);saved=JSON.parse(w.localStorage.getItem('wb_study_goal_tracker_data'));return {id:g.id,goals:saved.goals.length,records:saved.records.filter(function(x){return x.goalId===g.id}).length,completed:saved.records.filter(function(x){return x.goalId===g.id}).reduce(function(n,x){return n+x.amount},0),stored:saved.goals.some(function(x){return x.name==='E2E 学习目标'})}})()")
assert created["records"] == 1 and created["completed"] == 5 and created["stored"], created

for tab in ("board", "weekly", "mine", "today"):
    state = evaluate("(function(){var f=document.getElementById('studyFrame'),w=f.contentWindow,d=f.contentDocument;w.switchTab('" + tab + "');return {tab:d.getElementById('page-title').textContent,active:d.getElementById('tab-" + tab + "').classList.contains('active')}})()")
    assert state["active"], (tab, state)

evaluate("showView('weather'); showView('study'); true")
goal_id = json.dumps(created["id"])
returned = evaluate("(function(){var f=document.getElementById('studyFrame'),w=f.contentWindow,saved=JSON.parse(w.localStorage.getItem('wb_study_goal_tracker_data'));return {active:document.getElementById('studyView').classList.contains('active-view'),goal:saved.goals.some(function(x){return x.name==='E2E 学习目标';}),stored:saved.records.some(function(x){return x.goalId===" + goal_id + ";})};})()")
assert returned["active"] and returned["goal"] and returned["stored"], returned

evaluate("document.getElementById('studyFrame').src='./study-goal-tracker.html?reload_e2e='+Date.now(); true")
wait_js("document.getElementById('studyFrame').contentWindow.location.search.indexOf('reload_e2e=') >= 0 && document.getElementById('studyFrame').contentDocument.readyState === 'complete'")
wait_js("!!document.getElementById('studyFrame').contentDocument.getElementById('tab-today') && document.getElementById('studyFrame').contentDocument.getElementById('tab-today').innerText.length > 100")
reloaded = evaluate("(function(){var f=document.getElementById('studyFrame'),w=f.contentWindow,d=f.contentDocument,saved=JSON.parse(w.localStorage.getItem('wb_study_goal_tracker_data'));return {active:d.getElementById('tab-today').classList.contains('active'),content:d.getElementById('tab-today').innerText.length,goal:saved.goals.some(function(x){return x.name==='E2E 学习目标';}),activeTab:saved.activeTab};})()")
assert reloaded["active"] and reloaded["content"] > 100 and reloaded["goal"] and reloaded["activeTab"] == "today", reloaded

print(json.dumps({"initial": initial, "created": created, "returned": returned, "reloaded": reloaded}, ensure_ascii=False))
ws.close()
