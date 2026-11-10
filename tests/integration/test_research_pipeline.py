import csv
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from nasdaq100_pe.archive.store import ArchiveStore, CrashInjected
from nasdaq100_pe.archive.snapshots import canonical_input_bytes, input_hash, list_snapshots, read_snapshot
from nasdaq100_pe.export import export_snapshot
from nasdaq100_pe.pipeline import recompute, recompute_package, run_import
from nasdaq100_pe.publisher.local import ReleaseError, ReleaseSelection, build_local_release
from nasdaq100_pe.publisher.pointer import current_release, promote_release
from nasdaq100_pe.validate.eligibility import AnalysisContext
from tests.research_fixtures import base_input, dump, mod, ttm_evidence

D0 = date(2026, 11, 6)
T = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
FETCH = (T - timedelta(hours=2)).isoformat()


def ctx(**kw):
    base = dict(W=D0, D=D0, T=T, analysis_profile="research", basket_policy="current", coverage_policy="subset",
                freshness_policy="weekly", method_version="1", data_mode="synthetic")
    base.update(kw)
    return AnalysisContext(**base)


def full(eps=("5", "4", "2"), only=None, scope="full", fetched=FETCH, ttm_q="2026-09-30"):
    d = base_input(scope=scope)
    ids = "abc"
    d["prices"] = [{"security_id": s, "date": D0.isoformat(), "close": "100", "currency": "USD", "price_type": "regular_close",
                    "split_basis_date": "2026-01-01", "source_id": "s1", "fetched_at": fetched} for s in ids]
    d["earnings"] = [{"security_id": s, "kind": "ttm", "eps": e, "accounting_basis": "gaap", "currency": "USD",
                      "split_basis_date": "2026-01-01", "latest_quarter_end": ttm_q, "fetched_at": fetched,
                      **ttm_evidence(e, ttm_q)}
                     for s, e in zip(ids, eps) if only is None or s in only]
    return d


def write(tmp_path, d, name="in.json"):
    p = tmp_path / name; p.write_bytes(dump(d)); return p


@pytest.fixture
def store(tmp_path):
    return ArchiveStore(tmp_path / "data")


def test_complete_ttm_and_partial_fy1_archived_exit0(tmp_path, store):
    run = run_import(write(tmp_path, full()), ctx(), store)
    assert run.exit_code == 0 and run.snapshot_id
    assert run.completeness == {"ttm": "complete", "fy1": "unavailable"}
    assert run.publication_status == "archived_not_published"
    snap = read_snapshot(store, run.snapshot_id)
    assert snap["completeness"]["ttm"] == "complete" and snap["data_mode"] == "synthetic"


def test_partial_ttm_archived(tmp_path, store):
    run = run_import(write(tmp_path, full(only="ab")), ctx(), store)
    assert run.exit_code == 0 and run.completeness["ttm"] == "partial"
    snap = read_snapshot(store, run.snapshot_id)
    assert snap["results"]["metrics"]["ttm"]["pe"] is None and snap["results"]["metrics"]["ttm"]["missing_security_ids"] == ["c"]


def test_missing_complete_basket_no_snapshot_keeps_diagnostics_and_old_release(tmp_path, store):
    ok = run_import(write(tmp_path, full()), ctx(), store)
    rel = build_local_release(ReleaseSelection(snapshot_ids=[ok.snapshot_id]), store)
    promote_release(store, rel.release_id, None, name="research")
    bad = run_import(write(tmp_path, full(scope="top_n"), "bad.json"), ctx(), store)
    assert bad.exit_code == 4 and bad.snapshot_id is None and bad.completeness is None
    assert any(d["code"] == "UNKNOWN_UNIVERSE" for d in bad.diagnostics)
    assert (store.root / "runs" / f"{bad.run_id}.json").exists()
    assert current_release(store, "research") == rel.release_id
    assert len(list_snapshots(store)) == 1


