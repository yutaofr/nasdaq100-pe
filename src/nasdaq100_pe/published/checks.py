"""来源检查事件：只有带证据的检查才记录 checked_at；不修改指标原件或数据日期。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from nasdaq100_pe.archive.store import ArchiveError, ArchiveStore, canonical, sha256
from nasdaq100_pe.published.history import list_observations

WEEKLY = timedelta(days=7)


def _now(now):
    return now or datetime.now(timezone.utc)


def record_check(store: ArchiveStore, series_key: str, evidence: Path, *, evidence_dir: Path,
                 now: datetime | None = None) -> dict:
    hist = list_observations(series_key, store)
    if not hist:
        raise ArchiveError("SERIES_NOT_FOUND", series_key)
    evidence = Path(evidence)
    if not evidence.is_file():
        raise ArchiveError("EVIDENCE_NOT_FOUND", str(evidence.name))
    real, base = evidence.resolve(), Path(evidence_dir).resolve()
    if base not in real.parents:
        raise ArchiveError("EVIDENCE_OUTSIDE_DIR", evidence.name)
    data = real.read_bytes()
    h = sha256(data)
    raw = store.root / "raw" / h
    if not raw.exists():
        store.write_immutable(raw, data)
    ts = _now(now).isoformat()
    rec = {"series_key": series_key, "checked_at": ts, "evidence_sha256": h,
           "content_changed": h != hist[-1]["evidence_sha256"],
           "latest_observation_id": hist[-1]["observation_id"]}
    rec["check_id"] = sha256(canonical(rec))[:24]
    d = store.root / "checks"; d.mkdir(exist_ok=True)
    store.write_immutable(d / f"{rec['check_id']}.json", canonical(rec))
    store.log("checked", observation_id=rec["latest_observation_id"], sha256=h)
    return rec


def check_due(store: ArchiveStore, series_key: str, *, now: datetime | None = None) -> dict:
    checks = [c for c in store.list_checks() if c["series_key"] == series_key]
    hist = list_observations(series_key, store)
    base = max(c["checked_at"] for c in checks) if checks else (hist[-1]["observed_at"] if hist else None)
    if base is None:
        return {"due_at": None, "overdue": False}
    due = datetime.fromisoformat(base) + WEEKLY
    return {"due_at": due.isoformat(), "overdue": _now(now) > due, "last_basis": base}
