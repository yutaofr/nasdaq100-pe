from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from nasdaq100_pe.archive.store import ArchiveStore, sha256


@dataclass
class PromotionResult:
    ok: bool
    release_id: str | None
    code: str = "OK"
    exit_code: int = 0
    previous: str | None = None


def _ptr(store: ArchiveStore, name: str = "local") -> Path:
    d = store.root / "pointers"; d.mkdir(exist_ok=True)
    return d / f"{name}.json"


@contextmanager
def _lock(store: ArchiveStore):
    d = store.root / "pointers"; d.mkdir(exist_ok=True)
    with open(d / ".lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def current_release(store: ArchiveStore, name: str = "local") -> str | None:
    p = _ptr(store, name)
    return json.loads(p.read_text())["current"] if p.exists() else None


def _audit(store: ArchiveStore, **rec):
    rec["ts"] = datetime.now(timezone.utc).isoformat()
    with open(store.root / "pointers" / "audit.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def verify_release(store: ArchiveStore, release_id: str) -> dict | None:
    d = store.root / "releases" / release_id
    mp = d / "manifest.json"
    if not mp.exists():
        return None
    m = json.loads(mp.read_text(encoding="utf-8"))
    for name, h in m["files"].items():
        p = d / name
        if not p.exists() or sha256(p.read_bytes()) != h:
            return None
    return m


def _watermarks(m: dict) -> dict[str, str]:
    return {s["series_key"]: s["latest_observed_at"] for s in m["series"]}


def _regresses(new: dict, cur: dict) -> bool:
    if cur.get("kind") == "research" or new.get("kind") == "research":
        if cur.get("kind") != new.get("kind"):
            return True
        def top(m):
            out: dict = {}
            for x in m["snapshots"]:
                k = (x["series_key"], x["D"])
                out[k] = max(out.get(k, 0), x["revision_seq"])
            return out
        nw, cw = top(new), top(cur)
        return any(k not in nw or nw[k] < v for k, v in cw.items())
    nw, cw = _watermarks(new), _watermarks(cur)
    return any(k not in nw or nw[k] < v for k, v in cw.items())


def _write(store: ArchiveStore, release_id: str, previous: str | None, name: str = "local"):
    tmp = _ptr(store, name).with_suffix(".tmp")
    tmp.write_text(json.dumps({"current": release_id, "previous": previous}))
    os.replace(tmp, _ptr(store, name))


def promote_release(store: ArchiveStore, release_id: str, expected_current: str | None,
                    *, name: str = "local", _rollback: bool = False, _reason: str = "") -> PromotionResult:
    with _lock(store):
        cur = current_release(store, name)
        if cur != expected_current:
            _audit(store, event="promote_rejected", release_id=release_id, code="CAS_MISMATCH")
            return PromotionResult(False, release_id, "CAS_MISMATCH", 6, cur)
        m = verify_release(store, release_id)
        if m is None:
            _audit(store, event="promote_rejected", release_id=release_id, code="HASH_MISMATCH")
            return PromotionResult(False, release_id, "HASH_MISMATCH", 6, cur)
        if cur is not None and not _rollback:
            cm = verify_release(store, cur)
            if cm is not None and _regresses(m, cm):
                _audit(store, event="promote_rejected", release_id=release_id, code="STALE_REVISION")
                return PromotionResult(False, release_id, "STALE_REVISION", 6, cur)
        _write(store, release_id, cur, name)
        _audit(store, event="rollback" if _rollback else "promote", pointer=name, release_id=release_id, previous=cur,
               **({"reason": _reason} if _rollback else {}))
        return PromotionResult(True, release_id, previous=cur)


def rollback_release(store: ArchiveStore, release_id: str, expected_current: str | None, reason: str,
                     name: str = "local") -> PromotionResult:
    return promote_release(store, release_id, expected_current, name=name, _rollback=True, _reason=reason)