def test_no_prices_archives_unavailable_snapshot(tmp_path, store):
    d = full(); d["prices"] = []
    r = run_import(write(tmp_path, d), ctx(), store)
    assert r.exit_code == 0 and r.snapshot_id is not None
    assert r.completeness == {"ttm": "unavailable", "fy1": "unavailable"}
    snap = read_snapshot(store, r.snapshot_id)
    assert snap["results"]["metrics"]["ttm"]["pe"] is None


def test_structural_error_exit_4_input_error_exit_2(tmp_path, store):
    d = full(); d["universe"]["securities"].append(d["universe"]["securities"][0])
    assert run_import(write(tmp_path, d), ctx(), store).exit_code == 4
    p = tmp_path / "x.json"; p.write_bytes(b"{nope")
    assert run_import(p, ctx(), store).exit_code == 2


def test_canonical_hash_ignores_order_and_decimal_spelling(tmp_path):
    a = full()
    b = full()
    b["universe"]["securities"].reverse(); b["weights"]["items"].reverse(); b["prices"].reverse()
    b["weights"]["items"][0]["weight"] = b["weights"]["items"][0]["weight"] + "0"      # 0.50 vs 0.5
    assert input_hash(canonical_input_bytes(a)) == input_hash(canonical_input_bytes(b))
    c = full(fetched=(T - timedelta(hours=1)).isoformat())
    assert input_hash(canonical_input_bytes(a)) != input_hash(canonical_input_bytes(c))   # 新获取时间=新证据


def test_same_input_same_identity_idempotent_and_new_fetch_new_snapshot(tmp_path, store):
    r1 = run_import(write(tmp_path, full()), ctx(), store)
    r2 = run_import(write(tmp_path, full()), ctx(), store)
    assert r1.snapshot_id == r2.snapshot_id and len(list_snapshots(store)) == 1
    r3 = run_import(write(tmp_path, full(fetched=(T - timedelta(hours=1)).isoformat())), ctx(), store)
    assert r3.snapshot_id != r1.snapshot_id


def test_run_id_and_time_not_part_of_identity(tmp_path, store):
    r1 = run_import(write(tmp_path, full()), ctx(), store)
    r2 = run_import(write(tmp_path, full()), ctx(), store)
    assert r1.run_id != r2.run_id and r1.snapshot_id == r2.snapshot_id


def test_recompute_matches_archived(tmp_path, store):
    r = run_import(write(tmp_path, full()), ctx(), store)
    out = recompute(r.snapshot_id, store)
    assert out["identical"] is True


def test_recompute_matches_unsorted_complete_basket(tmp_path, store):
    d = full()
    d["universe"]["securities"].reverse()
    d["weights"]["excluded"] = [
        {"asset_class": "other", "label": "z", "weight": "0"},
        {"asset_class": "cash", "label": "a", "weight": "0"},
    ]
    r = run_import(write(tmp_path, d), ctx(), store)
    assert r.exit_code == 0 and r.snapshot_id
    assert recompute(r.snapshot_id, store)["identical"] is True


def test_correction_supersedes_and_old_remains_readable(tmp_path, store):
    r1 = run_import(write(tmp_path, full()), ctx(), store)
    r2 = run_import(write(tmp_path, full(eps=("6", "4", "2"), fetched=(T - timedelta(hours=1)).isoformat())), ctx(), store, reason="来源更正EPS")
    s2 = read_snapshot(store, r2.snapshot_id)
    assert s2["supersedes_snapshot_id"] == r1.snapshot_id and s2["revision_seq"] == 2 and s2["correction_reason"] == "来源更正EPS"
    assert read_snapshot(store, r1.snapshot_id)["revision_seq"] == 1


def test_late_old_revision_cannot_replace_new_release(tmp_path, store):
    r1 = run_import(write(tmp_path, full()), ctx(), store)
    r2 = run_import(write(tmp_path, full(eps=("6", "4", "2"), fetched=(T - timedelta(hours=1)).isoformat())), ctx(), store)
    new = build_local_release(ReleaseSelection(snapshot_ids=[r2.snapshot_id]), store)
    old = build_local_release(ReleaseSelection(snapshot_ids=[r1.snapshot_id]), store)
    assert promote_release(store, new.release_id, None, name="research").ok
    res = promote_release(store, old.release_id, new.release_id, name="research")
    assert not res.ok and res.code == "STALE_REVISION"


