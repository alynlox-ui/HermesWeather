"""万纳 All Contained —— 服务包。

对外兼容：
- weather_web.H 与 wanna.Handler 指向同一个请求处理器；
- 旧入口 `python weather_web.py` / `python news_service.py` / 双击 启动万纳.bat 全部可用。
"""
from .config import APP_VERSION, CRAWLER_REVISION, ROOT
from .routes import Handler
from .server import create_server, production_settings, run_local, serve_forever

H = Handler  # 兼容旧名

__all__ = ["APP_VERSION", "CRAWLER_REVISION", "ROOT", "Handler", "H",
           "create_server", "production_settings", "run_local", "serve_forever"]
