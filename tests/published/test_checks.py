import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from nasdaq100_pe.archive.store import ArchiveError
from nasdaq100_pe.published.checks import check_due, record_check
from nasdaq100_pe.published.history import series_key
from tests.published.test_history import setup
from tests.published.test_import import obs

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def mkstore(tmp_path):
    o = obs(observation_id="a")
    store = setup(tmp_path, o)
    ev = tmp_path / "ev"
    return store, ev, series_key({**o, "data_mode": "real"}), ev / "a.pdf"


def test_check_records_time_not_data_date(tmp_path):
    store, ev, key, f = mkstore(tmp_path)
    c = record_check(store, key, f, evidence_dir=ev, now=T0)
    assert c["checked_at"] == T0.isoformat() and c["content_changed"] is False
    obs_after = store.all_observations()
    assert obs_after[0]["source_as_of"] == "2026-09-30"  # 数据日期不被检查刷新


def test_due_is_last_evidenced_check_plus_7_days(tmp_path):
    store, ev, key, f = mkstore(tmp_path)
    record_check(store, key, f, evidence_dir=ev, now=T0)
    assert check_due(store, key, now=T0 + timedelta(days=7))["overdue"] is False
    assert check_due(store, key, now=T0 + timedelta(days=7, seconds=1))["overdue"] is True


def test_refresh_without_check_does_not_move_due(tmp_path):
    store, ev, key, f = mkstore(tmp_path)
    d1 = check_due(store, key, now=T0)
    d2 = check_due(store, key, now=T0 + timedelta(days=3))
    assert d1["due_at"] == d2["due_at"]  # 无检查记录时以最近观察 observed_at 为基准


def test_check_requires_existing_series_and_evidence(tmp_path):
    store, ev, key, f = mkstore(tmp_path)
    with pytest.raises(ArchiveError, match="SERIES_NOT_FOUND"):
        record_check(store, "nope", f, evidence_dir=ev, now=T0)
    with pytest.raises(ArchiveError, match="EVIDENCE_NOT_FOUND"):
        record_check(store, key, ev / "missing.pdf", evidence_dir=ev, now=T0)


def test_changed_content_flagged_and_still_not_new_data(tmp_path):
    store, ev, key, f = mkstore(tmp_path)
    g = ev / "new.pdf"; g.write_bytes(b"different")
    c = record_check(store, key, g, evidence_dir=ev, now=T0)
    assert c["content_changed"] is True
    assert len(store.all_observations()) == 1  # 不自动改指标


def test_check_enters_release(tmp_path):
    from nasdaq100_pe.publisher.local import ReleaseSelection, build_local_release
    import json
    store, ev, key, f = mkstore(tmp_path)
    record_check(store, key, f, evidence_dir=ev, now=T0)
    rel = build_local_release(ReleaseSelection(), store)
    assert json.loads((rel.path / "checks.json").read_text())["checks"][0]["series_key"] == key
