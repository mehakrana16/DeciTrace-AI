"""Minimal static + API-proxy server for the built DeciTrace AI frontend.

Serves frontend/dist with SPA fallback and proxies /api/* to the FastAPI
backend, so the production bundle can be exercised and screenshotted without
needing vite/node_modules at runtime.

    python scripts/serve_built.py [port]
"""
from __future__ import annotations

import http.server
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist")
ROOT = os.path.abspath(ROOT)
API = os.environ.get("DECITRACE_API", "http://127.0.0.1:8000")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    # -- API proxy ---------------------------------------------------------
    def _proxy(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None

        request = urllib.request.Request(API + self.path, data=body, method=method)
        ctype = self.headers.get("Content-Type")
        if ctype:
            request.add_header("Content-Type", ctype)
        request.add_header("Accept", "application/json")

        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = response.read()
                status = response.status
                content_type = response.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as exc:
            data = exc.read()
            status = exc.code
            content_type = exc.headers.get("Content-Type", "application/json")
        except Exception as exc:  # noqa: BLE001
            data = f'{{"detail":"backend unreachable: {exc}"}}'.encode()
            status = 502
            content_type = "application/json"

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/api/"):
            return self._proxy("GET")
        # SPA fallback: any non-file path serves index.html
        if not os.path.isfile(self.translate_path(self.path)):
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):  # noqa: N802
        return self._proxy("POST")

    def log_message(self, *_args):  # silence per-request noise
        return


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4174
    if not os.path.isfile(os.path.join(ROOT, "index.html")):
        print(f"ERROR: no built bundle at {ROOT}. Run `npm run build` in frontend/.")
        return 1
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler) as httpd:
        print(f"serving {ROOT} on http://127.0.0.1:{port} (proxying /api -> {API})")
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
