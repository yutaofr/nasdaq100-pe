from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import urllib.request
from pathlib import Path

from nasdaq100_pe.archive.evidence import archive_published
from nasdaq100_pe.archive.store import ArchiveError, ArchiveStore, sha256
from nasdaq100_pe.export import export_published
from nasdaq100_pe.published.importer import validate_published
from nasdaq100_pe.publisher.local import ReleaseError, ReleaseSelection, build_local_release
from nasdaq100_pe.publisher.pointer import current_release, promote_release
from nasdaq100_pe.server import make_server, serve_local


def _out(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _store(args) -> ArchiveStore:
    root = args.data_root or os.environ.get("NDX_PE_DATA_ROOT")
    if not root:
        _out({"ok": False, "error": "需要 --data-root 或环境变量 NDX_PE_DATA_ROOT"})
        sys.exit(2)
    return ArchiveStore(root)


def _find_evidence(evidence_dir: Path, obs: list[dict]) -> dict[str, Path]:
    by_hash: dict[str, Path] = {}
    base = evidence_dir.resolve()
    for p in sorted(base.rglob("*")):
        if p.is_file():
            r = p.resolve()
            if base in r.parents:
                by_hash.setdefault(sha256(r.read_bytes()), p)
    return {o["observation_id"]: by_hash[o["evidence_sha256"]] for o in obs if o["evidence_sha256"] in by_hash}


def _cmd_import_published(args) -> int:
    res = validate_published(Path(args.file).read_bytes())
    if not res.ok or args.validate_only:
        _out(res.to_json())
        return res.exit_code
    if not args.evidence_dir:
        _out({**res.to_json(), "ok": False, "exit_code": 2,
              "diagnostics": [{"path": "--evidence-dir", "code": "REQUIRED", "message": "归档须提供证据目录"}]})
        return 2
    store = _store(args)
    try:
        ev = _find_evidence(Path(args.evidence_dir), res.observations)
        batch = archive_published(res, ev, store, evidence_dir=Path(args.evidence_dir))
    except ArchiveError as e:
        _out({"ok": False, "exit_code": 6, "error": e.code, "publication_status": "not_published"})
        return 6
    _out({**res.to_json(), "batch_id": batch.batch_id, "publication_status": "archived_not_published"})
    return 0


def _verify_over_http(store: ArchiveStore, release_id: str) -> bool:
    srv = make_server(store.root, "127.0.0.1", 0)
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}/releases/{release_id}"
        man = json.loads(urllib.request.urlopen(f"{base}/manifest.json", timeout=5).read())
        for name, h in man["files"].items():
            if sha256(urllib.request.urlopen(f"{base}/{name}", timeout=5).read()) != h:
                return False
        return man["release_id"] == release_id
    except Exception:
        return False
    finally:
        srv.shutdown(); srv.server_close()


def _cmd_build_local(args) -> int:
    store = _store(args)
    ids = [b for b in (args.observations or "").split(",") if b] or None
    snaps = [x for x in (args.snapshot or "").split(",") if x] or None
    name = "research" if snaps else "local"
    if snaps:   # 研究发布累积：并入当前研究发布已有快照，避免新日期构建因“丢历史”被拒
        from nasdaq100_pe.archive.snapshots import list_snapshots
        cur = current_release(store, "research")
        keep = []
        if cur:
            mf = store.root / "releases" / cur / "manifest.json"
            keep = [x["snapshot_id"] for x in json.loads(mf.read_text()).get("snapshots", [])] if mf.exists() else []
        if snaps == ["all"]:
            snaps = [s["snapshot_id"] for s in list_snapshots(store)]
        snaps = sorted(set(keep) | set(snaps))
    try:
        rel = build_local_release(ReleaseSelection(batch_ids=None if snaps else ids, snapshot_ids=snaps, data_mode=args.data_mode), store)
    except ReleaseError as e:
        _out({"ok": False, "exit_code": e.exit_code, "error": e.code, "publication_status": "not_published"})
        return e.exit_code
    if not _verify_over_http(store, rel.release_id):
        _out({"ok": False, "exit_code": 6, "error": "HTTP_VERIFY_FAILED", "release_id": rel.release_id,
              "publication_status": "built_not_promoted"})
        return 6
    res = promote_release(store, rel.release_id, expected_current=current_release(store, name), name=name)
    _out({"ok": res.ok, "exit_code": res.exit_code, "release_id": rel.release_id, "code": res.code,
          "publication_status": "published" if res.ok else "built_not_promoted"})
    return res.exit_code


