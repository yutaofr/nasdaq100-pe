"""只读回环 HTTP 服务：仅 GET/HEAD；仅发布包与前端静态文件；无上传/配置接口；不开放 CORS。"""
from __future__ import annotations

import gzip
import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from nasdaq100_pe.publisher.pointer import current_release, verify_release
from nasdaq100_pe.archive.store import ArchiveStore

ALLOWED_HOSTS = {"localhost", "127.0.0.1", "[::1]"}
_REL = re.compile(r"^/releases/([0-9a-f]{16})/([A-Za-z0-9_.\-]+)$")


def _host_ok(h: str | None) -> bool:
    if not h:
        return False
    name = h.rsplit(":", 1)[0] if re.search(r":\d+$", h) and not h.endswith("]") else h
    return name in ALLOWED_HOSTS


def make_server(root: Path, host: str, port: int, web_root: Path | None = None) -> ThreadingHTTPServer:
    if host != "127.0.0.1":
        raise ValueError("服务只允许绑定 127.0.0.1")
    root = Path(root).resolve()
    web = Path(web_root).resolve() if web_root else None
    store = ArchiveStore(root)

    class H(BaseHTTPRequestHandler):
        server_version = "ndx-pe"
        sys_version = ""

        def log_message(self, *a):  # 不记录请求内容
            pass

        def _send(self, status, body: bytes = b"", ctype="application/json; charset=utf-8", head=False):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            if len(body) > 1024 and "gzip" in (self.headers.get("Accept-Encoding") or "") and \
                    ctype.split(";")[0] in ("application/json", "text/html", "text/css", "text/javascript", "application/javascript", "image/svg+xml"):
                body = gzip.compress(body, 6, mtime=0)
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if not head:
                self.wfile.write(body)

        def _json(self, status, obj, head=False):
            self._send(status, json.dumps(obj, ensure_ascii=False).encode(), head=head)

        def _handle(self, head=False):
            if not _host_ok(self.headers.get("Host")):
                return self._json(403, {"error": "bad_host"}, head)
            raw = urlsplit(self.path).path
            path = unquote(raw)
            if "\x00" in path or "\\" in path or any(seg == ".." for seg in path.split("/")):
                return self._json(400, {"error": "bad_path"}, head)
            if path == "/healthz":
                cur = current_release(store)
                return self._json(200, {"status": "ok", "current_release": cur, "empty": cur is None,
                                        "deployment_mode": "local_private"}, head)
            if path == "/api/current":
                cur = current_release(store)
                return self._json(200, {"release_id": cur, "research_release_id": current_release(store, "research")}, head)
            m = _REL.match(path)
            if path.startswith("/releases/"):
                if not m:
                    return self._json(404, {"error": "not_found"}, head)
                rid, name = m.groups()
                man = verify_release(store, rid)
                if man is None or (name != "manifest.json" and name not in man["files"]):
                    return self._json(404, {"error": "not_found"}, head)
                f = (root / "releases" / rid / name)
                return self._send(200, f.read_bytes(), head=head)
            return self._static(path, head)

        def _static(self, path, head):
            if web is None:
                return self._json(404, {"error": "no_web"}, head)
            rel = path.lstrip("/") or "index.html"
            f = (web / rel).resolve()
            if f != web and web not in f.parents:
                return self._json(403, {"error": "forbidden"}, head)
            if f.is_file():
                ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                return self._send(200, f.read_bytes(), ctype, head)
            if "." not in Path(rel).name and (web / "index.html").is_file():  # SPA 路由回退
                return self._send(200, (web / "index.html").read_bytes(), "text/html; charset=utf-8", head)
            return self._json(404, {"error": "not_found"}, head)

        def do_GET(self):
            self._handle()

        def do_HEAD(self):
            self._handle(head=True)

        def _deny(self):
            self._json(405, {"error": "read_only"})

        do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _deny

    class Server(ThreadingHTTPServer):
        request_queue_size = 128      # 默认 backlog=5：页面并行取多个文件时 SYN 被丢弃导致数秒停顿
        daemon_threads = True

    return Server((host, port), H)


def serve_local(root: Path, host: str, port: int, web_root: Path | None = None) -> None:
    srv = make_server(root, host, port, web_root)
    print(json.dumps({"listening": f"{srv.server_address[0]}:{srv.server_address[1]}"}), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
