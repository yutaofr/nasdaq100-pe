from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from nasdaq100_pe.archive.store import ArchiveError, ArchiveStore, canonical, sha256
from nasdaq100_pe.published.importer import PublishedImportResult

_SECRET_KEYS = ("token", "key", "secret", "sig", "auth", "pass", "session", "credential")


@dataclass
class ObservationBatch:
    batch_id: str
    observations: list[dict]


def sanitize_url(url: str) -> str:
    u = urlsplit(url)
    host = u.hostname or ""
    if u.port:
        host += f":{u.port}"
    q = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True) if not any(s in k.lower() for s in _SECRET_KEYS)]
    return urlunsplit((u.scheme, host, u.path, urlencode(q), ""))


def _check_evidence(path: Path | None, declared: str, evidence_dir: Path, oid: str) -> bytes:
    if path is None:
        raise ArchiveError("EVIDENCE_MISSING", oid)
    path = Path(path)
    if not path.exists():
        raise ArchiveError("EVIDENCE_NOT_FOUND", oid)
    real, base = path.resolve(), Path(evidence_dir).resolve()
    if base != real and base not in real.parents:
        raise ArchiveError("EVIDENCE_OUTSIDE_DIR", oid)
    data = real.read_bytes()
    if sha256(data) != declared:
        raise ArchiveError("HASH_MISMATCH", oid)
    return data


def archive_published(result: PublishedImportResult, evidence_files: Mapping[str, Path],
                      store: ArchiveStore, *, evidence_dir: Path) -> ObservationBatch:
    if not result.ok:
        raise ArchiveError("INVALID_IMPORT", "只能归档通过校验的导入结果")
    # 1. 全部验证后才写任何文件
    recs, blobs = [], {}
    for o in result.observations:
        blobs[o["evidence_sha256"]] = _check_evidence(evidence_files.get(o["observation_id"]), o["evidence_sha256"],
                                                      evidence_dir, o["observation_id"])
        rec = dict(o, data_mode=result.data_mode, source_url=sanitize_url(o["source_url"]))
        recs.append(rec)
    known = store.known_records()
    batch_ids_in = {r["observation_id"] for r in recs}
    new = []
    for r in recs:
        old = known.get(r["observation_id"])
        if old is not None:
            if canonical(old) != canonical(r):
                raise ArchiveError("ID_CONFLICT", r["observation_id"])
            continue
        tgt = r.get("corrects_observation_id")
        if tgt and tgt not in known and tgt not in batch_ids_in:
            raise ArchiveError("CORRECTION_TARGET_MISSING", tgt)
        new.append(r)
    batch_id = sha256(canonical(sorted(recs, key=lambda r: r["observation_id"])))[:32]
    manifest_path = store.root / "batches" / f"{batch_id}.json"
    if not new and manifest_path.exists():
        with store._conn() as c:  # 崩溃于索引前后重试：补齐索引，仍幂等
            for r in recs:
                store.index_observation(c, r, batch_id)
        return ObservationBatch(batch_id, recs)
    # 2. 写原件、观察文件（原子改名），清单最后写——清单是提交点
    for h, data in blobs.items():
        dest = store.root / "raw" / h
        if not dest.exists():
            store.write_immutable(dest, data)
    for r in new:
        store.write_immutable(store.record_path(r["observation_id"]), canonical(r))
    store._crash("before_manifest")
    entries = [{"observation_id": r["observation_id"],
                "record_sha256": sha256(store.record_path(r["observation_id"]).read_bytes())} for r in recs]
    manifest = {"batch_id": batch_id, "archived_at": datetime.now(timezone.utc).isoformat(),
                "observations": sorted(entries, key=lambda e: e["observation_id"])}
    if not manifest_path.exists():
        store.write_immutable(manifest_path, canonical(manifest))
    store._crash("before_index")
    with store._conn() as c:
        for r in recs:
            store.index_observation(c, r, batch_id)
    for r in new:
        store.log("archived", batch_id=batch_id, observation_id=r["observation_id"], sha256=r["evidence_sha256"])
    return ObservationBatch(batch_id, recs)
