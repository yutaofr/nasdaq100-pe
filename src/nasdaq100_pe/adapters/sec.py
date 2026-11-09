from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlsplit

from nasdaq100_pe.archive.store import ArchiveStore, canonical, sha256
from nasdaq100_pe.normalize.quarters import select_ttm
from nasdaq100_pe.normalize.supplements import list_supplements
from nasdaq100_pe.validate.earnings import EarningsBatch

ALLOWED_HOSTS = {"data.sec.gov", "www.sec.gov"}


class SecAuthError(Exception): ...
class SecRateLimited(Exception): ...
class SecTransient(Exception): ...


def urllib_fetch(url: str, headers: dict) -> bytes:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise SecAuthError(str(e.code))
        if e.code == 429:
            raise SecRateLimited("429")
        if e.code >= 500:
            raise SecTransient(str(e.code))
        raise
    except (urllib.error.URLError, TimeoutError) as e:
        raise SecTransient(type(e).__name__)


class SecClient:
    """速率上限、指数退避、User-Agent 必填；日志只含主机与状态，不含响应/查询参数。"""

    def __init__(self, fetch=urllib_fetch, *, user_agent: str, sleep=time.sleep, min_interval: float = 0.15,
                 max_retries: int = 2, backoff_base: float = 1.0, clock=time.monotonic):
        if not user_agent or not user_agent.strip():
            raise ValueError("SEC 要求配置 User-Agent（含联系方式）")
        self._fetch, self.ua, self._sleep = fetch, user_agent, sleep
        self.min_interval, self.max_retries, self.base, self._clock = min_interval, max_retries, backoff_base, clock
        self._last: float | None = None
        self.log: list[dict] = []

    def get(self, url: str) -> bytes:
        host = urlsplit(url).hostname
        if host not in ALLOWED_HOSTS:
            raise ValueError("仅允许访问 SEC 域名")
        if self._last is not None:
            wait = self.min_interval - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        attempt = 0
        while True:
            self._last = self._clock()
            try:
                body = self._fetch(url, {"User-Agent": self.ua, "Accept-Encoding": "identity"})
                self.log.append({"event": "ok", "host": host})
                return body
            except SecAuthError:
                self.log.append({"event": "auth_error", "host": host})
                raise
            except (SecRateLimited, SecTransient) as e:
                self.log.append({"event": type(e).__name__, "host": host, "attempt": attempt})
                if attempt >= self.max_retries:
                    raise
                self._sleep(self.base * (2 ** attempt))
                attempt += 1


def _cik10(issuer_id: str) -> str:
    digits = "".join(ch for ch in issuer_id if ch.isdigit())
    if not digits:
        raise ValueError(f"issuer_id 无 CIK: {issuer_id}")
    return digits.zfill(10)


def _cache_path(store: ArchiveStore, cik10: str):
    d = store.root / "sec_cache"; d.mkdir(exist_ok=True)
    return d / f"{cik10}.json"


def _batch(store: ArchiveStore, issuer_id: str, cik10: str, meta: dict, flags: list[str], freshness: str) -> EarningsBatch:
    body = (store.root / "raw" / meta["current"]["content_sha256"]).read_bytes()
    ttm = select_ttm(json.loads(body), list_supplements(store, issuer_id))
    cur = meta["current"]
    return EarningsBatch(issuer_id=issuer_id, cik=cik10, currency=ttm.currency, split_basis_date=None, ttm=ttm,
                         checked_at=cur["checked_at"], content_fetched_at=cur["content_fetched_at"],
                         content_sha256=cur["content_sha256"], versions=meta["versions"], flags=flags, freshness=freshness)


def read_cached(issuer_id: str, store: ArchiveStore) -> EarningsBatch:
    """离线重读：不改变 checked_at / content_fetched_at。"""
    cik10 = _cik10(issuer_id)
    meta = json.loads(_cache_path(store, cik10).read_text())
    return _batch(store, issuer_id, cik10, meta, [], "cached")


def fetch_earnings(issuer_id: str, store: ArchiveStore, client: SecClient, *, now: datetime | None = None) -> EarningsBatch:
    now = now or datetime.now(timezone.utc)
    cik10 = _cik10(issuer_id)
    p = _cache_path(store, cik10)
    meta = json.loads(p.read_text()) if p.exists() else None
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"
    try:
        body = client.get(url)
    except (SecAuthError, SecRateLimited, SecTransient):
        if meta is None:
            raise
        return _batch(store, issuer_id, cik10, meta, ["CHECK_FAILED"], "unverified")   # 复核失败不冒充最新
    h = sha256(body)
    raw = store.root / "raw" / h
    if not raw.exists():
        store.write_immutable(raw, body)
    flags: list[str] = []
    ts = now.isoformat()
    if meta is None:
        meta = {"versions": [{"content_sha256": h, "content_fetched_at": ts}],
                "current": {"content_sha256": h, "content_fetched_at": ts, "checked_at": ts}}
    elif meta["current"]["content_sha256"] == h:
        meta["current"]["checked_at"] = ts                 # 内容未变：只更新检查时间
    else:
        meta["versions"].append({"content_sha256": h, "content_fetched_at": ts})
        meta["current"] = {"content_sha256": h, "content_fetched_at": ts, "checked_at": ts}
        flags.append("NEW_DISCLOSURE")
    p.write_bytes(canonical(meta))
    store.log("sec_checked", sha256=h)
    return _batch(store, issuer_id, cik10, meta, flags, "verified")
