import json
import os
import subprocess
import sys

from tests.integration.test_research_pipeline import full, write


def run(root, *args):
    env = dict(os.environ, NDX_PE_DATA_ROOT=str(root))
    return subprocess.run([sys.executable, "-m", "nasdaq100_pe.cli", *args], capture_output=True, text=True, env=env)


CTX = ["--basket-date", "2026-11-06", "--price-date", "2026-11-06", "--observed-at", "2026-11-08T12:00:00+00:00"]


def test_validate_import_recompute_export_build(tmp_path):
    root = tmp_path / "d"
    f = write(tmp_path, full())
    v = run(root, "validate", "--input", str(f))
    assert v.returncode == 0 and json.loads(v.stdout)["basket_qualified"] is True
    i = run(root, "import", "--file", str(f), *CTX)
    assert i.returncode == 0, i.stdout + i.stderr
    out = json.loads(i.stdout)
    assert out["completeness"]["ttm"] == "complete" and out["publication_status"] == "archived_not_published"
    sid = out["snapshot_id"]
    assert json.loads(run(root, "recompute", "--snapshot", sid).stdout)["identical"] is True
    e = run(root, "export", "--snapshot", sid, "--scope", "local", "--output", str(tmp_path / "e"))
    assert e.returncode == 0 and (tmp_path / "e" / "detail.csv").exists()
    b = run(root, "build-local", "--snapshot", sid)
    assert b.returncode == 0, b.stdout
    st = json.loads(run(root, "status").stdout)
    assert st["publish"]["research_release"] and st["publish"]["current_release"] is None


def test_import_missing_basket_exit4(tmp_path):
    r = run(tmp_path / "d", "import", "--file", str(write(tmp_path, full(scope="top_n"))), *CTX)
    assert r.returncode == 4 and json.loads(r.stdout)["publication_status"] == "not_published"


def test_import_bad_input_exit2(tmp_path):
    p = tmp_path / "x.json"; p.write_bytes(b"{")
    assert run(tmp_path / "d", "import", "--file", str(p), *CTX).returncode == 2


def test_strict_with_wrong_combo_exit2(tmp_path):
    r = run(tmp_path / "d", "import", "--file", str(write(tmp_path, full())), *CTX, "--profile", "strict", "--freshness", "weekly")
    assert r.returncode == 2
