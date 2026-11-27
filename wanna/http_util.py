"""HTTP 响应工具：JSON / 静态 / 错误，统一 HEAD 与 CORS 行为。

对照旧 weather_web.py 的修复点：
- 旧版 do_HEAD 直接复用 do_GET，而 sendj 不判断 self.command，
  HEAD 命中 API 会写出响应体，违反 HTTP 语义；本实现在唯一出口处拦截 body；
- 304 与 200 分支都带 Vary: Accept-Encoding；
- 上游故障返回 502/503，不再一律 400；
- send_static 缺文件/读失败不再抛裸 500，统一转成状态码响应。
"""
import json

from . import config, static


class RateLimited(Exception):
    """触发限流或并发闸 → 429。"""


def _cors_headers():
    # 保持与旧版一致的可跨域行为（部署在 CDN/静态托管时前端需跨源取 API）。
    # 若仅同源使用，可把 config.CORS_ORIGIN 收紧为空以关闭该头。
    origin = getattr(config, "CORS_ORIGIN", "*")
    if not origin:
        return ()
    return (
        ("Access-Control-Allow-Origin", origin),
        ("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS"),
        ("Access-Control-Allow-Headers", "Content-Type"),
    )


class Responder:
    """包一层 BaseHTTPRequestHandler，提供统一的写出入口。"""

    def __init__(self, handler):
        self.h = handler

    def _wants_body(self):
        return self.h.command.upper() != "HEAD"

    def json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
        ] + list(_cors_headers())
        self._send(body, status, headers, compress=False)

    def static(self, path, etag, body, use_gzip, cache_seconds):
        headers = [
            ("Content-Type", static.content_type_for(path)),
            ("Cache-Control", f"public, max-age={cache_seconds}, stale-while-revalidate=86400"),
            ("ETag", etag),
            ("Vary", "Accept-Encoding"),
            ("X-Content-Type-Options", "nosniff"),
        ] + list(_cors_headers())
        if use_gzip:
            headers.append(("Content-Encoding", "gzip"))
        self._send(body, 200, headers, known_length=len(body))

    def not_modified(self, etag, cache_seconds):
        # 304 按 RFC 7230 不应携带 Content-Length，也不应有响应体。
        headers = [
            ("ETag", etag),
            ("Cache-Control", f"public, max-age={cache_seconds}, stale-while-revalidate=86400"),
            ("Vary", "Accept-Encoding"),
        ] + list(_cors_headers())
        self.h.send_response(304)
        for key, value in headers:
            self.h.send_header(key, value)
        self.h.end_headers()

    def error(self, status, message):
        self.json({"error": message}, status)

    def options(self):
        self.h.send_response(204)
        for key, value in _cors_headers():
            self.h.send_header(key, value)
        self.h.end_headers()

    def _send(self, body, status, headers, known_length=None, compress=False, skip_body=False):
        self.h.send_response(status)
        length = known_length if known_length is not None else len(body)
        for key, value in headers:
            self.h.send_header(key, value)
        self.h.send_header("Content-Length", length)
        self.h.end_headers()
        if body and length and not skip_body and self._wants_body():
            self.h.wfile.write(body)


def accepts_gzip(header_value):
    return "gzip" in (header_value or "").lower()
