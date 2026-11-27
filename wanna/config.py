"""万纳 All Contained —— 服务全局配置（单一真值源）。

原先版本号同时写死在 index.html、weather_web.py 与测试里，造成漂移；
统一收敛到本模块，/health 与 compat 入口都从这里读取。
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 应用版本：meta[name=app-version] 必须与此一致（契约测试会校验）
APP_VERSION = "1.17.1-wanna-icon"
CRAWLER_REVISION = f"web-{APP_VERSION}"

# 上游（Open-Meteo）请求参数
UPSTREAM_TIMEOUT = 12
UPSTREAM_RETRIES = 2
UPSTREAM_RETRY_DELAY = 0.5

# /api/news/article：正文抓取昂贵，保留原有的限流与并发闸
ARTICLE_CONCURRENCY = 4
ARTICLE_RATE_PER_MIN = 20

# /api/weather：每次最多触发 4 次 geocoding + 1 次 forecast 外呼，
# 必须限流，否则公网部署等于免费请求放大器
WEATHER_CONCURRENCY = 8
WEATHER_RATE_PER_MIN = 60

# 限流表内存上限（按客户端 IP 计，超出按 LRU 淘汰，修复只增不清）
RATE_LIMIT_MAX_CLIENTS = 2048

# 静态资源缓存
CACHE_HTML_SECONDS = 300
CACHE_ASSET_SECONDS = 86400
GZIP_COMPRESS_LEVEL = 6
STATIC_CACHE_MAX_ASSETS = 64

# 静态目录：只允许下列前缀被公网访问，防止源码/说明文件泄露
PUBLIC_PREFIXES = ("/assets/", "/static/")
PUBLIC_TOP_LEVEL = {
    "/": "index.html",
    "/index.html": "index.html",
    "/study-goal-tracker.html": "study-goal-tracker.html",
    "/hot-news.json": "hot-news.json",
}

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}

# 跨域：前端页面可能托管在 GitHub Pages / CDN，而 API 部署在 Render 上，
# 属于跨源调用，因此默认保持旧版的 Access-Control-Allow-Origin: *。
# 注意正文抓取代理接口也随之对任意站点开放，靠域名白名单与限流兜底。
# 若确认页面与 API 始终同源部署，可设环境变量 WANNA_CORS_ORIGIN='' 关闭。
CORS_ORIGIN = os.environ.get("WANNA_CORS_ORIGIN", "*")

# 访问日志：本机双击启动默认安静；生产入口（news_service.py）默认打开。
# 原先 log_message 被整体覆写为 pass，线上排障无任何痕迹。
DEFAULT_LOG_REQUESTS = False


def request_logging_enabled():
    env = os.environ.get("WANNA_LOG_REQUESTS")
    if env is None:
        return DEFAULT_LOG_REQUESTS
    return env not in ("", "0", "false", "no")
