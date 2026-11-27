"""服务装配与启动。

本机：run_local() 端口 8765-8775 依次尝试并自动打开浏览器（与旧版一致）。
生产：news_service.py 用 HOST/PORT 绑定（Render 等平台注入）。
"""
import threading
import webbrowser
from http.server import ThreadingHTTPServer

from . import config
from .routes import Handler

LOCAL_HOST = "127.0.0.1"
LOCAL_PORT_RANGE = range(8765, 8776)


def create_server(host, port, handler=Handler):
    return ThreadingHTTPServer((host, port), handler)


def serve_forever(server):
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def run_local(open_browser=True):
    """返回已绑定的 server；端口全被占用时返回 None。"""
    for port in LOCAL_PORT_RANGE:
        try:
            server = create_server(LOCAL_HOST, port)
        except OSError:
            continue
        url = f"http://{LOCAL_HOST}:{port}"
        print(f"万纳 All Contained 已启动：{url}")
        if open_browser:
            threading.Timer(0.7, lambda: webbrowser.open(url)).start()
        return server
    print(f"启动失败：{LOCAL_PORT_RANGE.start}-{LOCAL_PORT_RANGE.stop - 1} 端口均被占用。")
    return None


def production_settings():
    import os
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "10000"))
    return host, port
