from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from nasdaq100_pe.archive.store import ArchiveError, ArchiveStore, canonical, sha256

_DEC = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$")
DEC_KEYS = {"weight", "close", "eps", "profit", "market_cap", "pe"}
TS_KEYS = {"fetched_at"}


def _norm(o, key=None):
    if isinstance(o, dict):
        return {k: _norm(v, k) for k, v in o.items()}
    if isinstance(o, list):
        items = [_norm(v, key) for v in o]
        if all(isinstance(i, dict) for i in items):
            items.sort(key=lambda i: json.dumps(i, sort_keys=True, ensure_ascii=False))
        return items
    if isinstance(o, str):
        if key in DEC_KEYS and _DEC.match(o):
            return format(Decimal(o).normalize(), "f") if Decimal(o) != 0 else "0"
        if key in TS_KEYS:
            return datetime.fromisoformat(o).astimezone(timezone.utc).isoformat()
    return o


def canonical_input_bytes(raw: dict) -> bytes:
    """规范化排序/时间/Decimal 表示后的稳定字节串。"""
    return canonical(_norm(raw))


def input_hash(b: bytes) -> str:
    return sha256(b)


def _dir(store: ArchiveStore, name: str) -> Path:
    d = store.root / name
    d.mkdir(exist_ok=True)
    return d


def save_input(store: ArchiveStore, b: bytes) -> str:
    h = input_hash(b)
    p = _dir(store, "research_inputs") / f"{h}.json"
    if not p.exists():
        store.write_immutable(p, b)
    return h


def load_input(store: ArchiveStore, h: str) -> bytes:
    p = _dir(store, "research_inputs") / f"{h}.json"
    if not p.exists():
        raise ArchiveError("INPUT_MISSING", h)
    b = p.read_bytes()
    if input_hash(b) != h:
        raise ArchiveError("HASH_MISMATCH", h)
    return b


def write_snapshot(store: ArchiveStore, snap: dict) -> None:
    p = _dir(store, "snapshots") / f"{snap['snapshot_id']}.json"
    if not p.exists():
        store.write_immutable(p, canonical(snap))


def read_snapshot(store: ArchiveStore, sid: str) -> dict:
    p = _dir(store, "snapshots") / f"{sid}.json"
    if not p.exists():
        raise ArchiveError("SNAPSHOT_NOT_FOUND", sid)
    return json.loads(p.read_text(encoding="utf-8"))


def list_snapshots(store: ArchiveStore) -> list[dict]:
    out = [json.loads(p.read_text(encoding="utf-8")) for p in _dir(store, "snapshots").glob("*.json")]
    return sorted(out, key=lambda s: (s["series_key"], s["context"]["D"], s["revision_seq"], s["snapshot_id"]))
