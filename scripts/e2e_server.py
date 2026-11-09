"""E2E 用：在临时 DATA_ROOT 中以正式 CLI 导入合成（demo）引用数据，构建并 serve。仅供测试，数据标记 synthetic。"""
import hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path

PORT = sys.argv[1] if len(sys.argv) > 1 else "4173"
WEB = Path(__file__).resolve().parents[1] / "apps" / "web" / "dist"
tmp = Path(tempfile.mkdtemp(prefix="ndxpe-e2e-"))
env = dict(os.environ, NDX_PE_DATA_ROOT=str(tmp / "data"))
ev = tmp / "ev"; ev.mkdir()
(ev / "demo.pdf").write_bytes(b"synthetic demo evidence")
sha = hashlib.sha256(b"synthetic demo evidence").hexdigest()

def ob(i, kind, label, val, at, asof):
    return {"observation_id": i, "provider": "演示来源", "instrument": "QQQ", "metric_label_original": label,
            "metric_kind": kind, "value": val, "unit": "x", "source_as_of": asof, "observed_at": at,
            "source_url": "https://example.test/demo", "evidence_sha256": sha, "evidence_locator": "demo p1",
            "period_basis": "unknown", "accounting_basis": "unknown", "loss_treatment": "unknown",
            "methodology_status": "unknown", "entry_mode": "file"}

pkg = {"schema_version": "1", "data_mode": "synthetic", "observations": [
    ob("d1", "trailing_pe", "Demo TTM PE", "30.10", "2026-10-25T00:00:00+00:00", "2026-09-30"),
    ob("d2", "trailing_pe", "Demo TTM PE", "30.55", "2026-11-01T00:00:00+00:00", "2026-09-30"),
    ob("d3", "forward_pe", "Demo Forward PE", "26.80", "2026-11-01T00:00:00+00:00", None)]}
(tmp / "in.json").write_text(json.dumps(pkg))
py = [sys.executable, "-m", "nasdaq100_pe.cli"]
subprocess.run(py + ["import-published", "--file", str(tmp / "in.json"), "--evidence-dir", str(ev)], env=env, check=True, capture_output=True)
subprocess.run(py + ["build-local"], env=env, check=True, capture_output=True)
# ---- 研究：合成演示输入（101 只左右规模由性能测试脚本另行生成；此处小样本） ----
import datetime as _dt
H = "c" * 64
N = int(os.environ.get("E2E_N", "12"))
ids = [f"s{i:03d}" for i in range(N)]
w = [f"{1/N:.10f}" for _ in ids]
w[-1] = format(1 - sum(float(x) for x in w[:-1]), ".10f")
rows = {"schema_version": "1", "method_version": "1", "data_mode": "synthetic",
        "sources": [{"source_id": "s1", "content_sha256": H, "fetched_at": "2026-11-08T10:00:00+00:00", "locator": "demo"}],
        "universe": {"as_of": "2026-11-06", "source_id": "s1", "listing_scope": "full",
                     "securities": [{"security_id": i, "issuer_id": i, "share_class": "common", "ticker": i.upper(), "name": f"演示公司 {i}",
                                     "sector": ["科技", "医疗", "消费"][n % 3], "sector_source": "demo", "asset_class": "equity"} for n, i in enumerate(ids)]},
        "weights": {"mode": "qqq_equity_proxy", "date": "2026-11-06", "source_id": "s1",
                    "items": [{"security_id": i, "weight": x} for i, x in zip(ids, w)], "excluded": []},
        "prices": [{"security_id": i, "date": "2026-11-06", "close": "100", "currency": "USD", "price_type": "regular_close",
                    "split_basis_date": "2026-01-01", "source_id": "s1", "fetched_at": "2026-11-08T10:00:00+00:00"} for i in ids],
        "earnings": [{"security_id": i, "kind": "ttm", "eps": str(2 + n % 7 - (8 if n == 3 else 0)), "accounting_basis": "gaap", "currency": "USD",
                      "split_basis_date": "2026-01-01", "latest_quarter_end": "2026-09-30", "fetched_at": "2026-11-08T10:00:00+00:00"}
                     for n, i in enumerate(ids) if n % 5 != 4]}
(tmp / "research.json").write_text(json.dumps(rows))
r = subprocess.run(py + ["import", "--file", str(tmp / "research.json"), "--basket-date", "2026-11-06", "--price-date", "2026-11-06",
                         "--observed-at", "2026-11-08T12:00:00+00:00"], env=env, check=True, capture_output=True, text=True)
sid = json.loads(r.stdout)["snapshot_id"]
subprocess.run(py + ["build-local", "--snapshot", sid], env=env, check=True, capture_output=True)
os.execvpe(sys.executable, py + ["serve", "--port", PORT, "--web-root", str(WEB)], env)