def _cmd_check_published(args) -> int:
    from nasdaq100_pe.published.checks import record_check
    store = _store(args)
    try:
        rec = record_check(store, args.series, Path(args.evidence), evidence_dir=Path(args.evidence_dir or Path(args.evidence).parent))
    except ArchiveError as e:
        _out({"ok": False, "exit_code": 2, "error": e.code})
        return 2
    _out({"ok": True, "check": rec})
    return 0


def _ctx(args, data_mode="synthetic"):
    from datetime import date, datetime, timezone
    from nasdaq100_pe.validate.eligibility import AnalysisContext, EligibilityError
    t = datetime.fromisoformat(args.observed_at) if args.observed_at else datetime.now(timezone.utc)
    return AnalysisContext(W=date.fromisoformat(args.basket_date), D=date.fromisoformat(args.price_date), T=t,
                           analysis_profile=args.profile, basket_policy=args.basket, coverage_policy=args.coverage,
                           freshness_policy=args.freshness, method_version="1", data_mode=data_mode)


def _cmd_validate(args) -> int:
    from nasdaq100_pe.method import MethodSpec
    from nasdaq100_pe.validate.input import validate_research_input
    v = validate_research_input(Path(args.input).read_bytes(), MethodSpec.load())
    _out({"ok": v.ok, "exit_code": v.exit_code, "layers": v.layers, "diagnostics": v.diagnostics,
          "basket_qualified": bool(v.basket and v.basket.qualified), "publication_status": "not_published"})
    return v.exit_code


def _cmd_import(args) -> int:
    from nasdaq100_pe.pipeline import run_import
    from nasdaq100_pe.validate.eligibility import EligibilityError
    store = _store(args)
    try:
        raw = json.loads(Path(args.file).read_bytes())
        mode = raw.get("data_mode", "synthetic") if isinstance(raw, dict) else "synthetic"
        ctx = _ctx(args, mode if mode in ("real", "synthetic") else "synthetic")
    except EligibilityError as e:
        _out({"ok": False, "exit_code": 2, "error": e.code}); return 2
    except (ValueError, OSError):
        ctx = _ctx(args)
    run = run_import(Path(args.file), ctx, store, reason=args.reason)
    _out({"ok": run.exit_code == 0, **run.to_json()})
    return run.exit_code


def _cmd_recompute(args) -> int:
    from nasdaq100_pe.pipeline import recompute, recompute_package
    out = recompute_package(Path(args.package)) if args.package else recompute(args.snapshot, _store(args))
    _out(out)
    return 0 if out["identical"] else 4


def _cmd_check_prices(args) -> int:
    from nasdaq100_pe.adapters.price_file import load_prices
    from nasdaq100_pe.method import MethodSpec
    from nasdaq100_pe.validate.input import validate_research_input
    v = validate_research_input(Path(args.input).read_bytes(), MethodSpec.load())
    if not v.ok:
        _out({"ok": False, "exit_code": v.exit_code, "diagnostics": v.diagnostics}); return v.exit_code
    b = load_prices(Path(args.prices), v.universe, _ctx(args))
    _out({"ok": True, **b.to_json(), "note": "状态 ok 不代表完整真实价格轴通过；见 matrix 逐证券状态"})
    return 0


def _cmd_backup(args) -> int:
    from nasdaq100_pe.archive.backup import BackupError, backup
    try:
        _out({"ok": True, **backup(_store(args), Path(args.dest))}); return 0
    except BackupError as e:
        _out({"ok": False, "exit_code": 6, "error": e.code}); return 6


def _cmd_restore(args) -> int:
    from nasdaq100_pe.archive.backup import BackupError, restore
    try:
        st = restore(Path(args.source), Path(args.target))
    except BackupError as e:
        _out({"ok": False, "exit_code": 6, "error": e.code}); return 6
    _out({"ok": True, "indexed": st.index_count(), "note": "索引已从清单重建；请重新 build-local 发布，并用 recompute 核对快照"}); return 0


