"""按客户端 IP 的滑动窗口限流 + 并发闸。

对照旧实现的修复点：
- 旧版把状态挂在 BaseHTTPRequestHandler 的类属性上，注释不清晰且
  recent 列表只追加、过期项只在被同一 IP 再次命中时清理，字典本身无上限；
  本实现给客户端数量设上限并按最近活跃时间淘汰。
- 提供可注入的时钟，便于单测。
"""
import threading
import time
from collections import OrderedDict

from . import config


class RateLimiter:
    """60 秒滑动窗口；超过 max_per_minute 则拒绝。"""

    def __init__(self, max_per_minute, window_seconds=60.0, max_clients=None, clock=time.monotonic):
        self.max_per_minute = max_per_minute
        self.window = float(window_seconds)
        self.max_clients = max_clients or config.RATE_LIMIT_MAX_CLIENTS
        self.clock = clock
        self._lock = threading.Lock()
        self._hits = OrderedDict()  # client -> [timestamps]

    def allow(self, client):
        now = self.clock()
        with self._lock:
            hits = [stamp for stamp in self._hits.get(client, ()) if now - stamp < self.window]
            if len(hits) >= self.max_per_minute:
                self._hits[client] = hits
                self._hits.move_to_end(client)
                return False
            hits.append(now)
            self._hits[client] = hits
            self._hits.move_to_end(client)
            # 淘汰长期不活跃的客户端，防止字典无限增长。
            # 最多完整扫描一轮：全员活跃时接受临时超限，绝不循环卡死。
            if len(self._hits) > self.max_clients:
                for _ in range(len(self._hits)):
                    stale_client, stamps = next(iter(self._hits.items()))
                    if not any(now - stamp < self.window for stamp in stamps):
                        self._hits.pop(stale_client, None)
                        break
                    self._hits.move_to_end(stale_client)
        return True

    def client_count(self):
        with self._lock:
            return len(self._hits)


class ConcurrencyGate:
    """非阻塞并发闸，等价于旧版 BoundedSemaphore.acquire(blocking=False)。"""

    def __init__(self, slots):
        self._sem = threading.BoundedSemaphore(slots)

    def try_acquire(self):
        return self._sem.acquire(blocking=False)

    def release(self):
        self._sem.release()

    def __enter__(self):
        if not self.try_acquire():
            raise RuntimeError("并发闸已满")
        return self

    def __exit__(self, *exc):
        self.release()
        return False
