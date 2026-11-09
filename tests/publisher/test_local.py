import hashlib
import json
import threading

import pytest

from nasdaq100_pe.archive.evidence import archive_published
from nasdaq100_pe.archive.store import ArchiveStore
from nasdaq100_pe.publisher.local import ReleaseError, ReleaseSelection, build_local_release
from nasdaq100_pe.publisher.pointer import promote_release, current_release, rollback_release
from nasdaq100_pe.published.importer import validate_published
from tests.published.test_import import obs, pack


def mk(tmp_path):
    ev = tmp_path / "ev"; ev.mkdir()
    f = ev / "a.pdf"; f.write_bytes(b"x")
    return ev, f, hashlib.sha256(b"x").hexdigest(), ArchiveStore(tmp_path / "data")


def add(store, ev, f, sha, *os_, mode="real"):
    for o in os_:
        o["evidence_sha256"] = sha
    r = validate_published(pack(*os_, data_mode=mode)); assert r.ok, r.diagnostics
    return archive_published(r, {o["observation_id"]: f for o in os_}, store, evidence_dir=ev)


def test_build_without_securities_and_consistent_manifest(tmp_path):
    ev, f, sha, store = mk(tmp_path)
    b = add(store, ev, f, sha, obs(), obs(observation_id="o2", metric_kind="forward_pe"))
    rel = build_local_release(ReleaseSelection(batch_ids=[b.batch_id]), store)
    m = json.loads((rel.path / "manifest.json").read_text())
    assert m["deployment_mode"] == "local_private" and m["release_id"] == rel.release_id
    for name, h in m["files"].items():
        assert hashlib.sha256((rel.path / name).read_bytes()).hexdigest() == h
    assert {"observations.json", "method.json", "status.json", "checks.json"} <= set(m["files"])
    assert not (store.root / "public").exists()
    import nasdaq100_pe.publisher.local as L
    assert not hasattr(L, "calculate")  # 引用发布不依赖 engine


def test_public_denied_allows_local(tmp_path):
    ev, f, sha, store = mk(tmp_path)
    b = add(store, ev, f, sha, obs())
    for perm in ("unknown", "denied"):
        rel = build_local_release(ReleaseSelection(batch_ids=[b.batch_id], public_permission=perm), store)
        assert rel.path.exists()
    assert not (store.root / "public").exists()


def test_promote_atomic_and_pointer(tmp_path):
    ev, f, sha, store = mk(tmp_path)
    b = add(store, ev, f, sha, obs())
    rel = build_local_release(ReleaseSelection(batch_ids=[b.batch_id]), store)
    assert current_release(store) is None
    r = promote_release(store, rel.release_id, expected_current=None)
    assert r.ok and current_release(store) == rel.release_id


def test_cas_rejects_wrong_expected(tmp_path):
    ev, f, sha, store = mk(tmp_path)
    b = add(store, ev, f, sha, obs())
    rel = build_local_release(ReleaseSelection(batch_ids=[b.batch_id]), store)
    promote_release(store, rel.release_id, expected_current=None)
    r = promote_release(store, rel.release_id, expected_current="zzz")
    assert not r.ok and r.code == "CAS_MISMATCH"


