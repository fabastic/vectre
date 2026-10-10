"""Local static server for the WebGPU demo, plus a save endpoint for harness results.

  python src/webgpu/serve.py [--port 8765]
  then open http://localhost:8765/  (WebGPU needs a secure context; localhost counts)

GET  serves files from src/webgpu/ (no caching).
POST /save/<name>  writes the request body to results/phase2/gpu/<name>
     (name restricted to [A-Za-z0-9_.-]; binds to 127.0.0.1 only).
"""
from __future__ import annotations

import argparse
import re
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "results" / "phase2" / "gpu"


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_POST(self):
        m = re.fullmatch(r"/save/([A-Za-z0-9_.\-]{1,120})", self.path)
        if not m:
            self.send_error(404); return
        n = int(self.headers.get("Content-Length", 0))
        if n > 64 * 1024 * 1024:
            self.send_error(413); return
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / m.group(1)).write_bytes(self.rfile.read(n))
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), partial(Handler, directory=str(HERE)))
    print(f"serving {HERE} at http://localhost:{a.port}/  (results -> {OUT})")
    srv.serve_forever()
