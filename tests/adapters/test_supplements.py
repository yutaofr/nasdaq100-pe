import hashlib
import json
import subprocess
import sys
import os
from datetime import datetime, timezone

import pytest

from nasdaq100_pe.adapters.sec import SecClient, fetch_earnings, read_cached
from nasdaq100_pe.archive.store import ArchiveError, ArchiveStore
from nasdaq100_pe.normalize.quarters import select_ttm
from nasdaq100_pe.normalize.supplements import import_supplements, list_supplements
from tests.sec_fixtures import body, facts, four_quarters

NOW = datetime(2026, 11, 9, tzinfo=timezone.utc)
ISSUER = "cik-0000001234"


def pkg(sha, **kw):
    s = {"issuer_id": ISSUER, "start": "2026-07-01", "end": "2026-09-30", "eps": "1.40", "currency": "USD", "form": "8-K",
         "filed": "2026-10-30", "evidence_sha256": sha, "locator": "ex99.1 p3 table 2", "reviewed_at": "2026-11-09T00:00:00+00:00"}
    s.update(kw)
    return json.dumps({"schema_version": "1", "supplements": [s]}).encode()


@pytest.fixture
def env(tmp_path):
    ev = tmp_path / "ev"; ev.mkdir(); (ev / "pr.pdf").write_bytes(b"press release")
    return ev, hashlib.sha256(b"press release").hexdigest(), ArchiveStore(tmp_path / "d")


def test_supplement_archived_with_evidence(env):
    ev, sha, store = env
    r = import_supplements(pkg(sha), ev, store)
    assert r[0]["eps"] == "1.40" and (store.root / "raw" / sha).read_bytes() == b"press release"
    assert len(list_supplements(store, ISSUER)) == 1
    import_supplements(pkg(sha), ev, store)           # 幂等
    assert len(list_supplements(store, ISSUER)) == 1


@pytest.mark.parametrize("mut,code", [
    (dict(evidence_sha256="0" * 64), "HASH_MISMATCH"),
    (dict(locator=""), "SUPPLEMENT_INVALID"),
    (dict(reviewed_at=None), "SUPPLEMENT_INVALID"),
    (dict(eps="NaN"), "SUPPLEMENT_INVALID"),
    (dict(start="2026-09-30", end="2026-07-01"), "SUPPLEMENT_INVALID"),
    (dict(currency=""), "SUPPLEMENT_INVALID"),
])
def test_invalid_supplement_rejected_nothing_written(env, mut, code):
    ev, sha, store = env
    p = json.loads(pkg(sha)); p["supplements"][0].update(mut)
    with pytest.raises(ArchiveError, match=code):
        import_supplements(json.dumps(p).encode(), ev, store)
    assert list_supplements(store, ISSUER) == []


def test_missing_evidence_file_rejected(env):
    ev, sha, store = env
    empty = ev.parent / "empty"; empty.mkdir()
    with pytest.raises(ArchiveError, match="EVIDENCE_NOT_FOUND"):
        import_supplements(pkg(sha), empty, store)


def test_supplement_fills_missing_q4_and_marks_manual():
    es = four_quarters(); missing = es.pop(-1)                 # 缺最近一季
    sup = [{"start": missing["start"], "end": missing["end"], "eps": "1.40", "currency": "USD", "form": "8-K", "filed": "2026-10-30",
            "evidence_sha256": "e" * 64, "locator": "p3", "reviewed_at": "2026-11-09T00:00:00+00:00"}]
    assert select_ttm(facts(es)).status == "missing_quarter"
    r = select_ttm(facts(es), supplements=sup)
    assert r.status == "ok" and float(r.ttm_eps) == pytest.approx(5.0)
    last = r.quarters[-1]
    assert last["manual"] is True and last["evidence_sha256"] == "e" * 64 and last["locator"] == "p3"
    assert not any(q.get("manual") for q in r.quarters[:-1])


def test_supplement_conflicting_with_sec_value_goes_manual_review():
    es = four_quarters(); last = es[-1]
    sup = [{"start": last["start"], "end": last["end"], "eps": "9.99", "currency": "USD", "form": "8-K", "filed": "2026-10-30",
            "evidence_sha256": "e" * 64, "locator": "p3", "reviewed_at": "2026-11-09T00:00:00+00:00"}]
    r = select_ttm(facts(es), supplements=sup)
    assert r.status == "needs_manual_review" and "MANUAL_CONFLICT" in r.reasons


def test_supplement_equal_to_sec_value_is_harmless():
    es = four_quarters(); last = es[-1]
    sup = [{"start": last["start"], "end": last["end"], "eps": str(last["val"]), "currency": "USD", "form": "8-K", "filed": "2026-10-30",
            "evidence_sha256": "e" * 64, "locator": "p3", "reviewed_at": "2026-11-09T00:00:00+00:00"}]
    assert select_ttm(facts(es), supplements=sup).status == "ok"


def test_foreign_currency_supplement_not_mixed():
    es = four_quarters(); missing = es.pop(-1)
    sup = [{"start": missing["start"], "end": missing["end"], "eps": "1.40", "currency": "EUR", "form": "8-K", "filed": "x",
            "evidence_sha256": "e" * 64, "locator": "p3", "reviewed_at": "t"}]
    r = select_ttm(facts(es), supplements=sup)
    assert r.status == "missing_quarter" and "SUPPLEMENT_CURRENCY_MISMATCH" in r.reasons


class Fake:
    def __init__(self, r): self.r = r
    def __call__(self, u, h): return self.r


def test_fetch_and_cached_use_stored_supplements(env):
    ev, sha, store = env
    es = four_quarters(); gone = es.pop(-1)
    c = SecClient(Fake(body(facts(es))), user_agent="ua", sleep=lambda s: None)
    assert fetch_earnings(ISSUER, store, c, now=NOW).ttm.status == "missing_quarter"
    import_supplements(pkg(sha, start=gone["start"], end=gone["end"]), ev, store)
    assert fetch_earnings(ISSUER, store, c, now=NOW).ttm.status == "ok"
    b = read_cached(ISSUER, store)
    assert b.ttm.status == "ok" and any(q.get("manual") for q in b.ttm.quarters)


def test_cli_supplement_and_ttm_report(tmp_path):
    ev = tmp_path / "ev"; ev.mkdir(); (ev / "pr.pdf").write_bytes(b"press release")
    sha = hashlib.sha256(b"press release").hexdigest()
    f = tmp_path / "s.json"; f.write_bytes(pkg(sha))
    env = dict(os.environ, NDX_PE_DATA_ROOT=str(tmp_path / "d"))
    run = lambda *a: subprocess.run([sys.executable, "-m", "nasdaq100_pe.cli", *a], capture_output=True, text=True, env=env)
    r = run("import-supplement", "--file", str(f), "--evidence-dir", str(ev))
    assert r.returncode == 0 and json.loads(r.stdout)["imported"] == 1
    bad = tmp_path / "b.json"; bad.write_bytes(pkg("0" * 64))
    assert run("import-supplement", "--file", str(bad), "--evidence-dir", str(ev)).returncode == 6
    ttm = run("ttm-report", "--issuer", ISSUER)
    assert ttm.returncode == 2          # 无 SEC 缓存：明确报错而非空结果
