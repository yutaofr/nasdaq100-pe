import csv
import hashlib
import json

from nasdaq100_pe.archive.evidence import archive_published
from nasdaq100_pe.archive.store import ArchiveStore
from nasdaq100_pe.export import export_published
from nasdaq100_pe.published.importer import validate_published
from tests.published.test_import import obs, pack


def setup(tmp_path, *os_):
    ev = tmp_path / "ev"; ev.mkdir()
    f = ev / "a.pdf"; f.write_bytes(b"x"); sha = hashlib.sha256(b"x").hexdigest()
    store = ArchiveStore(tmp_path / "d")
    for o in os_:
        o["evidence_sha256"] = sha
    r = validate_published(pack(*os_)); assert r.ok, r.diagnostics
    return store, archive_published(r, {o["observation_id"]: f for o in os_}, store, evidence_dir=ev)


def test_json_roundtrip_preserves_business_fields(tmp_path):
    store, b = setup(tmp_path, obs(), obs(observation_id="o2", metric_kind="forward_pe", value="27.10", source_as_of=None))
    out = tmp_path / "out"
    m = export_published(b.batch_id, out, store)
    data = json.loads((out / "published.json").read_bytes())
    assert data["export_meta"]["reproducible"] is False and "引用" in data["export_meta"]["note"]
    again = validate_published(json.dumps(data).encode())
    assert again.ok
    key = lambda o: o["observation_id"]
    orig = sorted(b.observations, key=key)
    for a, c in zip(orig, sorted(again.observations, key=key)):
        for k in c:
            assert a[k] == c[k]
    assert "published.csv" in m.files and "metadata.json" in m.files


def test_csv_escapes_formulas_and_keeps_negative_numbers(tmp_path):
    store, b = setup(tmp_path, obs(provider="=HYPERLINK(\"x\")", value="-5.50"),
                     obs(observation_id="o2", provider="+cmd", metric_label_original="@SUM(1)", instrument="-QQQ"))
    out = tmp_path / "out"
    export_published(b.batch_id, out, store)
    rows = list(csv.DictReader((out / "published.csv").open(encoding="utf-8")))
    r1 = next(r for r in rows if r["observation_id"] == "o1")
    assert r1["provider"].startswith("'=") and r1["value"] == "-5.50"
    r2 = next(r for r in rows if r["observation_id"] == "o2")
    assert r2["provider"].startswith("'+") and r2["metric_label_original"].startswith("'@") and r2["instrument"].startswith("'-")


def test_export_has_no_paths_or_secrets(tmp_path):
    store, b = setup(tmp_path, obs())
    out = tmp_path / "out"
    export_published(b.batch_id, out, store)
    for p in out.iterdir():
        t = p.read_text(encoding="utf-8")
        assert str(tmp_path) not in t
    meta = json.loads((out / "metadata.json").read_text())
    assert meta["units"]["value"] and meta["data_mode"] == "real"