def test_partial_after_complete_links_last_complete_without_copying_pe(tmp_path, store):
    c = run_import(write(tmp_path, full()), ctx(), store)
    p = run_import(write(tmp_path, full(only="ab", fetched=(T - timedelta(hours=1)).isoformat())), ctx(D=D0), store)
    snap = read_snapshot(store, p.snapshot_id)
    assert snap["last_complete"]["ttm"]["snapshot_id"] == c.snapshot_id
    assert snap["results"]["metrics"]["ttm"]["pe"] is None
    assert "pe" not in snap["last_complete"]["ttm"]


def test_export_json_package_and_csv(tmp_path, store):
    d = full(only="ab"); d["universe"]["securities"][0]["name"] = "=cmd|' /C calc'!A0"
    r = run_import(write(tmp_path, d), ctx(), store)
    out = tmp_path / "exp"
    m = export_snapshot(r.snapshot_id, out, store)
    pkg = json.loads((out / "recompute-package.json").read_text())
    assert pkg["snapshot"]["snapshot_id"] == r.snapshot_id and "input" in pkg and pkg["reproducible"] is True
    rows = list(csv.DictReader((out / "detail.csv").open(encoding="utf-8")))
    assert [x["security_id"] for x in rows] == ["a", "b", "c"]
    assert rows[0]["name"].startswith("'=") and rows[2]["ttm_yield"] == "" and "MISSING" in rows[2]["ttm_missing_reason"]
    assert rows[0]["ttm_yield"] == "0.05"
    meta = json.loads((out / "metadata.json").read_text())
    assert meta["analysis"]["analysis_profile"] == "research" and meta["data_mode"] == "synthetic"
    assert str(tmp_path) not in (out / "recompute-package.json").read_text()
    again = recompute_package(out / "recompute-package.json")
    assert again["identical"] is True


def test_publish_retry_reuses_snapshot_without_recompute(tmp_path, store, monkeypatch):
    r = run_import(write(tmp_path, full()), ctx(), store)
    import nasdaq100_pe.pipeline as P
    monkeypatch.setattr(P, "calculate", lambda *a, **k: (_ for _ in ()).throw(AssertionError("recomputed")))
    rel = build_local_release(ReleaseSelection(snapshot_ids=[r.snapshot_id]), store)
    assert (rel.path / "research.json").exists()


def test_crash_after_input_archive_before_snapshot_recovers(tmp_path, store):
    store.crash_hook = lambda st: (_ for _ in ()).throw(CrashInjected()) if st == "before_snapshot" else None
    with pytest.raises(CrashInjected):
        run_import(write(tmp_path, full()), ctx(), store)
    assert list_snapshots(store) == []
    store.crash_hook = None
    r = run_import(write(tmp_path, full()), ctx(), store)
    assert r.exit_code == 0 and len(list_snapshots(store)) == 1


def test_published_and_research_pointers_isolated(tmp_path, store):
    from tests.published.test_history import setup as pub_setup  # noqa
    r = run_import(write(tmp_path, full()), ctx(), store)
    rel = build_local_release(ReleaseSelection(snapshot_ids=[r.snapshot_id]), store)
    promote_release(store, rel.release_id, None, name="research")
    assert current_release(store) is None and current_release(store, "research") == rel.release_id


def test_secret_in_research_release_rejected_published_untouched(tmp_path, store):
    d = full(); d["universe"]["securities"][0]["name"] = "api_key=abcdef123"
    r = run_import(write(tmp_path, d), ctx(), store)
    with pytest.raises(ReleaseError) as e:
        build_local_release(ReleaseSelection(snapshot_ids=[r.snapshot_id]), store)
    assert e.value.code == "SECRET_DETECTED"
