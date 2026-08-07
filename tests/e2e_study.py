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
                if tab.get("type") == "page" and str(tab.get("url", "")).startswith(("http://", "https://")):
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


def click_selector(selector):
    target = evaluate("(function(){var b=document.querySelector(" + json.dumps(selector) + "),r=b.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2,h=document.elementFromPoint(x,y);return {x:x,y:y,hitView:h&&h.closest('[data-view]')&&h.closest('[data-view]').getAttribute('data-view'),hitId:h&&h.id};})()")
    command("Input.dispatchMouseEvent", {"type": "mousePressed", "x": target["x"], "y": target["y"], "button": "left", "clickCount": 1})
    command("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": target["x"], "y": target["y"], "button": "left", "clickCount": 1})
    return target


command("Runtime.enable")
command("Page.enable")
command("Emulation.setDeviceMetricsOverride", {
    "width": 390,
    "height": 844,
    "deviceScaleFactor": 1,
    "mobile": True,
    "screenWidth": 390,
    "screenHeight": 844,
})
command("Page.reload", {"ignoreCache": True})
wait_js("document.readyState === 'complete'")
evaluate("document.querySelector('[data-view=study]').click(); true")
wait_js("document.getElementById('studyView').classList.contains('active-view')")
wait_js("document.getElementById('studyFrame').contentDocument && document.getElementById('studyFrame').contentDocument.readyState === 'complete'")
wait_js("!!(document.getElementById('studyFrame').contentDocument && document.getElementById('studyFrame').contentDocument.getElementById('tab-today'))")

evaluate("localStorage.removeItem('wb_study_goal_tracker_data');document.getElementById('studyFrame').src='./study-goal-tracker.html?fresh_e2e='+Date.now();true")
wait_js("document.getElementById('studyFrame').contentWindow.location.search.indexOf('fresh_e2e=') >= 0 && document.getElementById('studyFrame').contentDocument.readyState === 'complete'")
fresh = evaluate("(function(){var w=document.getElementById('studyFrame').contentWindow,s=JSON.parse(w.localStorage.getItem('wb_study_goal_tracker_data'));return {goals:s.goals.length,records:s.records.length,version:s.version};})()")
assert fresh == {"goals": 0, "records": 0, "version": 3}, fresh

legacy = json.dumps({
    "goals": [
        {"id": "ex-1", "name": "旧示例一", "unit": "个", "total": 10, "deadline": "2026-12-31", "isExample": True},
        {"id": "ex-9", "name": "旧示例二", "unit": "页", "total": 20, "deadline": "2026-12-31"},
        {"id": "real-1", "name": "用户真实目标", "unit": "章", "total": 8, "deadline": "2026-12-31"},
        {"id": "toString", "name": "特殊ID真实目标", "unit": "次", "total": 5, "deadline": "2026-12-31"},
    ],
    "records": [
        {"id": "sample-record", "goalId": "ex-1", "date": "2026-08-05", "amount": 10},
        {"id": "real-record", "goalId": "real-1", "date": "2026-08-05", "amount": 2},
        {"id": "special-record", "goalId": "toString", "date": "2026-08-05", "amount": 1},
    ],
    "weeklyReports": {}, "activeTab": "today", "version": 2,
}, ensure_ascii=False)
evaluate("localStorage.setItem('wb_study_goal_tracker_data'," + json.dumps(legacy) + ");document.getElementById('studyFrame').src='./study-goal-tracker.html?migration_e2e='+Date.now();true")
wait_js("document.getElementById('studyFrame').contentWindow.location.search.indexOf('migration_e2e=') >= 0 && document.getElementById('studyFrame').contentDocument.readyState === 'complete'")
wait_js("!!document.getElementById('studyFrame').contentDocument.getElementById('tab-today')")

