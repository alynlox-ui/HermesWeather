#!/usr/bin/env python3
"""兼容入口：万纳服务实现已迁移到 wanna 包。

保留本文件是为了：
1. `from weather_web import H`（tests/ 与历史脚本仍在用）；
2. `python weather_web.py` 与 启动万纳.bat 的本机启动路径不变。

新代码请直接使用 wanna.routes.Handler / wanna.server.run_local。
"""
import logging

from wanna import Handler  # noqa: F401  (re-export)
from wanna.server import run_local, serve_forever

H = Handler  # 兼容旧名

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    server = run_local()
    if server is None:
        input("按回车键退出…")
        raise SystemExit(1)
    serve_forever(server)
