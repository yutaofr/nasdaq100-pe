import hashlib
import json
import sqlite3

import pytest

from nasdaq100_pe.archive.store import ArchiveError, ArchiveStore, CrashInjected
from nasdaq100_pe.archive.evidence import archive_published
from nasdaq100_pe.published.importer import validate_published
from tests.published.test_import import obs, pack


@pytest.fixture
def env(tmp_path):
    ev = tmp_path / "evidence"; ev.mkdir()
    f = ev / "f.pdf"; f.write_bytes(b"factsheet-bytes")
    sha = hashlib.sha256(b"factsheet-bytes").hexdigest()
    store = ArchiveStore(tmp_path / "data")
    return ev, f, sha, store


def res_for(sha, **kw):
    return validate_published(pack(obs(evidence_sha256=sha, **kw)))


def test_archive_copies_raw_and_indexes(env):
    ev, f, sha, store = env
    b = archive_published(res_for(sha), {"o1": f}, store, evidence_dir=ev)
    assert (store.root / "raw" / sha).read_bytes() == b"factsheet-bytes"
    assert [o["observation_id"] for o in b.observations] == ["o1"]
    assert store.index_count() == 1


def test_hash_mismatch_fails_no_partial(env):
    ev, f, sha, store = env
    r = res_for("b" * 64)
    with pytest.raises(ArchiveError, match="HASH_MISMATCH"):
        archive_published(r, {"o1": f}, store, evidence_dir=ev)
    assert store.index_count() == 0 and not list((store.root / "raw").glob("*"))


def test_missing_evidence_and_traversal_fail(env, tmp_path):
    ev, f, sha, store = env
    with pytest.raises(ArchiveError, match="EVIDENCE_MISSING"):
        archive_published(res_for(sha), {}, store, evidence_dir=ev)
    with pytest.raises(ArchiveError, match="EVIDENCE_NOT_FOUND"):
        archive_published(res_for(sha), {"o1": ev / "nope.pdf"}, store, evidence_dir=ev)
    outside = tmp_path / "out.pdf"; outside.write_bytes(b"factsheet-bytes")
    with pytest.raises(ArchiveError, match="EVIDENCE_OUTSIDE_DIR"):
        archive_published(res_for(sha), {"o1": outside}, store, evidence_dir=ev)
    link = ev / "link.pdf"; link.symlink_to(outside)
    with pytest.raises(ArchiveError, match="EVIDENCE_OUTSIDE_DIR"):
        archive_published(res_for(sha), {"o1": link}, store, evidence_dir=ev)
    assert store.index_count() == 0


def test_idempotent_and_conflict(env):
    ev, f, sha, store = env
    archive_published(res_for(sha), {"o1": f}, store, evidence_dir=ev)
    archive_published(res_for(sha), {"o1": f}, store, evidence_dir=ev)
    assert store.index_count() == 1
    with pytest.raises(ArchiveError, match="ID_CONFLICT"):
        archive_published(res_for(sha, value="99.9"), {"o1": f}, store, evidence_dir=ev)


def test_correction_needs_new_id_and_existing_target(env):
    ev, f, sha, store = env
    archive_published(res_for(sha), {"o1": f}, store, evidence_dir=ev)
    r = validate_published(pack(obs(observation_id="o2", value="30.0", evidence_sha256=sha,
                                    corrects_observation_id="o1", correction_reason="转录错误")))
    b = archive_published(r, {"o2": f}, store, evidence_dir=ev)
    assert b.observations[0]["corrects_observation_id"] == "o1"
    r = validate_published(pack(obs(observation_id="o3", evidence_sha256=sha,
                                    corrects_observation_id="zzz", correction_reason="x")))
    with pytest.raises(ArchiveError, match="CORRECTION_TARGET_MISSING"):
        archive_published(r, {"o3": f}, store, evidence_dir=ev)


def test_files_immutable_readonly(env):
    ev, f, sha, store = env
    archive_published(res_for(sha), {"o1": f}, store, evidence_dir=ev)
    raw = store.root / "raw" / sha
    assert not (raw.stat().st_mode & 0o222)


def test_crash_before_index_then_rebuild(env):
    ev, f, sha, store = env
    store.crash_hook = lambda stage: (_ for _ in ()).throw(CrashInjected()) if stage == "before_index" else None
    with pytest.raises(CrashInjected):
        archive_published(res_for(sha), {"o1": f}, store, evidence_dir=ev)
    assert store.index_count() == 0
    store2 = ArchiveStore(store.root)
    before = store2.manifest_digest()
    n = store2.rebuild_index()
    assert n == 1 and store2.index_count() == 1 and store2.manifest_digest() == before


def test_crash_after_files_before_manifest_not_success(env):
    ev, f, sha, store = env
    store.crash_hook = lambda stage: (_ for _ in ()).throw(CrashInjected()) if stage == "before_manifest" else None
    with pytest.raises(CrashInjected):
        archive_published(res_for(sha), {"o1": f}, store, evidence_dir=ev)
    s2 = ArchiveStore(store.root)
    assert s2.rebuild_index() == 0 and s2.index_count() == 0
    archive_published(res_for(sha), {"o1": f}, s2, evidence_dir=ev)  # 重试成功
    assert s2.index_count() == 1


def test_index_delete_rebuild_same(env):
    ev, f, sha, store = env
    archive_published(res_for(sha), {"o1": f}, store, evidence_dir=ev)
    snap = store.index_snapshot()
    (store.root / "index.sqlite").unlink()
    s2 = ArchiveStore(store.root)
    s2.rebuild_index()
    assert s2.index_snapshot() == snap


def test_log_has_only_allowed_fields_and_url_sanitized(env):
    ev, f, sha, store = env
    r = res_for(sha, source_url="https://u:p@x.com/a?token=SECRET&page=2#frag")
    b = archive_published(r, {"o1": f}, store, evidence_dir=ev)
    assert b.observations[0]["source_url"] == "https://x.com/a?page=2"
    log = (store.root / "logs" / "import.jsonl").read_text()
    assert "SECRET" not in log and "u:p" not in log
    for line in log.splitlines():
        assert set(json.loads(line)) <= {"ts", "event", "batch_id", "observation_id", "sha256", "code"}


def test_retry_after_crash_before_index_reindexes(env):
    ev, f, sha, store = env
    store.crash_hook = lambda stage: (_ for _ in ()).throw(CrashInjected()) if stage == "before_index" else None
    with pytest.raises(CrashInjected):
        archive_published(res_for(sha), {"o1": f}, store, evidence_dir=ev)
    store.crash_hook = None
    archive_published(res_for(sha), {"o1": f}, store, evidence_dir=ev)
    assert store.index_count() == 1
