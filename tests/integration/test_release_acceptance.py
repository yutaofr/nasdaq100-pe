"""T14 首版集成验收：真实/演示四层隔离、静态产物秘密检查、禁止内容扫描、失败不损坏旧版本。"""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.integration.test_research_pipeline import full, write
from tests.published.test_import import obs, pack

ROOT = Path(__file__).resolve().parents[2]
CTX = ["--basket-date", "2026-11-06", "--price-date", "2026-11-06", "--observed-at", "2026-11-08T12:00:00+00:00"]


def cli(root, *args):
    env = dict(os.environ, NDX_PE_DATA_ROOT=str(root))
    return subprocess.run([sys.executable, "-m", "nasdaq100_pe.cli", *args], capture_output=True, text=True, env=env)


def publish_pkg(tmp_path, name, mode, oid):
    ev = tmp_path / "ev"; ev.mkdir(exist_ok=True)
    (ev / "f.pdf").write_bytes(b"pdf")
    sha = hashlib.sha256(b"pdf").hexdigest()
    p = tmp_path / f"{name}.json"
    p.write_bytes(pack(obs(observation_id=oid, evidence_sha256=sha), data_mode=mode))
    return p, ev


def test_real_and_synthetic_isolated_in_input_history_release_export(tmp_path):
    root = tmp_path / "d"
    out = {}
    for mode, oid in (("real", "r1"), ("synthetic", "s1")):
        p, ev = publish_pkg(tmp_path, mode, mode, oid)
        r = cli(root, "import-published", "--file", str(p), "--evidence-dir", str(ev))
        assert r.returncode == 0, r.stdout
        out[mode] = json.loads(r.stdout)["batch_id"]
    # 输入层：分属不同批次；历史层：序列键含 data_mode
    from nasdaq100_pe.archive.store import ArchiveStore
    from nasdaq100_pe.published.history import series_key
    recs = ArchiveStore(root).all_observations()
    assert len({series_key(o) for o in recs}) == 2
    # 发布层：混合构建被拒；分别构建
    assert cli(root, "build-local").returncode == 2
    assert cli(root, "build-local", "--data-mode", "synthetic").returncode == 0
    # 导出层：携带模式且互不混入
    for mode in out:
        e = cli(root, "export", "--observations", out[mode], "--scope", "local", "--output", str(tmp_path / f"exp-{mode}"))
        assert e.returncode == 0
        meta = json.loads((tmp_path / f"exp-{mode}" / "metadata.json").read_text())
        assert meta["data_mode"] == mode
    pj = json.loads((tmp_path / "exp-real" / "published.json").read_text())
    assert pj["data_mode"] == "real" and all(o["observation_id"] == "r1" for o in pj["observations"])


def test_static_artifacts_have_no_secrets_or_sourcemaps(tmp_path):
    root = tmp_path / "d"
    p, ev = publish_pkg(tmp_path, "x", "real", "r1")
    assert cli(root, "import-published", "--file", str(p), "--evidence-dir", str(ev)).returncode == 0
    f = write(tmp_path, full())
    sid = json.loads(cli(root, "import", "--file", str(f), *CTX).stdout)["snapshot_id"]
    assert cli(root, "build-local").returncode == 0 and cli(root, "build-local", "--snapshot", sid).returncode == 0
    texts = []
    for d in (root / "releases", ROOT / "apps" / "web" / "dist"):
        if d.exists():
            for q in d.rglob("*"):
                assert q.suffix != ".map", f"source map: {q}"
                if q.is_file() and q.suffix in (".json", ".js", ".css", ".html"):
                    texts.append(q.read_text(encoding="utf-8", errors="ignore"))
    blob = "\n".join(texts)
    for bad in (str(root), str(tmp_path), "Traceback (most recent", "Bearer ", "api_key", "/raw/"):
        assert bad not in blob, bad


def test_no_valuation_signals_in_frontend_sources():
    banned = ["买入", "卖出", "百分位", "抄底", "低估", "高估", "红涨", "绿跌"]
    bad = []
    for p in (ROOT / "apps" / "web" / "src").rglob("*.ts*"):
        if p.name.endswith((".test.tsx", ".test.ts")) or p.name == "testFixtures.ts":
            continue
        t = p.read_text(encoding="utf-8")
        bad += [(p.name, w) for w in banned if w in t]
    css = (ROOT / "apps" / "web" / "src" / "styles.css").read_text()
    assert not bad, bad
    assert not re.search(r"pe-(low|high)|undervalued|overvalued", css)


def test_invalid_import_does_not_damage_last_good_release(tmp_path):
    root = tmp_path / "d"
    p, ev = publish_pkg(tmp_path, "g", "real", "r1")
    bid = json.loads(cli(root, "import-published", "--file", str(p), "--evidence-dir", str(ev)).stdout)["batch_id"]
    rid = json.loads(cli(root, "build-local", "--observations", bid).stdout)["release_id"]
    bad = tmp_path / "bad.json"; bad.write_bytes(b'{"schema_version":"1","data_mode":"real","observations":[{"value":1}]}')
    assert cli(root, "import-published", "--file", str(bad), "--evidence-dir", str(ev)).returncode == 2
    st = json.loads(cli(root, "status").stdout)
    assert st["publish"]["current_release"] == rid and st["archive"]["observations"] == 1


def test_research_failure_does_not_clear_published_pointer(tmp_path):
    root = tmp_path / "d"
    p, ev = publish_pkg(tmp_path, "g", "real", "r1")
    cli(root, "import-published", "--file", str(p), "--evidence-dir", str(ev))
    rid = json.loads(cli(root, "build-local").stdout)["release_id"]
    r = cli(root, "import", "--file", str(write(tmp_path, full(scope="top_n"))), *CTX)
    assert r.returncode == 4
    st = json.loads(cli(root, "status").stdout)
    assert st["publish"]["current_release"] == rid and st["publish"]["research_release"] is None


def test_exit_zero_is_not_completeness_claim(tmp_path):
    root = tmp_path / "d"
    f = write(tmp_path, full(only="ab"))
    out = json.loads(cli(root, "import", "--file", str(f), *CTX).stdout)
    assert out["exit_code"] == 0 and out["completeness"]["ttm"] == "partial" and out["publication_status"] == "archived_not_published"
