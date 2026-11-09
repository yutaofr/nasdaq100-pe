import json
import subprocess
import sys

from tests.published.test_import import obs, pack


def run(*args):
    return subprocess.run([sys.executable, "-m", "nasdaq100_pe.cli", *args], capture_output=True, text=True)


def test_help_distinguishes_modes():
    r = run("--help")
    assert r.returncode == 0
    assert "import-published" in r.stdout and "import " in r.stdout.replace("import-published", "")


def test_import_published_ok_and_bad(tmp_path):
    good = tmp_path / "g.json"; good.write_bytes(pack(obs()))
    r = run("import-published", "--file", str(good), "--validate-only")
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["publication_status"] == "not_published" and out["completeness"]["trailing_pe"] is True
    bad = tmp_path / "b.json"; bad.write_bytes(pack(obs(value=1)))
    r = run("import-published", "--file", str(bad), "--validate-only")
    assert r.returncode == 2
    assert "observations[0].value" in r.stdout
