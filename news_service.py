#!/usr/bin/env python3
"""Production entry point for the Hermes Weather news crawler API."""
import os
from http.server import ThreadingHTTPServer

from weather_web import H


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "10000"))
    server = ThreadingHTTPServer((host, port), H)
    print(f"Hermes Weather news service listening on {host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
