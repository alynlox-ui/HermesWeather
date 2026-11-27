"""静态文件服务：通用路由 + ETag/304/gzip + 内存缓存。

对照旧 weather_web.py 的修复点：
- 旧版是 if/elif 硬编码白名单，新增 favicon、.webp、css/js 都要改代码；
  本实现改为「受控根目录 + 前缀策略」的通用文件服务；
- 旧版每个请求都 read_bytes + 全文件 sha256 + 每次重新 gzip；
  本实现用 (size, mtime_ns) 作缓存键，命中时只 stat 一次；
- 旧版 304 分支缺 Vary: Accept-Encoding，代理可能被投毒；
  本实现所有分支统一带 Vary；
- 路径穿越防护：解析后必须仍位于项目根内；
- 默认只放行 index.html、study-goal-tracker.html、hot-news.json 与
  /assets/、/static/ 前缀，其余 404，避免源码/说明文件经公网泄露。
"""
import gzip
import hashlib
import os
import threading
from collections import OrderedDict
from pathlib import Path

from . import config

_MAX_CACHED_BYTES = 8 << 20  # 超过 8MB 的文件不进内存缓存，按需直读


class StaticError(Exception):
    """静态服务失败，携带要回给客户端的状态码。"""

    def __init__(self, status, message=""):
        super().__init__(message or f"HTTP {status}")
        self.status = status


_CACHE_SECONDS = dict(
    {ext: config.CACHE_HTML_SECONDS for ext in (".html", ".json")},
    **{ext: config.CACHE_ASSET_SECONDS for ext in
       (".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".woff", ".woff2")},
)


class _Entry:
    """缓存条目：原始字节 + 惰性 gzip + etag。"""

    __slots__ = ("key", "raw", "gz", "etag")

    def __init__(self, key, raw):
        self.key = key
        self.raw = raw
        self.gz = None
        self.etag = '"' + hashlib.sha256(raw).hexdigest()[:24] + '"'

    def body(self, use_gzip):
        if not use_gzip:
            return self.raw
        if self.gz is None:
            self.gz = gzip.compress(self.raw, compresslevel=config.GZIP_COMPRESS_LEVEL)
        return self.gz


class StaticStore:
    """LRU 缓存；键为 (size, mtime_ns)，文件更新后自动失效。"""

    def __init__(self, max_assets=None):
        self.max_assets = max_assets or config.STATIC_CACHE_MAX_ASSETS
        self._cache = OrderedDict()
        self._lock = threading.Lock()

    def entry(self, path):
        try:
            stat_result = path.stat()
        except OSError:
            raise StaticError(404)
        if not os.path.isfile(path):
            raise StaticError(404)
        key = f"{stat_result.st_size}|{stat_result.st_mtime_ns}"
        if stat_result.st_size > _MAX_CACHED_BYTES:
            return _Entry(None, path.read_bytes())  # 大文件直读，不占缓存
        with self._lock:
            cached = self._cache.get(path)
            if cached is not None and cached.key == key:
                self._cache.move_to_end(path)
                return cached
        entry = _Entry(key, path.read_bytes())
        with self._lock:
            self._cache[path] = entry
            self._cache.move_to_end(path)
            while len(self._cache) > self.max_assets:
                self._cache.popitem(last=False)
        return entry

    def invalidate(self):
        with self._lock:
            self._cache.clear()


STORE = StaticStore()


def _within_root(candidate, root):
    try:
        return candidate.is_relative_to(root)
    except (OSError, ValueError, AttributeError):
        return False


def resolve_local_path(url_path):
    """URL 路径 → 允许访问的本地文件；不放行或越界则 StaticError(404/403)。"""
    clean = os.path.normpath(url_path).replace("\\", "/")
    root = config.ROOT.resolve()

    if clean in config.PUBLIC_TOP_LEVEL:
        return (root / config.PUBLIC_TOP_LEVEL[clean]).resolve()

    if not any(clean.startswith(prefix) for prefix in config.PUBLIC_PREFIXES):
        raise StaticError(404)

    candidate = (root / clean.lstrip("/")).resolve()
    if not _within_root(candidate, root):
        raise StaticError(403, "非法路径")
    # 再次确认软链接的真实目标仍在根内
    try:
        if not _within_root(Path(os.path.realpath(candidate)).resolve(), root):
            raise StaticError(403, "非法路径")
    except OSError:
        raise StaticError(404)
    if not os.path.isfile(candidate):
        raise StaticError(404)
    if candidate.suffix.lower() not in config.MIME_TYPES:
        raise StaticError(404)
    return candidate


def content_type_for(path):
    return config.MIME_TYPES.get(path.suffix.lower(), "application/octet-stream")


def cache_seconds_for(path):
    return _CACHE_SECONDS.get(path.suffix.lower(), config.CACHE_HTML_SECONDS)