def _cmd_import_supplement(args) -> int:
    from nasdaq100_pe.normalize.supplements import import_supplements
    store = _store(args)
    try:
        recs = import_supplements(Path(args.file).read_bytes(), Path(args.evidence_dir), store)
    except ArchiveError as e:
        code = 2 if e.code == "SUPPLEMENT_INVALID" else 6
        _out({"ok": False, "exit_code": code, "error": e.code}); return code
    _out({"ok": True, "imported": len(recs), "supplement_ids": [r["supplement_id"] for r in recs],
          "note": "补录已归档；用 ttm-report 复核，再把合格 TTM 行写入研究输入"}); return 0


def _cmd_ttm_report(args) -> int:
    from nasdaq100_pe.adapters.sec import read_cached
    store = _store(args)
    try:
        b = read_cached(args.issuer, store)
    except (OSError, ValueError):
        _out({"ok": False, "exit_code": 2, "error": "无该发行人的 SEC 缓存；先联网 fetch_earnings 一次"}); return 2
    t = b.ttm
    _out({"ok": True, "issuer": args.issuer, "status": t.status, "reasons": t.reasons,
          "ttm_eps": str(t.ttm_eps) if t.ttm_eps is not None else None, "latest_quarter_end": t.latest_quarter_end,
          "quarters": t.quarters, "checked_at": b.checked_at, "content_fetched_at": b.content_fetched_at})
    return 0


def _cmd_serve(args) -> int:
    try:
        serve_local(Path(_store(args).root), args.host, args.port, Path(args.web_root) if args.web_root else None)
    except ValueError as e:
        _out({"ok": False, "exit_code": 2, "error": str(e)})
        return 2
    return 0


def _cmd_export(args) -> int:
    store = _store(args)
    if args.snapshot:
        from nasdaq100_pe.export import export_snapshot
        from nasdaq100_pe.archive.store import ArchiveError
        try:
            m = export_snapshot(args.snapshot, Path(args.output), store)
        except ArchiveError as e:
            _out({"ok": False, "exit_code": 2, "error": e.code}); return 2
        _out({"ok": True, "output": str(m.output), "files": m.files, "scope": "local"}); return 0
    if args.scope != "local":
        _out({"ok": False, "exit_code": 2, "error": "仅支持 --scope local"})
        return 2
    try:
        m = export_published(args.observations, Path(args.output), store)
    except KeyError:
        _out({"ok": False, "exit_code": 2, "error": "未知 batch"})
        return 2
    _out({"ok": True, "output": str(m.output), "files": m.files, "scope": "local"})
    return 0


