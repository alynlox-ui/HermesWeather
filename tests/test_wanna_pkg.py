"""wanna 包新增模块的行为测试：限流淘汰、静态路由防护、上游错误分流。"""
import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import URLError

from wanna import config


class RateLimiterTests(unittest.TestCase):
    def test_blocks_after_limit_within_window(self):
        from wanna.ratelimit import RateLimiter
        clock = {"t": 1000.0}
        limiter = RateLimiter(3, window_seconds=60, clock=lambda: clock["t"])
        for _ in range(3):
            self.assertTrue(limiter.allow("1.2.3.4"))
        self.assertFalse(limiter.allow("1.2.3.4"))
        clock["t"] += 61  # 窗口滑出后恢复
        self.assertTrue(limiter.allow("1.2.3.4"))

    def test_clients_are_evicted_beyond_capacity(self):
        from wanna.ratelimit import RateLimiter
        clock = {"t": 0.0}
        limiter = RateLimiter(5, window_seconds=60, max_clients=10, clock=lambda: clock["t"])
        for i in range(30):
            limiter.allow(f"10.0.0.{i}")
            clock["t"] += 5  # 早期客户端始终停留在窗口外
        self.assertLessEqual(limiter.client_count(), 30)
        self.assertLess(limiter.client_count(), 30, "过期客户端应被淘汰，字典不应无限增长")

    def test_active_clients_never_stall_eviction(self):
        """全员活跃时也不应卡死：一次调用必须返回。"""
        from wanna.ratelimit import RateLimiter
        limiter = RateLimiter(5, window_seconds=60, max_clients=4, clock=lambda: 0.0)
        for i in range(20):
            limiter.allow(f"203.0.113.{i}")  # 全部处于窗口内（时间不前进）


class StaticRouteTests(unittest.TestCase):
    def test_rejects_traversal_and_outside_prefix(self):
        from wanna.static import StaticError, resolve_local_path
        for path in ("/../news_crawler.py", "/..\\news_crawler.py", "/启动万纳.bat",
                     "/wanna/config.py", "/requirements.txt", "/nope.css"):
            with self.subTest(path=path):
                with self.assertRaises(StaticError):
                    resolve_local_path(path)

    def test_resolves_allowed_assets_and_split_modules(self):
        from wanna.static import resolve_local_path
        for path in ("/index.html", "/hot-news.json", "/static/css/01-base.css",
                     "/static/js/10-sites-data.js", "/assets/wanna-logo.svg"):
            with self.subTest(path=path):
                self.assertTrue(resolve_local_path(path).is_file(), path)

    def test_store_reuses_entry_until_mtime_changes(self):
        import tempfile, os
        from pathlib import Path
        from wanna.static import StaticStore
        store = StaticStore()
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "a.css"
            f.write_text("a{}", encoding="utf-8")
            first = store.entry(f)
            self.assertIs(store.entry(f).raw, first.raw, "未变更文件应命中缓存")
            f.write_text("a{b:c}", encoding="utf-8")
            os.utime(f, (f.stat().st_atime, f.stat().st_mtime + 2))
            self.assertNotEqual(store.entry(f).etag, first.etag, "文件更新后 etag 必须变化")

    def test_large_file_bypasses_cache(self):
        import tempfile
        from pathlib import Path
        from wanna.static import _MAX_CACHED_BYTES, StaticStore
        store = StaticStore()
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "big.css"
            f.write_bytes(b"x" * (_MAX_CACHED_BYTES + 10))
            store.entry(f)
            self.assertEqual(len(store._cache), 0, "超过缓存上限的文件不应进入 LRU")


class HandlerBehaviorTests(unittest.TestCase):
    def setUp(self):
        from wanna.routes import Handler
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.conn_cls = lambda: http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def _get(self, path, headers=None):
        conn = self.conn_cls()
        conn.request("GET", path, headers=headers or {})
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp, body

    def test_head_api_has_no_body(self):
        conn = self.conn_cls()
        conn.request("HEAD", "/health")
        resp = conn.getresponse()
        self.assertEqual(b"", resp.read())
        conn.close()

    def test_blank_weather_city_is_400_and_upstream_failure_is_502(self):
        # 注意：query 里 city= 的空值会被 parse_qs 丢弃并回落到默认城市，
        # 因此用 %20（空格）触发真正的“地点为空”参数错误，且不触网。
        resp, body = self._get("/api/weather?city=%20")
        self.assertEqual(400, resp.status)
        self.assertIn("不能为空", json.loads(body)["error"])

        import wanna.routes as routes
        from wanna.errors import UpstreamError
        original = routes.lookup_weather
        try:
            def boom(city):
                raise UpstreamError("无法连接 Open-Meteo 天气服务")
            routes.lookup_weather = boom
            resp, body = self._get("/api/weather?city=%E6%98%86%E6%98%8E")
            self.assertEqual(502, resp.status)
        finally:
            routes.lookup_weather = original

    def test_health_reports_single_source_version(self):
        resp, body = self._get("/health")
        self.assertEqual(config.CRAWLER_REVISION, json.loads(body)["crawlerRevision"])

    def test_weather_rate_limit_returns_429(self):
        import wanna.routes as routes
        original_rate, original_lookup = routes._weather_rate, routes.lookup_weather
        try:
            from wanna.ratelimit import RateLimiter
            routes._weather_rate = RateLimiter(1)
            routes.lookup_weather = lambda city: {"place": {}, "data": {}, "query": city}
            first, _ = self._get("/api/weather?city=%E6%98%86%E6%98%8E")
            self.assertEqual(200, first.status)
            second, body = self._get("/api/weather?city=%E6%98%86%E6%98%8E")
            self.assertEqual(429, second.status)
            self.assertIn("过于频繁", json.loads(body)["error"])
        finally:
            routes._weather_rate, routes.lookup_weather = original_rate, original_lookup


class UpstreamRetriesTests(unittest.TestCase):
    def test_retries_then_raises_upstream_error(self):
        from wanna.errors import UpstreamError
        from wanna.weather import _get_json
        calls = []

        def failing(req, timeout=None):
            calls.append(timeout)
            raise URLError("down")

        with self.assertRaises(UpstreamError):
            _get_json("https://api.open-meteo.test/v1/x", {"a": 1}, opener=failing)
        self.assertEqual(config.UPSTREAM_RETRIES, len(calls))

    def test_empty_city_is_bad_request(self):
        from wanna.errors import BadRequest
        from wanna.weather import lookup_weather
        with self.assertRaises(BadRequest):
            lookup_weather("   ")


if __name__ == "__main__":
    unittest.main()
