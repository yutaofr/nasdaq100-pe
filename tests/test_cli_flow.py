import hashlib
import json
import os
import subprocess
import sys

from tests.published.test_import import obs, pack


def run(root, *args):
    env = dict(os.environ, NDX_PE_DATA_ROOT=str(root))
    return subprocess.run([sys.executable, "-m", "nasdaq100_pe.cli", *args], capture_output=True, text=True, env=env)


def prep(tmp_path, **kw):
    ev = tmp_path / "ev"; ev.mkdir(exist_ok=True)
    (ev / "factsheet.pdf").write_bytes(b"pdf-bytes")
    sha = hashlib.sha256(b"pdf-bytes").hexdigest()
    inp = tmp_path / "in.json"; inp.write_bytes(pack(obs(evidence_sha256=sha, **kw)))
    return ev, inp


def test_full_flow_import_build_export_status(tmp_path):
    root = tmp_path / "data"
    ev, inp = prep(tmp_path)
    r = run(root, "import-published", "--file", str(inp), "--evidence-dir", str(ev))
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout); bid = out["batch_id"]
    assert out["publication_status"] == "archived_not_published"
    # 重复导入幂等
    assert run(root, "import-published", "--file", str(inp), "--evidence-dir", str(ev)).returncode == 0
    st = json.loads(run(root, "status").stdout)
    assert st["archive"]["observations"] == 1 and st["publish"]["current_release"] is None
    b = run(root, "build-local", "--observations", bid)
    assert b.returncode == 0, b.stdout + b.stderr
    rid = json.loads(b.stdout)["release_id"]
    st = json.loads(run(root, "status").stdout)
    assert st["publish"]["current_release"] == rid and st["backup"]["configured"] is False
    e = run(root, "export", "--observations", bid, "--scope", "local", "--output", str(tmp_path / "exp"))
    assert e.returncode == 0 and (tmp_path / "exp" / "published.csv").exists()


def test_missing_evidence_exit_6_and_nothing_archived(tmp_path):
    root = tmp_path / "data"
    ev, inp = prep(tmp_path)
    (ev / "factsheet.pdf").write_bytes(b"tampered")
    r = run(root, "import-published", "--file", str(inp), "--evidence-dir", str(ev))
    assert r.returncode == 6
    st = json.loads(run(root, "status").stdout)
    assert st["archive"]["observations"] == 0


def test_bad_input_exit_2_and_no_data_written(tmp_path):
    root = tmp_path / "data"
    ev, _ = prep(tmp_path)
    bad = tmp_path / "bad.json"; bad.write_bytes(pack(obs(value=1)))
    assert run(root, "import-published", "--file", str(bad), "--evidence-dir", str(ev)).returncode == 2
    assert not (root / "batches").exists() or not list((root / "batches").iterdir())


def test_build_unknown_batch_exit_2(tmp_path):
    assert run(tmp_path / "d", "build-local", "--observations", "nope").returncode == 2


def test_failed_build_keeps_old_pointer(tmp_path):
    root = tmp_path / "data"
    ev, inp = prep(tmp_path)
    bid = json.loads(run(root, "import-published", "--file", str(inp), "--evidence-dir", str(ev)).stdout)["batch_id"]
    rid = json.loads(run(root, "build-local", "--observations", bid).stdout)["release_id"]
    # 第二次导入含秘密注入 -> 构建失败(6)，指针保持
    inp2 = tmp_path / "in2.json"
    sha = hashlib.sha256(b"pdf-bytes").hexdigest()
    inp2.write_bytes(pack(obs(observation_id="z", provider="x api_key=abc123", evidence_sha256=sha)))
    b2 = json.loads(run(root, "import-published", "--file", str(inp2), "--evidence-dir", str(ev)).stdout)["batch_id"]
    r = run(root, "build-local", "--observations", f"{bid},{b2}")
    assert r.returncode == 6
    assert json.loads(run(root, "status").stdout)["publish"]["current_release"] == rid