def _cmd_status(args) -> int:
    store = _store(args)
    audit = store.root / "pointers" / "audit.jsonl"
    last = json.loads(audit.read_text().splitlines()[-1]) if audit.exists() and audit.read_text().strip() else None
    ptr = store.root / "pointers" / "local.json"
    prev = json.loads(ptr.read_text()).get("previous") if ptr.exists() else None
    _out({
        "import": {"batches": len(store.manifests())},
        "archive": {"observations": len(store.known_records()), "indexed": store.index_count(),
                    "raw_files": len(list((store.root / "raw").glob("*")))},
        "publish": {"current_release": current_release(store), "research_release": current_release(store, "research"), "previous_release": prev, "last_event": last},
        "backup": __import__("nasdaq100_pe.archive.backup", fromlist=["x"]).backup_status(store),
        "note": "退出码0不代表数据完整；以 completeness 与各发布状态为准",
    })
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ndx-pe", description="纳指100估值看板（本机个人使用）")
    p.add_argument("--data-root", help="数据根目录（默认读取 NDX_PE_DATA_ROOT；须在服务目录之外）")
    sub = p.add_subparsers(dest="cmd", required=True)
    ip = sub.add_parser("import-published", help="导入来源公布的引用指标（滚动PE/Forward PE）；与研究数据 import 无关")
    ip.add_argument("--file", required=True); ip.add_argument("--evidence-dir")
    ip.add_argument("--validate-only", action="store_true", help="只校验不归档")
    ip.set_defaults(func=_cmd_import_published)
    bl = sub.add_parser("build-local", help="构建本机发布包，经HTTP读取校验后提升指针")
    bl.add_argument("--observations", help="batch_id，逗号分隔；缺省为全部已归档观察")
    bl.add_argument("--data-mode", choices=["real", "synthetic"], help="库内同时有真实与演示数据时必须选择")
    bl.add_argument("--snapshot", help="研究快照ID，逗号分隔；构建研究发布（与引用发布指针隔离）")
    bl.set_defaults(func=_cmd_build_local)
    ck = sub.add_parser("check-published", help="记录一次带证据的来源检查（不修改指标原件或数据日期）")
    ck.add_argument("--series", required=True); ck.add_argument("--evidence", required=True)
    ck.add_argument("--evidence-dir")
    ck.set_defaults(func=_cmd_check_published)
    sv = sub.add_parser("serve", help="只读回环服务")
    sv.add_argument("--host", default="127.0.0.1"); sv.add_argument("--port", type=int, default=8765)
    sv.add_argument("--web-root")
    sv.set_defaults(func=_cmd_serve)
    ex = sub.add_parser("export", help="导出（JSON+CSV+metadata）")
    ex.add_argument("--observations"); ex.add_argument("--snapshot"); ex.add_argument("--scope", default="local")
    ex.add_argument("--output", required=True)
    ex.set_defaults(func=_cmd_export)
    va = sub.add_parser("validate", help="研究输入的结构/语义/覆盖校验，不发布")
    va.add_argument("--input", required=True); va.set_defaults(func=_cmd_validate)
    im = sub.add_parser("import", help="研究数据导入：校验→归档→计算→快照（不含引用指标，见 import-published）")
    im.add_argument("--file", required=True); im.add_argument("--reason")
    im.add_argument("--basket-date", required=True, help="权重/篮子日 W"); im.add_argument("--price-date", required=True, help="价格日 D")
    im.add_argument("--observed-at", help="观察时点 T（带时区），缺省为当前时间")
    im.add_argument("--profile", default="research", choices=["research", "strict"])
    im.add_argument("--basket", default="current", choices=["current", "fixed"])
    im.add_argument("--coverage", default="subset", choices=["full", "subset"])
    im.add_argument("--freshness", default="weekly", choices=["daily", "weekly"])
    im.set_defaults(func=_cmd_import)
    cp = sub.add_parser("check-prices", help="按价格文件核验全名单价格并输出逐证券矩阵（缺文件报告 awaiting_user_import）")
    cp.add_argument("--input", required=True, help="含 universe/weights 的研究输入"); cp.add_argument("--prices", required=True)
    cp.add_argument("--basket-date", required=True); cp.add_argument("--price-date", required=True); cp.add_argument("--observed-at")
    cp.add_argument("--profile", default="research"); cp.add_argument("--basket", default="current")
    cp.add_argument("--coverage", default="subset"); cp.add_argument("--freshness", default="weekly")
    cp.set_defaults(func=_cmd_check_prices)
    bk = sub.add_parser("backup", help="备份私有归档/方法到独立本地目录")
    bk.add_argument("--dest", required=True); bk.set_defaults(func=_cmd_backup)
    rs = sub.add_parser("restore", help="从备份恢复到空目录并重建索引")
    rs.add_argument("--source", required=True); rs.add_argument("--target", required=True); rs.set_defaults(func=_cmd_restore)
    isp = sub.add_parser("import-supplement", help="人工补录单季 EPS（须带原件哈希、页/表定位、复核时间）")
    isp.add_argument("--file", required=True); isp.add_argument("--evidence-dir", required=True)
    isp.set_defaults(func=_cmd_import_supplement)
    tr = sub.add_parser("ttm-report", help="离线读取 SEC 缓存+补录，报告 TTM 选择结果")
    tr.add_argument("--issuer", required=True); tr.set_defaults(func=_cmd_ttm_report)
    rc = sub.add_parser("recompute", help="用固定归档输入复算快照或复算包")
    rc.add_argument("--snapshot"); rc.add_argument("--package"); rc.set_defaults(func=_cmd_recompute)
    st = sub.add_parser("status", help="导入/归档/发布状态")
    st.set_defaults(func=_cmd_status)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
