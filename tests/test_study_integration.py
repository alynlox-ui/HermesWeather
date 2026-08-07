import gzip
import http.client
import json
import threading
import unittest
from pathlib import Path

from http.server import ThreadingHTTPServer
from weather_web import H

ROOT = Path(__file__).resolve().parents[1]


class StudyIntegrationTests(unittest.TestCase):
    def test_main_app_exposes_embedded_study_goal_column(self):
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('name="app-version" content="1.14.0-sites-expanded"', source)
        self.assertIn('data-view="study"', source)
        self.assertIn('id="studyView"', source)
        self.assertIn('id="studyFrame"', source)
        self.assertIn('src="./study-goal-tracker.html"', source)
        self.assertIn('title="学习目标管理台"', source)
        self.assertIn('sandbox="allow-scripts allow-same-origin allow-downloads allow-forms"', source)
        self.assertIn('allow="clipboard-read; clipboard-write"', source)
        self.assertIn("study:'学习目标'", source)
        self.assertIn("name==='study'", source)
        self.assertIn('class="study-nav-icon"', source)
        self.assertIn('.study-nav-icon svg{width:24px;height:24px;', source)
        self.assertNotIn('title="学习目标">◎</button>', source)
        self.assertNotIn("grid-template-columns:repeat(5", source)
        self.assertIn(".study-frame{height:calc(100vh - 140px);min-height:520px}", source)
        self.assertIn(".study-shell{overflow:hidden;border:1px solid var(--line);border-radius:18px;background:#080a0d", source)
        self.assertIn(".study-frame{display:block;width:100%;height:calc(100vh - 128px);min-height:720px;border:0;background:#080a0d}", source)
        self.assertIn("function syncStudyFrameHeight()", source)
        self.assertIn("new ResizeObserver(syncStudyFrameHeight)", source)

    def test_learning_navigation_uses_weather_style_full_width_tabs(self):
        source = (ROOT / "study-goal-tracker.html").read_text(encoding="utf-8")
        for contract in (
            ".page-title{display:none}",
            ".topbar-nav{display:flex;gap:8px;width:100%;margin:0;padding:5px;border:1px solid var(--bd);border-radius:15px",
            ".topbar-nav .nav-item{flex:1;min-height:42px;padding:0 12px;border-radius:11px;flex-direction:row",
            ".topbar-nav .nav-item:hover,.topbar-nav .nav-item.active{color:var(--pri);background:var(--priBg);box-shadow:none}",
            ".topbar-right{display:flex;justify-content:flex-end;width:100%}",
        ):
            self.assertIn(contract, source)

    def test_weekly_four_field_icons_are_compact(self):
        source = (ROOT / "study-goal-tracker.html").read_text(encoding="utf-8")
        self.assertIn(".weekly-four-item .form-label{display:flex;align-items:center;gap:5px;color:var(--txt)}", source)
        self.assertIn(".weekly-four-item .form-label svg{width:14px;height:14px;flex:0 0 14px}", source)
        for label, icon_name in (("保持", "check"), ("问题", "alert"), ("尝试", "play"), ("下周预案", "shield")):
            self.assertIn("icon('" + icon_name + "')+' " + label, source)

    def test_settings_removes_weather_specific_content(self):
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-view="settings" data-label="设置" title="工具箱设置">⚙</button>', source)
        self.assertNotIn('data-weather-tab="settings"', source)
        settings = source.split('id="settingsView"', 1)[1].split('id="newsView"', 1)[0]
        self.assertNotIn('温度单位', settings)
        self.assertNotIn('启动时自动查询', settings)
        self.assertNotIn('默认地点', settings)
        self.assertIn("let target=name==='settings'?'weather':name", source)
        self.assertIn("settings:'工具箱设置'", source)
        self.assertIn("requestAnimationFrame(()=>{let top=scrollY+$('settingsView').getBoundingClientRect().top;document.documentElement.scrollTop=top;document.body.scrollTop=top})", source)
        self.assertIn("else if(name==='weather'){showWeatherTab('places');document.documentElement.scrollTop=0;document.body.scrollTop=0}", source)

    def test_official_sites_is_a_sixth_dock_view_with_grouped_cards(self):
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-view="sites" data-label="官网" title="软件官网合集"', source)
        self.assertIn('id="sitesView"', source)
        self.assertIn("sites:'官网合集'", source)
        self.assertIn('data-site-category="games"', source)
        self.assertIn('data-site-category="office"', source)
        for label in ('游戏', '办公', '开发', '设计', '影音', '实用工具'):
            self.assertIn(label, source)
        for name in ('Steam', 'Epic Games', 'Microsoft 365', 'WPS Office', 'Visual Studio Code', 'GitHub Desktop'):
            self.assertIn(name, source)
        self.assertIn('class="site-official"', source)
        self.assertIn('class="site-download"', source)
        for added in ('Battle.net', 'Ubisoft Connect', 'EA app', '腾讯会议', '钉钉', 'Notion', 'Git', 'Node.js', 'JetBrains Toolbox', 'Krita', 'Inkscape', 'DaVinci Resolve', 'PotPlayer', 'Spotify', 'HandBrake', 'WinRAR', 'Microsoft PowerToys', 'LocalSend'):
            self.assertIn(added, source)
        self.assertIn('const SITE_EXTRA_SOFTWARE=', source)
        for added in ('GOG GALAXY', 'HoYoPlay', 'WeGame', 'itch.io', 'Minecraft Launcher', 'Riot Games',
                      'Microsoft Teams', 'Zoom', '飞书', 'Obsidian', 'ONLYOFFICE', 'Slack',
                      'Docker Desktop', 'Visual Studio', 'Android Studio', 'Postman', 'DBeaver', 'Sublime Text',
                      'Adobe Creative Cloud', 'Affinity', 'Canva', 'Paint.NET', 'FreeCAD', 'SketchUp',
                      'QQ音乐', '网易云音乐', 'foobar2000', 'MusicBee', 'AIMP', 'Kodi',
                      'Google Chrome', 'Mozilla Firefox', 'Microsoft Edge', 'ShareX', 'CrystalDiskInfo', 'Ventoy'):
            self.assertIn(added, source)
        extras = source.split('const SITE_EXTRA_SOFTWARE=[', 1)[1].split('];', 1)[0]
        self.assertEqual(54, extras.count("{cat:"))

    def test_official_sites_supports_fuzzy_software_search(self):
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="siteSearch"', source)
        self.assertIn('id="siteSearchCount"', source)
        self.assertIn('id="siteSearchEmpty"', source)
        self.assertIn('function normalizeSiteQuery(', source)
        self.assertIn('function siteEditDistance(', source)
        self.assertIn('function siteMatchScore(', source)
        self.assertIn('function filterSites(', source)
        self.assertIn("$('siteSearch').addEventListener('input'", source)
        self.assertIn('data-search="vscode', source)
        self.assertIn('data-search="steam', source)

    def test_dock_is_hidden_left_drawer_with_icon_text_labels(self):
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="dockToggle"', source)
        self.assertIn('id="dockBackdrop"', source)
        self.assertIn('aria-expanded="false"', source)
        self.assertIn('.sidebar{position:fixed;inset:0 auto 0 0;width:250px;', source)
        self.assertIn('transform:translateX(-105%)', source)
        self.assertIn('body.dock-open .sidebar{transform:translateX(0)', source)
        self.assertIn('.nav-item::after{content:attr(data-label)', source)
        self.assertIn("function setDockOpen(open)", source)
        self.assertIn("setDockOpen(false)", source)
        self.assertIn("if(e.key==='Escape')setDockOpen(false)", source)
        self.assertIn('.shell{z-index:auto;display:block', source)
        self.assertIn('.page{position:relative;z-index:3;grid-column:auto', source)
        self.assertIn('visibility:hidden;pointer-events:none', source)
        self.assertIn('visibility:visible;pointer-events:auto', source)

    def test_embedded_project_retains_goal_checkin_weekly_and_backup_features(self):
        source = (ROOT / "study-goal-tracker.html").read_text(encoding="utf-8")
        for contract in (
            "wb_study_goal_tracker_data",
            "function saveGoal(",
            "function submitCheckin(",
            "function renderWeekly(",
            "function exportJSON(",
            "function handleImportFile(",
            "function getStreak(",
            "function getEstimateInfo(",
            "@media(max-width:600px)",
            ".handle-item-actions{width:100%",
            ".section-header .section-title{white-space:nowrap;flex:1}",
            ".section-title svg{width:18px;height:18px;flex-shrink:0}",
            "if(!TAB_TITLES[data.activeTab])data.activeTab='today';",
            "function getInitialData()",
            "version:3",
        ):
            self.assertIn(contract, source)
        for removed in (
            "isExample:true",
            "isExample:false",
            "id:'ex-1'",
            "id:'ex-2'",
            "id:'ex-3'",
            "function clearExampleData(",
            "清空示例数据",
        ):
            self.assertNotIn(removed, source)
        self.assertIn("g.isExample===true||/^ex-\\d+$/.test(String(g.id||''))", source)
        self.assertIn("var removedIds=Object.create(null);", source)

    def test_embedded_project_matches_hermes_visual_system_and_host_theme(self):
        source = (ROOT / "study-goal-tracker.html").read_text(encoding="utf-8")
        for contract in (
            '<meta name="theme-color" content="#080a0d">',
            "--bg:#080a0d;--bg2:#0d1116;--card:#111419;",
            "--pri:#b8ff35;--priL:#80d900;",
            "--txt:#f3f5f7;--txt2:#89919c;--txt3:#78818c;",
            "--bd:#252b33;",
            ".sidebar{display:none}",
            ".main{flex:1;margin-left:0;padding:24px 28px;max-width:none}",
            ".topbar-nav{display:flex",
            ".bottom-nav{display:none;position:fixed;bottom:0;left:0;right:0;background:rgba(12,14,17,.97)",
            ".btn-primary{background:linear-gradient(135deg,var(--pri),var(--priL));color:#090b0d}",
            ".card{background:rgba(17,20,25,.92);border:1px solid var(--bd);",
            "function syncHostTheme()",
            "parent.document.body.classList.contains('theme-light')",
            "new MutationObserver(syncHostTheme)",
            "getPropertyValue('--green')",
            "body.host-light{--bg:#e9edf2;",
            ".section-header .section-title{white-space:nowrap;flex:1}",
            ".section-title svg{width:18px;height:18px;flex-shrink:0}",
            ".topbar-nav{display:flex;order:3;width:100%;margin-left:0}",
            ".bottom-nav{display:none!important}",
        ):
            self.assertIn(contract, source)
        self.assertNotIn("--bg:#f8fafc;--bg2:#f1f5f9;--card:#fff;", source)

    def test_server_serves_embedded_study_app_with_gzip(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            conn.request("GET", "/study-goal-tracker.html", headers={
                "User-Agent": "Mozilla/5.0 MicroMessenger/8.0",
                "Accept-Encoding": "gzip",
            })
            response = conn.getresponse()
            body = response.read()
            self.assertEqual(200, response.status)
            self.assertEqual("gzip", response.getheader("Content-Encoding"))
            decoded = gzip.decompress(body)
            self.assertIn("学习目标管理台".encode("utf-8"), decoded)
            self.assertIn(b"wb_study_goal_tracker_data", decoded)

            conn.request("GET", "/health")
            response = conn.getresponse()
            health = json.loads(response.read())
            self.assertEqual(200, response.status)
            self.assertEqual("web-1.14.0-sites-expanded", health["crawlerRevision"])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
