"""研究管线：校验 → 归档输入 → 资格 → 唯一内核 → 不可变快照。"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from nasdaq100_pe.archive.snapshots import (canonical_input_bytes, input_hash, list_snapshots, load_input, read_snapshot,
                                            save_input, write_snapshot)
from nasdaq100_pe.archive.store import ArchiveStore, canonical, sha256
from nasdaq100_pe.calendar import TradingCalendar
from nasdaq100_pe.dec import dstr
from nasdaq100_pe.engine.core import ENGINE_VERSION, calculate
from nasdaq100_pe.engine.subset import calculate_subset
from nasdaq100_pe.method import MethodSpec
from nasdaq100_pe.validate.eligibility import (AnalysisContext, EligibilityError, assess_eligibility, series_key)
from nasdaq100_pe.validate.input import validate_research_input

SCHEMA_VERSION = "1"


@dataclass
class RunRecord:
    run_id: str
    exit_code: int
    snapshot_id: str | None
    completeness: dict | None
    publication_status: str
    diagnostics: list = field(default_factory=list)
    input_hash: str | None = None
    started_at: str = ""
    finished_at: str = ""

    def to_json(self) -> dict:
        return dict(self.__dict__)


def _schema() -> dict:
    for parent in Path(__file__).resolve().parents:
        p = parent / "schemas" / "snapshot.schema.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError("snapshot.schema.json")


def context_from_dict(d: dict, policy: MethodSpec | None = None) -> AnalysisContext:
    return AnalysisContext(W=date.fromisoformat(d["W"]), D=date.fromisoformat(d["D"]), T=datetime.fromisoformat(d["T"]),
                           analysis_profile=d["analysis_profile"], basket_policy=d["basket_policy"],
                           coverage_policy=d["coverage_policy"], freshness_policy=d["freshness_policy"],
                           method_version=d["method_version"], data_mode=d["data_mode"], policy=policy or MethodSpec.load())


def _compute(raw_bytes: bytes, context: AnalysisContext, calendar: TradingCalendar):
    """运行与复算共用的唯一路径。返回 (validation, core|None, error_diags)。"""
    val = validate_research_input(raw_bytes, context.policy)
    if val.exit_code != 0:
        return val, None, val.diagnostics
    if not val.basket.qualified:
        return val, None, val.diagnostics
    try:
        elig = assess_eligibility(val, context, calendar)
    except EligibilityError as e:
        return val, None, val.diagnostics + [{"code": e.code, "message": str(e)}]
    # 结果里的方法版本取自快照上下文，而不是当前配置：旧方法版本的快照须能原样复算
    res = calculate(elig, replace(context.policy, method_version=context.method_version))
    ws = val.basket.weights
    core = {
        "completeness": {k: m.eligibility for k, m in res.metrics.items()},
        "basket": {"mode": ws.mode, "date": ws.date, "universe_complete": val.basket.qualified,
                   "listing_scope": val.universe.listing_scope,
                   "raw_weights": {k: dstr(v) for k, v in sorted(ws.raw.items())},
                   "final_weights": {k: dstr(v) for k, v in sorted(ws.final.items())},
                   "official_rounding_factor": dstr(ws.official_rounding_factor),
                   "proxy_normalization_factor": dstr(ws.proxy_normalization_factor),
                   "known_excluded_weight": dstr(ws.known_excluded_weight),
                   "total_excluded_weight": dstr(ws.total_excluded_weight),
                   "unknown_excluded_items": ws.unknown_excluded_items, "excluded": ws.excluded,
                   "index_comparability": elig.index_comparability},
        "results": res.to_dict(),
        "subsets": ({k: _subset(res, k, context) for k in ("ttm", "fy1")} if context.coverage_policy == "subset" else {}),
        "diagnostics": val.diagnostics + elig.diagnostics,
    }
    return val, core, []


V2_SUBSET_KEYS = ("coverage_ratio", "min_coverage", "display_qualified")


def _subset(res, kind: str, context: AnalysisContext) -> dict:
    if context.method_version == "1":       # 旧快照须逐字节可复算：不带方法版本 2 的展示字段
        d = _plain(calculate_subset(res, kind))
        return {k: v for k, v in d.items() if k not in V2_SUBSET_KEYS}
    from nasdaq100_pe.dec import D
    return _plain(calculate_subset(res, kind, D(context.policy.subset_display_min_coverage)))


def _plain(o):
    from nasdaq100_pe.engine.core import _plain as p
    return p(o)


def _finish(store, run: RunRecord) -> RunRecord:
    run.finished_at = datetime.now(timezone.utc).isoformat()
    d = store.root / "runs"; d.mkdir(exist_ok=True)
    store.write_immutable(d / f"{run.run_id}.json", canonical(run.to_json()))
    return run


def run_import(path: Path, context: AnalysisContext, store: ArchiveStore, *, reason: str | None = None,
               calendar: TradingCalendar | None = None) -> RunRecord:
    cal = calendar or TradingCalendar.load()
    run = RunRecord(str(uuid.uuid4()), 0, None, None, "not_published", started_at=datetime.now(timezone.utc).isoformat())
    raw = Path(path).read_bytes()
    val, core, errs = _compute(raw, context, cal)
    if val.exit_code == 2:
        run.exit_code, run.diagnostics = 2, val.diagnostics
        return _finish(store, run)
    cb = canonical_input_bytes(val.raw) if val.raw else None
    if core is not None and cb is not None:
        # Snapshot results must be calculated from the exact bytes archived for recompute.
        val, core, errs = _compute(cb, context, cal)
    if val.exit_code == 0 and cb:
        run.input_hash = save_input(store, cb)       # 归档输入证据（含被拒的诊断依据）
    store._crash("before_snapshot")
    if core is None:
        run.exit_code, run.diagnostics = 4, errs
        return _finish(store, run)

    ctxd = context.as_dict()
    sid = sha256(canonical({"input": run.input_hash, "ctx": ctxd, "m": context.method_version, "e": ENGINE_VERSION,
                            "s": SCHEMA_VERSION}))[:20]
    key = series_key(context)
    existing = list_snapshots(store)
    run.snapshot_id, run.completeness = sid, core["completeness"]
    run.publication_status = "archived_not_published"
    run.diagnostics = core["diagnostics"]
    if any(s["snapshot_id"] == sid for s in existing):
        return _finish(store, run)                      # 幂等
    same = [s for s in existing if s["series_key"] == key]
    same_day = [s for s in same if s["context"]["D"] == ctxd["D"]]
    prev = max(same_day, key=lambda s: s["revision_seq"]) if same_day else None
    last_complete = {}
    for k in ("ttm", "fy1"):
        cands = [s for s in same if s["completeness"][k] == "complete" and s["context"]["D"] <= ctxd["D"]]
        if cands:
            b = max(cands, key=lambda s: (s["context"]["D"], s["revision_seq"]))
            last_complete[k] = {"snapshot_id": b["snapshot_id"], "D": b["context"]["D"]}   # 只引用，不复制数值
    snap = {
        "snapshot_id": sid, "schema_version": SCHEMA_VERSION, "method_version": context.method_version,
        "engine_version": ENGINE_VERSION, "input_hash": run.input_hash, "context": ctxd, "series_key": key,
        "data_mode": context.data_mode, "publication_status_at_archive": "archived_not_published",
        "securities": [{"security_id": s.security_id, "issuer_id": s.issuer_id, "share_class": s.share_class,
                        "ticker": s.ticker, "name": s.name, "sector": s.sector} for s in val.universe.securities],
        "sources": val.sources, "revision_seq": (prev["revision_seq"] + 1) if prev else 1,
        "supersedes_snapshot_id": prev["snapshot_id"] if prev else None,
        "correction_reason": reason if prev else None, "last_complete": last_complete,
        "created_at": datetime.now(timezone.utc).isoformat(), **core,
    }
    errors = list(Draft202012Validator(_schema()).iter_errors(snap))
    if errors:
        raise ValueError(f"snapshot schema: {errors[0].message}")
    write_snapshot(store, snap)
    return _finish(store, run)


CORE_KEYS = ("completeness", "basket", "results", "subsets", "diagnostics")


def _compare(snap: dict, core: dict) -> bool:
    return all(canonical(snap[k]) == canonical(json.loads(json.dumps(core[k]))) for k in CORE_KEYS)


def recompute(snapshot_id: str, store: ArchiveStore, calendar: TradingCalendar | None = None) -> dict:
    snap = read_snapshot(store, snapshot_id)
    raw = load_input(store, snap["input_hash"])
    ctx = context_from_dict(snap["context"])
    _, core, errs = _compute(raw, ctx, calendar or TradingCalendar.load())
    return {"snapshot_id": snapshot_id, "identical": core is not None and _compare(snap, core), "errors": errs}


def recompute_package(path: Path, calendar: TradingCalendar | None = None) -> dict:
    pkg = json.loads(Path(path).read_text(encoding="utf-8"))
    snap = pkg["snapshot"]
    raw = canonical(pkg["input"])
    if input_hash(raw) != snap["input_hash"]:
        return {"snapshot_id": snap["snapshot_id"], "identical": False, "errors": [{"code": "INPUT_HASH_MISMATCH"}]}
    _, core, errs = _compute(raw, context_from_dict(snap["context"]), calendar or TradingCalendar.load())
    return {"snapshot_id": snap["snapshot_id"], "identical": core is not None and _compare(snap, core), "errors": errs}
