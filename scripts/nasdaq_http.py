"""HTTP GET for the Nasdaq JSON endpoints, with a curl fallback.

Nasdaq's edge has refused Python's urllib (HTTP 403) while answering the same URL and headers from curl
(docs/acceptance/2026-11-17-nocp-not-published.md). On 2026-11-17 the user approved falling back to curl.
The fallback sends the same URL and the same two headers; nothing else is changed or imitated. Once curl
has answered, urllib is not asked again in this run. A refusal from curl is final: callers stop.
"""
from __future__ import annotations

import subprocess
import urllib.error
import urllib.request

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
REFUSED = (401, 403, 406, 429)


class CurlUnavailable(Exception):
    pass


def urllib_fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def curl_fetch(url: str) -> bytes:
    cmd = ["curl", "-sS", "--max-time", "20", "-w", "\n%{http_code}"]
    for k, v in HEADERS.items():
        cmd += ["-H", f"{k}: {v}"]
    try:
        r = subprocess.run(cmd + [url], capture_output=True, timeout=30)
    except FileNotFoundError as e:
        raise CurlUnavailable() from e
    except subprocess.TimeoutExpired as e:
        raise TimeoutError(str(e)) from e
    if r.returncode != 0:
        raise urllib.error.URLError(f"curl exit {r.returncode}: {r.stderr.decode(errors='replace').strip()}")
    body, _, status = r.stdout.rpartition(b"\n")
    code = int(status)
    if code >= 400:
        raise urllib.error.HTTPError(url, code, "curl", {}, None)
    return body


class Fetcher:
    """Callable url -> bytes. `via` names the client that produced the last body."""

    def __init__(self) -> None:
        self.via = "urllib"
        self.urllib_refusal: str | None = None

    def __call__(self, url: str) -> bytes:
        if self.via == "curl":
            return curl_fetch(url)
        try:
            return urllib_fetch(url)
        except urllib.error.HTTPError as e:
            if e.code not in REFUSED:
                raise
            try:
                body = curl_fetch(url)          # HTTPError from curl propagates: refused twice, stop
            except CurlUnavailable:
                raise e from None
            self.via, self.urllib_refusal = "curl", f"HTTP_{e.code}"
            return body