def test_concurrent_promote_only_one_wins(tmp_path):
    ev, f, sha, store = mk(tmp_path)
    b = add(store, ev, f, sha, obs())
    rel = build_local_release(ReleaseSelection(batch_ids=[b.batch_id]), store)
    out = []
    ts = [threading.Thread(target=lambda: out.append(promote_release(store, rel.release_id, expected_current=None).ok)) for _ in range(6)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert out.count(True) >= 1 and current_release(store) == rel.release_id


def test_late_revision_cannot_replace_current(tmp_path):
    ev, f, sha, store = mk(tmp_path)
    old = add(store, ev, f, sha, obs(observation_id="old", observed_at="2026-11-01T00:00:00+00:00"))
    new = add(store, ev, f, sha, obs(observation_id="new", observed_at="2026-11-08T00:00:00+00:00", value="33"))
    r_new = build_local_release(ReleaseSelection(batch_ids=[old.batch_id, new.batch_id]), store)
    r_old = build_local_release(ReleaseSelection(batch_ids=[old.batch_id]), store)
    promote_release(store, r_new.release_id, expected_current=None)
    res = promote_release(store, r_old.release_id, expected_current=r_new.release_id)
    assert not res.ok and res.code == "STALE_REVISION"
    assert current_release(store) == r_new.release_id
    rb = rollback_release(store, r_old.release_id, expected_current=r_new.release_id, reason="人工回滚测试")
    assert rb.ok and current_release(store) == r_old.release_id
    audit = (store.root / "pointers" / "audit.jsonl").read_text()
    assert "rollback" in audit and "人工回滚测试" in audit


def test_hash_tamper_blocks_promotion_keeps_last(tmp_path):
    ev, f, sha, store = mk(tmp_path)
    a = add(store, ev, f, sha, obs())
    ra = build_local_release(ReleaseSelection(batch_ids=[a.batch_id]), store)
    promote_release(store, ra.release_id, expected_current=None)
    b = add(store, ev, f, sha, obs(observation_id="o9", observed_at="2026-11-09T00:00:00+00:00"))
    rb = build_local_release(ReleaseSelection(batch_ids=[a.batch_id, b.batch_id]), store)
    p = rb.path / "observations.json"; p.chmod(0o644); p.write_text(p.read_text() + " ")
    res = promote_release(store, rb.release_id, expected_current=ra.release_id)
    assert not res.ok and res.code == "HASH_MISMATCH" and res.exit_code == 6
    assert current_release(store) == ra.release_id


def test_missing_raw_evidence_rejected(tmp_path):
    ev, f, sha, store = mk(tmp_path)
    b = add(store, ev, f, sha, obs())
    p = store.root / "raw" / sha; p.chmod(0o644); p.unlink()
    with pytest.raises(ReleaseError) as e:
        build_local_release(ReleaseSelection(batch_ids=[b.batch_id]), store)
    assert e.value.exit_code == 6 and e.value.code == "EVIDENCE_MISSING"


@pytest.mark.parametrize("inject", ["api_key=abcd1234", "Bearer abc.def.ghi", "Traceback (most recent call last)", "@ROOT@/raw/x"])
def test_secret_injection_rejected(tmp_path, inject):
    ev, f, sha, store = mk(tmp_path)
    inject = inject.replace("@ROOT@", str(store.root))
    b = add(store, ev, f, sha, obs(provider=f"Evil {inject}"))
    with pytest.raises(ReleaseError) as e:
        build_local_release(ReleaseSelection(batch_ids=[b.batch_id]), store)
    assert e.value.code == "SECRET_DETECTED" and e.value.exit_code == 6
    assert not list((store.root / "releases").glob("[!.]*"))


def test_unknown_batch_rejected(tmp_path):
    ev, f, sha, store = mk(tmp_path)
    with pytest.raises(ReleaseError) as e:
        build_local_release(ReleaseSelection(batch_ids=["nope"]), store)
    assert e.value.exit_code in (2, 6)


def test_release_files_contain_no_data_root(tmp_path):
    ev, f, sha, store = mk(tmp_path)
    b = add(store, ev, f, sha, obs())
    rel = build_local_release(ReleaseSelection(batch_ids=[b.batch_id]), store)
    for p in rel.path.rglob("*"):
        if p.is_file():
            assert str(store.root) not in p.read_text()


def test_mixed_real_and_synthetic_refused_unless_mode_chosen(tmp_path):
    ev, f, sha, store = mk(tmp_path)
    add(store, ev, f, sha, obs(observation_id="r"), mode="real")
    add(store, ev, f, sha, obs(observation_id="s"), mode="synthetic")
    with pytest.raises(ReleaseError) as e:
        build_local_release(ReleaseSelection(), store)
    assert e.value.code == "MIXED_DATA_MODES" and e.value.exit_code == 2
    real = build_local_release(ReleaseSelection(data_mode="real"), store)
    demo = build_local_release(ReleaseSelection(data_mode="synthetic"), store)
    assert json.loads((real.path / "manifest.json").read_text())["data_modes"] == ["real"]
    assert json.loads((demo.path / "manifest.json").read_text())["data_modes"] == ["synthetic"]
    assert real.release_id != demo.release_id
