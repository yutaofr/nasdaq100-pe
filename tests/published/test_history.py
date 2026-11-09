import hashlib

from nasdaq100_pe.archive.evidence import archive_published
from nasdaq100_pe.archive.store import ArchiveStore
from nasdaq100_pe.published.history import list_observations, series_key
from nasdaq100_pe.published.importer import validate_published
from tests.published.test_import import obs, pack


def setup(tmp_path, *obs_list, mode="real"):
    ev = tmp_path / "ev"; ev.mkdir()
    f = ev / "a.pdf"; f.write_bytes(b"x")
    sha = hashlib.sha256(b"x").hexdigest()
    store = tmp_path / "d"
    store = ArchiveStore(store)
    for o in obs_list:
        o["evidence_sha256"] = sha
    r = validate_published(pack(*obs_list, data_mode=mode))
    assert r.ok, r.diagnostics
    archive_published(r, {o["observation_id"]: f for o in obs_list}, store, evidence_dir=ev)
    return store


def test_series_separate_by_source_kind_basis_mode(tmp_path):
    a = obs(observation_id="a"); b = obs(observation_id="b", provider="StockAnalysis")
    c = obs(observation_id="c", accounting_basis="gaap"); d = obs(observation_id="d", metric_kind="forward_pe")
    store = setup(tmp_path, a, b, c, d)
    keys = {series_key(o) for o in store.all_observations()}
    assert len(keys) == 4
    real = obs(observation_id="e"); 
    assert series_key({**real, "data_mode": "synthetic"}) != series_key({**real, "data_mode": "real"})


def test_history_sorted_by_observed_at_and_keeps_dates(tmp_path):
    o1 = obs(observation_id="a", observed_at="2026-11-08T10:00:00+00:00", source_as_of="2026-09-30")
    o2 = obs(observation_id="b", observed_at="2026-11-01T10:00:00+00:00", source_as_of="2026-09-30", value="30")
    store = setup(tmp_path, o1, o2)
    key = series_key({**o1, "data_mode": "real"})
    hist = list_observations(key, store)
    assert [h["observation_id"] for h in hist] == ["b", "a"]
    assert all(h["source_as_of"] == "2026-09-30" for h in hist)


def test_synthetic_and_real_never_share_series(tmp_path):
    store = setup(tmp_path, obs(observation_id="a"), mode="synthetic")
    k_real = series_key({**obs(), "data_mode": "real"})
    assert list_observations(k_real, store) == []