initial = evaluate("(function(){var f=document.getElementById('studyFrame'),w=f.contentWindow,d=f.contentDocument,drawer=document.querySelector('.sidebar').getBoundingClientRect(),toggle=document.getElementById('dockToggle').getBoundingClientRect(),saved=JSON.parse(w.localStorage.getItem('wb_study_goal_tracker_data')),svg=document.querySelector('[data-view=study] svg'),css=getComputedStyle(svg);return {version:document.querySelector('meta[name=app-version]').content,active:document.getElementById('studyView').classList.contains('active-view'),crumb:document.querySelector('.crumb b').textContent,status:document.querySelector('.online').textContent.trim(),navCount:document.querySelectorAll('.nav .nav-item').length,frameTitle:d.title,goalCount:saved.goals.length,recordCount:saved.records.length,dataVersion:saved.version,noSamples:saved.goals.every(function(g){return !g.isExample&&!/^ex-\\d+$/.test(String(g.id||''));}),realGoal:saved.goals.some(function(g){return g.id==='real-1';}),realRecord:saved.records.some(function(x){return x.id==='real-record';}),specialGoal:saved.goals.some(function(g){return g.id==='toString';}),specialRecord:saved.records.some(function(x){return x.id==='special-record';}),icon:{width:css.width,height:css.height,viewBox:svg.getAttribute('viewBox'),paths:svg.querySelectorAll('path,rect').length},today:d.getElementById('tab-today').classList.contains('active'),drawerRight:Math.round(drawer.right),toggleSize:[Math.round(toggle.width),Math.round(toggle.height)],drawerOpen:document.body.classList.contains('dock-open')}})()")
assert initial["version"] == "1.13.0-sites-search", initial
assert initial["active"] and initial["crumb"] == "学习目标", initial
assert initial["navCount"] == 6 and initial["frameTitle"] == "学习目标管理台", initial
assert initial["goalCount"] == 2 and initial["recordCount"] == 2 and initial["dataVersion"] == 3, initial
assert initial["noSamples"] and initial["realGoal"] and initial["realRecord"] and initial["specialGoal"] and initial["specialRecord"] and initial["today"], initial
assert initial["icon"] == {"width": "24px", "height": "24px", "viewBox": "0 0 24 24", "paths": 4}, initial
assert initial["drawerRight"] <= 0 and initial["toggleSize"] == [44, 44] and not initial["drawerOpen"], initial

visual = evaluate("(function(){var d=document.getElementById('studyFrame').contentDocument,w=document.getElementById('studyFrame').contentWindow,nav=d.querySelector('.topbar-nav'),buttons=Array.prototype.slice.call(nav.querySelectorAll('.nav-item')),navRect=nav.getBoundingClientRect(),buttonRects=buttons.map(function(b){return b.getBoundingClientRect();});return {body:getComputedStyle(d.body).backgroundColor,card:getComputedStyle(d.querySelector('.card')).backgroundColor,sidebar:getComputedStyle(d.querySelector('.sidebar')).display,topnav:getComputedStyle(nav).display,bottomnav:getComputedStyle(d.querySelector('.bottom-nav')).display,accent:getComputedStyle(d.documentElement).getPropertyValue('--pri').trim(),text:getComputedStyle(d.body).color,pageTitle:getComputedStyle(d.getElementById('page-title')).display,tabCount:buttons.length,tabHeights:buttonRects.map(function(r){return Math.round(r.height);}),tabWidths:buttonRects.map(function(r){return Math.round(r.width);}),navWidth:Math.round(navRect.width),mainWidth:Math.round(d.querySelector('.main').getBoundingClientRect().width)}})()")
assert visual["body"] == "rgb(8, 10, 13)" and visual["sidebar"] == "none" and visual["topnav"] == "flex" and visual["bottomnav"] == "none", visual
assert visual["accent"] == "#b8ff35" and visual["text"] == "rgb(243, 245, 247)", visual
assert visual["pageTitle"] == "none" and visual["tabCount"] == 4, visual
assert min(visual["tabHeights"]) >= 42 and max(visual["tabWidths"]) - min(visual["tabWidths"]) <= 1, visual
assert visual["navWidth"] >= visual["mainWidth"] - 34, visual

