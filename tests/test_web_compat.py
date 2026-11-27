import gzip
import http.client
import threading
import unittest
from pathlib import Path

from http.server import ThreadingHTTPServer
from weather_web import H

ROOT = Path(__file__).resolve().parents[1]


class WebCompatibilityTests(unittest.TestCase):
    def _frontend_scripts(self):
        """前端脚本已拆到 static/js/，逐个文件返回内容。"""
        for path in sorted((ROOT / "static" / "js").glob("*.js")):
            yield path.name, path.read_text(encoding="utf-8")

    def test_frontend_avoids_javascript_syntax_that_breaks_old_wechat_x5(self):
        for name, script in self._frontend_scripts():
            for unsupported in ("?.", "??", ".at("):
                self.assertNotIn(unsupported, script, f"{name} 含旧内核不支持语法 {unsupported}")

    def test_server_serves_mobile_page_and_snapshot_with_cache_and_gzip(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            conn.request("GET", "/", headers={
                "User-Agent": "Mozilla/5.0 MicroMessenger/8.0",
                "Accept-Encoding": "gzip",
            })
            response = conn.getresponse()
            body = response.read()
            self.assertEqual(200, response.status)
            self.assertEqual("gzip", response.getheader("Content-Encoding"))
            self.assertIn("public", response.getheader("Cache-Control", ""))
            self.assertIn("万纳 · All Contained".encode("utf-8"), gzip.decompress(body))

            conn.request("GET", "/hot-news.json", headers={"Accept-Encoding": "gzip"})
            response = conn.getresponse()
            body = response.read()
            self.assertEqual(200, response.status)
            self.assertEqual("gzip", response.getheader("Content-Encoding"))
            self.assertGreater(len(gzip.decompress(body)), 100)
        finally:
            server.shutdown()
            server.server_close()

    def test_split_frontend_assets_are_served_gzipped(self):
        """拆分后每个 css/js 模块都必须可访问且带正确 MIME 与 gzip。"""
        server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        expected = {
            ".css": "text/css",
            ".js": "application/javascript",
        }
        try:
            for folder, suffix in (("css", ".css"), ("js", ".js")):
                files = sorted((ROOT / "static" / folder).glob("*.js" if suffix == ".js" else "*.css"))
                self.assertTrue(files, f"static/{folder} 下没有模块文件")
                for path in files:
                    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                    conn.request("GET", f"/static/{folder}/{path.name}", headers={"Accept-Encoding": "gzip"})
                    response = conn.getresponse()
                    body = response.read()
                    self.assertEqual(200, response.status, path.name)
                    self.assertIn(expected[suffix], response.getheader("Content-Type", ""), path.name)
                    self.assertEqual("gzip", response.getheader("Content-Encoding"), path.name)
                    self.assertTrue(response.getheader("ETag"), path.name)
                    self.assertGreater(len(gzip.decompress(body)), 10, path.name)
                    conn.close()
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
