"""人工补录单季 EPS：必须关联原件哈希、页/表定位与复核时间；原件校验失败整批不写入。"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

from nasdaq100_pe.archive.store import ArchiveError, ArchiveStore, canonical, sha256
from nasdaq100_pe.dec import BadDecimal, D

_HASH = re.compile(r"^[0-9a-f]{64}$")
REQUIRED = ("issuer_id", "start", "end", "eps", "currency", "form", "filed", "evidence_sha256", "locator", "reviewed_at")


def _bad(msg):
    return ArchiveError("SUPPLEMENT_INVALID", msg)


def _validate(i: int, s: dict) -> dict:
    if not isinstance(s, dict):
        raise _bad(f"supplements[{i}] 不是对象")
    for k in REQUIRED:
        if not s.get(k):
            raise _bad(f"supplements[{i}].{k} 缺失")
    try:
        D(s["eps"])                      # 负值、零值有效；NaN/Infinity 拒绝
        a, b = date.fromisoformat(s["start"]), date.fromisoformat(s["end"])
        datetime.fromisoformat(s["reviewed_at"])
    except (BadDecimal, ValueError):
        raise _bad(f"supplements[{i}] 数值或日期非法")
    if not (70 <= (b - a).days + 1 <= 125):
        raise _bad(f"supplements[{i}] 期间长度不像单季")
    if not _HASH.match(s["evidence_sha256"]):
        raise _bad(f"supplements[{i}].evidence_sha256 非法")
    return {k: s[k] for k in REQUIRED + ("note",) if k in s}


def import_supplements(payload: bytes, evidence_dir: Path, store: ArchiveStore) -> list[dict]:
    try:
        data = json.loads(payload.decode("utf-8"))
        items = data["supplements"]
        assert data["schema_version"] == "1" and isinstance(items, list) and items
    except Exception:
        raise _bad("结构错误：需要 schema_version=1 与非空 supplements 列表")
    recs = [_validate(i, s) for i, s in enumerate(items)]
    base = Path(evidence_dir).resolve()
    files = [p for p in sorted(base.rglob("*")) if p.is_file() and base in p.resolve().parents]
    if not files:
        raise ArchiveError("EVIDENCE_NOT_FOUND", "证据目录为空")
    by_hash = {}
    for p in files:
        by_hash.setdefault(sha256(p.resolve().read_bytes()), p.resolve())
    for r in recs:                       # 全部核验后才写入
        if r["evidence_sha256"] not in by_hash:
            raise ArchiveError("HASH_MISMATCH", r["evidence_sha256"][:12])
    d = store.root / "supplements"; d.mkdir(exist_ok=True)
    for r in recs:
        raw = store.root / "raw" / r["evidence_sha256"]
        if not raw.exists():
            store.write_immutable(raw, by_hash[r["evidence_sha256"]].read_bytes())
        r["supplement_id"] = sha256(canonical(r))[:24]
        p = d / f"{r['supplement_id']}.json"
        if not p.exists():
            store.write_immutable(p, canonical(r))
        store.log("supplement", sha256=r["evidence_sha256"])
    return recs


def list_supplements(store: ArchiveStore, issuer_id: str) -> list[dict]:
    d = store.root / "supplements"
    if not d.exists():
        return []
    out = [json.loads(p.read_text(encoding="utf-8")) for p in d.glob("*.json")]
    return sorted((r for r in out if r["issuer_id"] == issuer_id), key=lambda r: (r["end"], r["supplement_id"]))
