from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path

from nasdaq100_pe.archive.store import ArchiveStore, sha256

CSV_FIELDS = ["observation_id", "provider", "instrument", "metric_label_original", "metric_kind", "value", "unit",
              "source_as_of", "observed_at", "source_url", "evidence_sha256", "evidence_locator", "period_basis",
              "accounting_basis", "loss_treatment", "methodology_status", "entry_mode", "data_mode",
              "basis_evidence", "corrects_observation_id", "correction_reason"]
UNITS = {"value": "倍（x，十进制字符串）", "source_as_of": "YYYY-MM-DD，空表示来源未注明",
         "observed_at": "带时区ISO 8601"}
NOTE = "来源引用包：保存来源公布值与原件证据引用，不是自算复算包，不含证券级输入。"


@dataclass
class ExportManifest:
    output: Path
    files: dict[str, str]


def escape_cell(v) -> str:
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def export_published(batch_id: str, output: Path, store: ArchiveStore) -> ExportManifest:
    batch = next((m for m in store.manifests() if m["batch_id"] == batch_id), None)
    if batch is None:
        raise KeyError(f"unknown batch {batch_id}")
    known = store.known_records()
    obs = [known[e["observation_id"]] for e in batch["observations"]]
    modes = sorted({o["data_mode"] for o in obs})
    mode = modes[0] if len(modes) == 1 else "mixed"
    clean = [{k: v for k, v in o.items() if k != "data_mode"} for o in obs]
    payload = {"schema_version": "1", "data_mode": mode, "observations": clean,
               "export_meta": {"scope": "local", "batch_id": batch_id, "reproducible": False, "note": NOTE}}
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    for o in obs:
        row = {k: ("" if o.get(k) is None else o.get(k, "")) for k in CSV_FIELDS}
        for k in CSV_FIELDS:
            if k != "value":
                row[k] = escape_cell(row[k])
        w.writerow(row)
    meta = {"batch_id": batch_id, "data_mode": mode, "fields": CSV_FIELDS, "units": UNITS, "encoding": "UTF-8",
            "note": NOTE, "csv_escaping": "文本列以 = + - @ 开头时前置单引号；value 列为数字原样输出"}
    files = {
        "published.json": json.dumps(payload, ensure_ascii=False, indent=2).encode(),
        "published.csv": buf.getvalue().encode("utf-8"),
        "metadata.json": json.dumps(meta, ensure_ascii=False, indent=2).encode(),
    }
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    for n, d in files.items():
        (output / n).write_bytes(d)
    return ExportManifest(output, {n: sha256(d) for n, d in files.items()})


# ---------------- 研究快照导出 ----------------
def export_snapshot(snapshot_id: str, output: Path, store: ArchiveStore) -> ExportManifest:
    from nasdaq100_pe.archive.snapshots import load_input, read_snapshot
    snap = read_snapshot(store, snapshot_id)
    inp = json.loads(load_input(store, snap["input_hash"]).decode("utf-8"))
    pkg = {"reproducible": True, "package_version": "1", "snapshot": snap, "input": inp,
           "policy": {"method_version": snap["method_version"], "engine_version": snap["engine_version"],
                      "context": snap["context"]}}
    ids = {s["security_id"]: s for s in snap["securities"]}
    ttm, fy1 = snap["results"]["metrics"]["ttm"], snap["results"]["metrics"]["fy1"]
    cols = ["security_id", "ticker", "name", "sector", "issuer_id", "share_class", "weight"]
    for k in ("ttm", "fy1"):
        cols += [f"{k}_yield", f"{k}_contribution_points", f"{k}_pe", f"{k}_status", f"{k}_missing_reason"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    for sid in sorted(ids):
        s = ids[sid]
        row = {"security_id": sid, "ticker": s["ticker"], "name": s["name"], "sector": s["sector"] or "",
               "issuer_id": s["issuer_id"], "share_class": s["share_class"], "weight": snap["basket"]["final_weights"][sid]}
        for k, m in (("ttm", ttm), ("fy1", fy1)):
            r = m["securities"][sid]
            ok = r["valid"]
            row[f"{k}_yield"] = r["yield_"] if ok else ""
            row[f"{k}_contribution_points"] = r["contribution_points"] if ok else ""
            row[f"{k}_pe"] = r["pe"] if ok and r["pe"] is not None else ""
            row[f"{k}_status"] = "valid" if ok else "missing"
            row[f"{k}_missing_reason"] = "" if ok else ";".join(r["flags"] or ["MISSING_FIELD"])
        for c in cols:
            if c in ("name", "ticker", "sector", "issuer_id", "share_class", "security_id") or c.endswith(("_status", "_missing_reason")):
                row[c] = escape_cell(row[c])
        w.writerow(row)
    meta = {"snapshot_id": snapshot_id, "data_mode": snap["data_mode"], "analysis": snap["context"],
            "completeness": snap["completeness"], "series_key": snap["series_key"], "encoding": "UTF-8",
            "units": {"weight": "小数(1=100%)", "yield": "小数收益率", "contribution_points": "百分点=100×权重×收益率", "pe": "倍"},
            "csv_escaping": "文本列以 = + - @ 开头时前置单引号；数值列原样输出", "scope": "local"}
    files = {"recompute-package.json": json.dumps(pkg, ensure_ascii=False, indent=2).encode(),
             "detail.csv": buf.getvalue().encode("utf-8"), "metadata.json": json.dumps(meta, ensure_ascii=False, indent=2).encode()}
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    for n, d in files.items():
        (output / n).write_bytes(d)
    return ExportManifest(output, {n: sha256(d) for n, d in files.items()})