toggle_hit = click_selector("#dockToggle")
assert toggle_hit["hitId"] == "dockToggle", toggle_hit
wait_js("document.body.classList.contains('dock-open') && document.querySelector('.sidebar').getBoundingClientRect().left >= -1")
drawer = evaluate("(function(){var labels=Array.prototype.map.call(document.querySelectorAll('.nav .nav-item'),function(x){return x.getAttribute('data-label')});var r=document.querySelector('.sidebar').getBoundingClientRect();return {labels:labels,left:Math.round(r.left),width:Math.round(r.width),expanded:document.getElementById('dockToggle').getAttribute('aria-expanded')};})()")
assert drawer["labels"] == ["天气", "热点", "学习", "网络", "官网", "设置"] and -1 <= drawer["left"] <= 0 and drawer["width"] >= 250 and drawer["expanded"] == "true", drawer
settings_hit = click_selector("[data-view=settings]")
assert settings_hit["hitView"] == "settings", settings_hit
wait_js("document.getElementById('settingsView').classList.contains('active-subpanel') && Math.abs(document.getElementById('settingsView').getBoundingClientRect().top) <= 80")
dock_settings = evaluate("(function(){var b=document.querySelector('[data-view=settings]'),p=document.getElementById('settingsView'),rect=p.getBoundingClientRect();return {active:b.classList.contains('active'),crumb:document.querySelector('.crumb b').textContent,settingsPanel:p.classList.contains('active-subpanel'),weatherHost:document.getElementById('weatherSuiteView').classList.contains('active-view'),oldSubtab:!!document.querySelector('[data-weather-tab=settings]'),dockCount:document.querySelectorAll('.nav .nav-item').length,panelTop:Math.round(rect.top),scrollY:Math.round(scrollY),drawerClosed:!document.body.classList.contains('dock-open'),weatherControls:!!document.getElementById('autoSearch')||!!document.getElementById('defaultPlace')||!!document.querySelector('[data-unit]')};})()")
assert dock_settings["active"] and dock_settings["crumb"] == "工具箱设置" and dock_settings["settingsPanel"] and dock_settings["weatherHost"], dock_settings
assert not dock_settings["oldSubtab"] and dock_settings["dockCount"] == 6 and dock_settings["drawerClosed"] and not dock_settings["weatherControls"], dock_settings
assert 0 <= dock_settings["panelTop"] <= 80 and dock_settings["scrollY"] > 0, dock_settings
settings_scroll = evaluate("(async function(){var root=document.documentElement,old=root.style.scrollBehavior;root.style.scrollBehavior='auto';root.scrollTop=root.scrollHeight;await new Promise(function(r){requestAnimationFrame(function(){requestAnimationFrame(r);});});var rows=document.querySelectorAll('#settingsView .setting-row'),last=rows[rows.length-1].getBoundingClientRect(),result={scrollY:Math.round(scrollY),max:root.scrollHeight-innerHeight,lastBottom:Math.round(last.bottom),viewport:innerHeight};root.style.scrollBehavior=old;return result;})()")
assert settings_scroll["scrollY"] == settings_scroll["max"] and settings_scroll["lastBottom"] <= settings_scroll["viewport"], settings_scroll

