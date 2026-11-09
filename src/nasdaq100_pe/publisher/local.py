"""引用发布包构建：不调用证券计算 engine；不生成 public 目录。"""
from __future__ import annotations

import json
import os
import shutil
import stat
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from jsonschema import Draft202012Validator

from nasdaq100_pe.archive.store import ArchiveStore, canonical, sha256
from nasdaq100_pe.published.history import series_key
from nasdaq100_pe.publisher.sanitize import scan_for_secrets

METHOD_TEXT = {
    "title": "方法与限制",
    "notes": [
        "页面展示的是来源公布的整体估值参考，不由本系统计算，也不声称与自算结果同口径。",
        "来源未披露的期间、会计口径、亏损处理保存为 unknown，不做推断。",
        "不同来源或口径各自成序列，不拼接历史，不计算跨来源变化率。",
        "页面报价日期不等于指标数据日期；未注明日期时显示观察时间。",
    ],
}


class ReleaseError(Exception):
    def __init__(self, code: str, message: str = "", exit_code: int = 6):
        super().__init__(f"{code}: {message}" if message else code)
        self.code, self.exit_code = code, exit_code


@dataclass
class ReleaseSelection:
    batch_ids: list[str] | None = None  # None = 存储内全部已归档观察
    snapshot_ids: list[str] | None = None  # 非空 = 研究发布（kind=research），与引用发布互相隔离
    data_mode: str | None = None       # real | synthetic；库内同时有两种时必须显式选择，发布包不混合
    public_permission: str = "unknown"  # 本机模式不检查再分发权限，仅记录


@dataclass
class Release:
    release_id: str
    path: Path
    manifest: dict = field(default_factory=dict)


def _schema() -> dict:
    for parent in Path(__file__).resolve().parents:
        p = parent / "schemas" / "local-release.schema.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError("local-release.schema.json")


def _apply_mode(items: list[dict], sel: ReleaseSelection) -> list[dict]:
    if sel.data_mode:
        items = [o for o in items if o["data_mode"] == sel.data_mode]
    elif len({o["data_mode"] for o in items}) > 1:
        raise ReleaseError("MIXED_DATA_MODES", "真实与演示数据不得混入同一发布包；请用 --data-mode 选择", exit_code=2)
    return items


def _select(store: ArchiveStore, sel: ReleaseSelection) -> list[dict]:
    return _apply_mode(_select_raw(store, sel), sel)


def _select_raw(store: ArchiveStore, sel: ReleaseSelection) -> list[dict]:
    known = store.known_records()
    if sel.batch_ids is None:
        return sorted(known.values(), key=lambda o: o["observation_id"])
    ids: set[str] = set()
    have = {m["batch_id"]: m for m in store.manifests()}
    for b in sel.batch_ids:
        if b not in have:
            raise ReleaseError("BATCH_NOT_FOUND", b, exit_code=2)
        ids |= {e["observation_id"] for e in have[b]["observations"]}
    return sorted((known[i] for i in ids), key=lambda o: o["observation_id"])


def _file_bytes(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")


def _build_research_release(selection: ReleaseSelection, store: ArchiveStore) -> Release:
    from nasdaq100_pe.archive.snapshots import read_snapshot
    snaps = []
    for sid in selection.snapshot_ids:
        try:
            snaps.append(read_snapshot(store, sid))
        except Exception:
            raise ReleaseError("SNAPSHOT_NOT_FOUND", sid, exit_code=2)
    snaps = _apply_mode(snaps, selection)
    snaps.sort(key=lambda s: s["snapshot_id"])
    files = {
        "research.json": _file_bytes({"snapshots": snaps}),
        "method.json": _file_bytes(METHOD_TEXT),
        "status.json": _file_bytes({"state": "ok", "kind": "research"}),
    }
    return _finish_release(store, files, "research", [], {"snapshots": [
        {"snapshot_id": s["snapshot_id"], "series_key": s["series_key"], "D": s["context"]["D"], "revision_seq": s["revision_seq"]}
        for s in snaps], "data_modes": sorted({s["data_mode"] for s in snaps})})


def build_local_release(selection: ReleaseSelection, store: ArchiveStore) -> Release:
    if selection.snapshot_ids:
        return _build_research_release(selection, store)
    obs = _select(store, selection)
    if not obs:
        raise ReleaseError("NO_OBSERVATIONS", "没有可发布的观察", exit_code=2)
    for o in obs:
        if not (store.root / "raw" / o["evidence_sha256"]).exists():
            raise ReleaseError("EVIDENCE_MISSING", o["observation_id"])
    groups: dict[str, list[dict]] = {}
    for o in obs:
        groups.setdefault(series_key(o), []).append(o)
    series = []
    for k, items in sorted(groups.items()):
        items.sort(key=lambda o: (o["observed_at"], o["observation_id"]))
        series.append({"series_key": k, "count": len(items), "latest_observed_at": items[-1]["observed_at"],
                       "observations": items})
    files = {
        "observations.json": _file_bytes({"series": series}),
        "method.json": _file_bytes(METHOD_TEXT),
        "status.json": _file_bytes({"built_from_batches": sorted({m["batch_id"] for m in store.manifests()
                                                                   if selection.batch_ids is None or m["batch_id"] in selection.batch_ids}),
                                    "state": "ok"}),
        "checks.json": _file_bytes({"checks": store.list_checks()}),
    }
    return _finish_release(store, files, "published", series, {"data_modes": sorted({o["data_mode"] for o in obs})})


def _finish_release(store, files: dict, kind: str, series: list, extra: dict) -> Release:
    forbidden = (str(store.root),)
    for name, data in files.items():
        if scan_for_secrets(data.decode("utf-8"), forbidden=forbidden):
            raise ReleaseError("SECRET_DETECTED", name)
    release_id = sha256(b"".join(canonical(n) + d for n, d in sorted(files.items())))[:16]
    manifest = {
        "release_id": release_id, "kind": kind, "deployment_mode": "local_private", "schema_version": "1",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "data_modes": extra.pop("data_modes"),
        "files": {n: sha256(d) for n, d in sorted(files.items())},
        "series": [{k: s[k] for k in ("series_key", "count", "latest_observed_at")} for s in series],
        **extra,
    }
    errs = list(Draft202012Validator(_schema()).iter_errors(manifest))
    if errs:
        raise ReleaseError("SCHEMA_INVALID", errs[0].message[:120])
    if scan_for_secrets(json.dumps(manifest), forbidden=forbidden):
        raise ReleaseError("SECRET_DETECTED", "manifest")
    rel_dir = store.root / "releases"
    rel_dir.mkdir(exist_ok=True)
    final = rel_dir / release_id
    if final.exists():
        return Release(release_id, final, json.loads((final / "manifest.json").read_text()))
    stage = rel_dir / f".stage-{uuid.uuid4().hex}"
    stage.mkdir()
    try:
        for n, d in files.items():
            (stage / n).write_bytes(d)
            os.chmod(stage / n, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        (stage / "manifest.json").write_bytes(_file_bytes(manifest))
        os.rename(stage, final)  # 候选包完整后原子改名
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return Release(release_id, final, manifest)
