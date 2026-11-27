#!/usr/bin/env python3
"""生产入口：万纳 All Contained 天气 + 新闻 API。

- 监听平台注入的 HOST/PORT（Render 默认 0.0.0.0:10000）；
- 生产环境默认打开访问日志，便于线上排障（本机双击启动仍保持安静）。
"""
import logging
import os

from wanna import Handler
from wanna.server import create_server, production_settings, serve_forever

if __name__ == "__main__":
    os.environ.setdefault("WANNA_LOG_REQUESTS", "1")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    host, port = production_settings()
    server = create_server(host, port, Handler)
    print(f"万纳 All Contained news service listening on {host}:{port}", flush=True)
    serve_forever(server)
