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
        self.assertIn('name="app-version" content="1.9.0-study-goals"', source)
        self.assertIn('data-view="study"', source)
        self.assertIn('id="studyView"', source)
        self.assertIn('id="studyFrame"', source)
        self.assertIn('src="./study-goal-tracker.html"', source)
        self.assertIn('title="学习目标管理台"', source)
        self.assertIn('sandbox="allow-scripts allow-same-origin allow-downloads allow-forms"', source)
        self.assertIn('allow="clipboard-read; clipboard-write"', source)
        self.assertIn("study:'学习目标'", source)
        self.assertIn("name==='study'", source)
        self.assertNotIn("@media(max-width:680px){.nav{grid-template-columns:repeat(3", source)
        self.assertIn("@media(max-width:680px){.nav{grid-template-columns:repeat(4", source)
        self.assertIn(".study-frame{height:calc(100vh - 140px);min-height:520px}", source)

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
            "weeklyReports:{},\n    activeTab:'today',",
        ):
            self.assertIn(contract, source)

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
            self.assertEqual("web-1.9.0-study-goals", health["crawlerRevision"])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
