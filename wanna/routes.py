"""请求路由：/api/weather、/api/news/article、/health 与静态文件。

对照旧 weather_web.py 的修复点：
- 异常语义分流：参数错误 400、上游故障 502、限流 429，不再一律 400；
- /api/weather 增加限流与并发闸（旧版完全没有，公网下是请求放大器）；
- 访问日志可开启（旧版整体静默，线上无从排障）；
- 静态资源交给 wanna.static 通用服务（旧版硬编码白名单）。
路由路径与响应 JSON 字段保持与旧版一致。
"""
import logging
from http.server import BaseHTTPRequestHandler
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

from . import config, static
from .errors import BadRequest, UpstreamError
from .http_util import Responder, RateLimited, accepts_gzip
from .ratelimit import ConcurrencyGate, RateLimiter
from .weather import DEFAULT_CITY, lookup_weather

logger = logging.getLogger("wanna")

# 进程级闸与限流器：与旧版一样跨请求共享，但字典有上限、逻辑集中可测
_weather_rate = RateLimiter(config.WEATHER_RATE_PER_MIN)
_weather_gate = ConcurrencyGate(config.WEATHER_CONCURRENCY)
_article_rate = RateLimiter(config.ARTICLE_RATE_PER_MIN)
_article_gate = ConcurrencyGate(config.ARTICLE_CONCURRENCY)


def _client_ip(handler):
    forwarded = handler.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return handler.client_address[0]


class Handler(BaseHTTPRequestHandler):
    server_version = f"AllContainedWeb/{config.APP_VERSION}"

    def do_OPTIONS(self):
        Responder(self).options()

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        responder = Responder(self)
        url = urlparse(self.path)
        try:
            if url.path == "/api/weather":
                self._handle_weather(url, responder)
            elif url.path == "/api/news/article":
                self._handle_article(url, responder)
            elif url.path == "/health":
                responder.json({"status": "ok", "service": "all-contained-web",
                                "crawlerRevision": config.CRAWLER_REVISION})
            else:
                self._handle_static(url, responder)
        except RateLimited as exc:
            responder.error(429, str(exc))
        except static.StaticError as exc:
            responder.error(exc.status, str(exc) or "资源不存在")
        except (BadRequest, ValueError) as exc:
            responder.error(400, str(exc))
        except (UpstreamError, HTTPError, URLError, TimeoutError, OSError) as exc:
            logger.warning("上游故障 %s %s: %r", self.command, url.path, exc)
            responder.error(502, "上游服务暂时不可用，请稍后重试")
        except Exception:
            logger.exception("未处理异常 %s %s", self.command, url.path)
            responder.error(500, "服务内部错误")

    def _handle_weather(self, url, responder):
        client = _client_ip(self)
        if not _weather_rate.allow(client):
            raise RateLimited("天气查询过于频繁，请稍后重试")
        if not _weather_gate.try_acquire():
            raise RateLimited("天气服务繁忙，请稍后重试")
        try:
            city = parse_qs(url.query).get("city", [DEFAULT_CITY])[0]
            responder.json(lookup_weather(city))
        finally:
            _weather_gate.release()

    def _handle_article(self, url, responder):
        client = _client_ip(self)
        if not _article_rate.allow(client):
            raise RateLimited("请求过于频繁，请稍后重试")
        if not _article_gate.try_acquire():
            raise RateLimited("正文抓取繁忙，请稍后重试")
        try:
            target = parse_qs(url.query).get("url", [""])[0]
            if not target:
                raise BadRequest("新闻网址不能为空")
            from news_crawler import fetch_article  # 保持既有顶层模块与单测 patch 点
            responder.json(fetch_article(target))
        finally:
            _article_gate.release()

    def _handle_static(self, url, responder):
        path = static.resolve_local_path(url.path)
        entry = static.STORE.entry(path)
        cache_seconds = static.cache_seconds_for(path)
        if self.headers.get("If-None-Match") == entry.etag:
            responder.not_modified(entry.etag, cache_seconds)
            return
        use_gzip = accepts_gzip(self.headers.get("Accept-Encoding"))
        body = entry.body(use_gzip)
        responder.static(path, entry.etag, body, use_gzip, cache_seconds)

    def log_message(self, fmt, *args):
        if config.request_logging_enabled():
            logger.info("%s %s", self.address_string(), fmt % args)