click_selector("#dockToggle")
wait_js("document.body.classList.contains('dock-open') && document.querySelector('.sidebar').getBoundingClientRect().left >= -1")
sites_hit = click_selector("[data-view=sites]")
assert sites_hit["hitView"] == "sites", sites_hit
wait_js("document.getElementById('sitesView').classList.contains('active-view')")
sites = evaluate("(function(){var tabs=document.querySelectorAll('.site-tab'),cards=document.querySelectorAll('.site-card'),office=document.querySelector('[data-site-category=office]');office.click();return {crumb:document.querySelector('.crumb b').textContent,tabs:tabs.length,cards:cards.length,activePanel:document.querySelector('.site-category.active').getAttribute('data-site-panel'),officeCards:document.querySelectorAll('[data-site-panel=office] .site-card').length,links:Array.prototype.every.call(document.querySelectorAll('.site-actions a'),function(a){return a.protocol==='https:'&&a.target==='_blank'&&a.rel.indexOf('noopener')>=0;})};})()")
assert sites["crumb"] == "官网合集" and sites["tabs"] == 6 and sites["cards"] == 36 and sites["activePanel"] == "office" and sites["officeCards"] == 6 and sites["links"], sites
fuzzy = evaluate("(function(){function run(q){var i=document.getElementById('siteSearch');i.value=q;i.dispatchEvent(new Event('input',{bubbles:true}));return {count:Array.prototype.filter.call(document.querySelectorAll('.site-card'),function(x){return !x.hidden}).length,names:Array.prototype.filter.call(document.querySelectorAll('.site-card'),function(x){return !x.hidden}).map(function(x){return x.querySelector('h3').textContent}),empty:document.getElementById('siteSearchEmpty').classList.contains('show')};}return {vscode:run('vscode'),typo:run('steem'),office:run('办公'),none:run('绝对不存在的软件xyz')};})()")
assert fuzzy["vscode"]["names"] == ["Visual Studio Code"], fuzzy
assert fuzzy["typo"]["names"] == ["Steam"], fuzzy
assert fuzzy["office"]["count"] == 6, fuzzy
assert fuzzy["none"]["count"] == 0 and fuzzy["none"]["empty"], fuzzy
evaluate("document.getElementById('siteSearchClear').click();true")
evaluate("document.querySelector('[data-view=study]').click();true")
wait_js("document.getElementById('studyView').classList.contains('active-view')")
weekly_icons = evaluate("(function(){var d=document.getElementById('studyFrame').contentDocument,b=d.querySelector('[data-tab=weekly]');b.click();var icons=Array.prototype.slice.call(d.querySelectorAll('.weekly-four-item .form-label svg'));var result={weeklyActive:d.getElementById('tab-weekly').classList.contains('active'),activeButtons:d.querySelectorAll('.topbar-nav .nav-item.active').length,count:icons.length,sizes:icons.map(function(x){var r=x.getBoundingClientRect();return [Math.round(r.width),Math.round(r.height)];})};d.querySelector('[data-tab=today]').click();return result;})()")
assert weekly_icons["weeklyActive"] and weekly_icons["activeButtons"] == 1 and weekly_icons["count"] == 4, weekly_icons
assert weekly_icons["sizes"] == [[14, 14], [14, 14], [14, 14], [14, 14]], weekly_icons

evaluate("document.body.classList.remove('theme-dark');document.body.classList.add('theme-light');document.documentElement.style.setProperty('--green','#51d9ff');true")
wait_js("document.getElementById('studyFrame').contentDocument.body.classList.contains('host-light') && getComputedStyle(document.getElementById('studyFrame').contentDocument.documentElement).getPropertyValue('--pri').trim()==='#51d9ff'")
light_theme = evaluate("(function(){var d=document.getElementById('studyFrame').contentDocument;return {body:getComputedStyle(d.body).backgroundColor,text:getComputedStyle(d.body).color,accent:getComputedStyle(d.documentElement).getPropertyValue('--pri').trim()}})()")
assert light_theme == {"body": "rgb(233, 237, 242)", "text": "rgb(23, 27, 32)", "accent": "#51d9ff"}, light_theme
evaluate("document.body.classList.remove('theme-light');document.body.classList.add('theme-dark');document.documentElement.style.setProperty('--green','#b8ff35');true")
wait_js("!document.getElementById('studyFrame').contentDocument.body.classList.contains('host-light')")

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

scroll_check = evaluate("(async function(){var f=document.getElementById('studyFrame'),w=f.contentWindow,d=f.contentDocument;w.scrollTo(0,d.documentElement.scrollHeight);await new Promise(function(r){requestAnimationFrame(function(){requestAnimationFrame(r);});});var all=d.querySelectorAll('#tab-today .btn'),last=all[all.length-1],r=last.getBoundingClientRect();return {scrollY:w.scrollY,max:d.documentElement.scrollHeight-w.innerHeight,lastBottom:Math.round(r.bottom),innerHeight:w.innerHeight};})()")
assert scroll_check["max"] > 0 and scroll_check["scrollY"] > 0, scroll_check
assert scroll_check["lastBottom"] <= scroll_check["innerHeight"] + 2, scroll_check

print(json.dumps({"fresh": fresh, "initial": initial, "visual": visual, "dock_settings": dock_settings, "settings_scroll": settings_scroll, "weekly_icons": weekly_icons, "light_theme": light_theme, "created": created, "returned": returned, "reloaded": reloaded, "scroll_check": scroll_check}, ensure_ascii=False))
ws.close()
