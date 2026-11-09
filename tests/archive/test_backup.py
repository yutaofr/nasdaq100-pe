import hashlib
import json

import pytest

from nasdaq100_pe.archive.backup import BackupError, backup, backup_status, restore
from nasdaq100_pe.archive.evidence import archive_published
from nasdaq100_pe.archive.store import ArchiveStore
from nasdaq100_pe.pipeline import recompute, run_import
from nasdaq100_pe.published.importer import validate_published
from tests.integration.test_research_pipeline import ctx, full, write
from tests.published.test_import import obs, pack


def populated(tmp_path):
    store = ArchiveStore(tmp_path / "data")
    ev = tmp_path / "ev"; ev.mkdir(); f = ev / "a.pdf"; f.write_bytes(b"x")
    r = validate_published(pack(obs(evidence_sha256=hashlib.sha256(b"x").hexdigest())))
    archive_published(r, {"o1": f}, store, evidence_dir=ev)
    run = run_import(write(tmp_path, full()), ctx(), store)
    return store, run.snapshot_id


def test_status_before_and_after_backup(tmp_path):
    store, sid = populated(tmp_path)
    assert backup_status(store)["configured"] is False and "无恢复保障" in backup_status(store)["note"]
    backup(store, tmp_path / "bk")
    st = backup_status(store)
    assert st["configured"] is True and st["last_success_at"] and "异地" in st["note"]


def test_restore_rebuilds_index_and_recompute_identical(tmp_path):
    store, sid = populated(tmp_path)
    backup(store, tmp_path / "bk")
    new = restore(tmp_path / "bk", tmp_path / "restored")
    assert new.index_count() == store.index_count() == 1
    assert new.known_records().keys() == store.known_records().keys()
    assert recompute(sid, new)["identical"] is True


def test_backup_manifest_detects_tamper(tmp_path):
    store, sid = populated(tmp_path)
    backup(store, tmp_path / "bk")
    victim = next((tmp_path / "bk" / "snapshots").glob("*.json"))
    victim.chmod(0o644); victim.write_text(victim.read_text() + " ")
    with pytest.raises(BackupError, match="HASH_MISMATCH"):
        restore(tmp_path / "bk", tmp_path / "restored")


def test_backup_dest_must_be_outside_data_root_and_not_overwrite(tmp_path):
    store, _ = populated(tmp_path)
    with pytest.raises(BackupError, match="DEST_INSIDE_DATA_ROOT"):
        backup(store, store.root / "bk")
    backup(store, tmp_path / "bk")
    with pytest.raises(BackupError, match="DEST_EXISTS"):
        backup(store, tmp_path / "bk")


def test_backup_includes_method_config_and_excludes_staging(tmp_path):
    store, _ = populated(tmp_path)
    (store.root / "staging" / "junk.tmp").write_text("x")
    backup(store, tmp_path / "bk")
    assert (tmp_path / "bk" / "config" / "methods.json").exists()
    assert not (tmp_path / "bk" / "staging").exists()


def test_restore_refuses_nonempty_target(tmp_path):
    store, _ = populated(tmp_path)
    backup(store, tmp_path / "bk")
    (tmp_path / "t").mkdir(); (tmp_path / "t" / "x").write_text("1")
    with pytest.raises(BackupError, match="TARGET_NOT_EMPTY"):
        restore(tmp_path / "bk", tmp_path / "t")
