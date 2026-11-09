"""独立评审 Important #1–#8 的回归测试（先红后绿）。"""
import hashlib
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

from nasdaq100_pe.archive.backup import backup, restore
from nasdaq100_pe.archive.evidence import archive_published
from nasdaq100_pe.archive.store import ArchiveStore
from nasdaq100_pe.calendar import CalendarUnknown, TradingCalendar
from nasdaq100_pe.normalize.supplements import import_supplements, list_supplements
from nasdaq100_pe.publisher.local import ReleaseSelection, build_local_release
from nasdaq100_pe.published.importer import validate_published
from nasdaq100_pe.validate.eligibility import EligibilityError, assess_eligibility
from nasdaq100_pe.validate.input import validate_research_input
from nasdaq100_pe.method import MethodSpec
from tests.integration.test_research_pipeline import ctx, full, write, D0, T
from tests.published.test_import import obs, pack
from tests.research_fixtures import dump, mod

CAL = TradingCalendar.load()
M = MethodSpec.load()


def iv_of(d):
    return validate_research_input(dump(d), M)


# ---- #1 W 与权重证据日期绑定 ----
def test_w_must_equal_weights_date_even_for_strict():
    d = full()
    d["weights"]["date"] = "2026-01-02"
    with pytest.raises(EligibilityError) as e:
        assess_eligibility(iv_of(d), ctx(), CAL)
    assert e.value.code == "WEIGHT_DATE_MISMATCH"
    d = full(); d["universe"]["as_of"] = "2026-01-02"
    with pytest.raises(EligibilityError) as e:
        assess_eligibility(iv_of(d), ctx(), CAL)
    assert e.value.code == "WEIGHT_DATE_MISMATCH"


# ---- #2 更正覆盖原值 ----
def mk_pub(tmp_path, *items):
    ev = tmp_path / "ev"; ev.mkdir(exist_ok=True); f = ev / "a"; f.write_bytes(b"x")
    sha = hashlib.sha256(b"x").hexdigest()
    store = ArchiveStore(tmp_path / "d")
    for o in items:
        o["evidence_sha256"] = sha
    r = validate_published(pack(*items)); assert r.ok, r.diagnostics
    archive_published(r, {o["observation_id"]: f for o in items}, store, evidence_dir=ev)
    return store


def test_correction_marks_original_superseded_in_release(tmp_path):
    store = mk_pub(tmp_path, obs(observation_id="z-orig", value="258.5"),
                   obs(observation_id="a-fix", value="25.85", corrects_observation_id="z-orig", correction_reason="转录错误"))
    rel = build_local_release(ReleaseSelection(), store)
    ser = json.loads((rel.path / "observations.json").read_text())["series"][0]["observations"]
    by = {o["observation_id"]: o for o in ser}
    assert by["z-orig"]["superseded_by"] == "a-fix" and "superseded_by" not in by["a-fix"]
    assert ser[-1]["observation_id"] == "a-fix"          # 更正排在被更正者之后


# ---- #3 时间戳统一 UTC ----
def test_observed_at_normalised_to_utc_and_latest_is_correct(tmp_path):
    r = validate_published(pack(obs(observed_at="2026-11-09T08:00:00+08:00")))
    assert r.observations[0]["observed_at"] == "2026-11-09T00:00:00+00:00"
    store = mk_pub(tmp_path, obs(observation_id="cn", observed_at="2026-11-09T08:00:00+08:00", value="1"),
                   obs(observation_id="utc", observed_at="2026-11-09T05:00:00Z", value="2"))
    assert [o["observation_id"] for o in store.all_observations()] == ["cn", "utc"]


def test_analysis_context_T_normalised_to_utc():
    c = ctx(T=datetime(2026, 11, 8, 20, 0, tzinfo=timezone(timedelta(hours=8))))
    assert c.as_dict()["T"] == "2026-11-08T12:00:00+00:00"


# ---- #4 研究价格门槛 ----
def test_non_usd_prices_and_eps_rejected_in_research_path():
    d = full()
    for p in d["prices"]: p["currency"] = "EUR"
    for e in d["earnings"]: e["currency"] = "EUR"
    v = assess_eligibility(iv_of(d), ctx(), CAL)
    assert all(s.ttm is None for s in v.securities) and any(x["code"] == "CURRENCY_NOT_USD" for x in v.diagnostics)


def test_real_mode_prices_need_evidence():
    d = full(); d["data_mode"] = "real"
    v = assess_eligibility(iv_of(d), ctx(data_mode="real"), CAL)
    assert all(s.ttm is None for s in v.securities) and any(x["code"] == "PRICE_NO_EVIDENCE" for x in v.diagnostics)
    for p in d["prices"]: p.update(evidence_sha256="e" * 64, locator="row1")
    v = assess_eligibility(iv_of(d), ctx(data_mode="real"), CAL)
    assert all(s.ttm is not None for s in v.securities)


def test_bad_session_or_feed_when_present_rejected():
    d = full()
    d["prices"][0]["feed"] = "iex"
    v = assess_eligibility(iv_of(d), ctx(), CAL)
    assert v.securities[0].ttm is None and any(x["code"] == "FEED_NOT_CONSOLIDATED" for x in v.diagnostics)


# ---- #5 备份含补录 ----
def test_backup_restore_keeps_supplements(tmp_path):
    ev = tmp_path / "ev"; ev.mkdir(); (ev / "pr.pdf").write_bytes(b"pr")
    sha = hashlib.sha256(b"pr").hexdigest()
    store = ArchiveStore(tmp_path / "d")
    sp = {"issuer_id": "cik-0000000001", "start": "2026-07-01", "end": "2026-09-30", "eps": "1.4", "currency": "USD", "form": "8-K",
          "filed": "2026-10-30", "evidence_sha256": sha, "locator": "p3", "reviewed_at": "2026-11-09T00:00:00+00:00"}
    import_supplements(json.dumps({"schema_version": "1", "supplements": [sp]}).encode(), ev, store)
    backup(store, tmp_path / "bk")
    new = restore(tmp_path / "bk", tmp_path / "r")
    assert len(list_supplements(new, "cik-0000000001")) == 1


# ---- #6 SEC 桥接用 checked_at 判新鲜度 ----
def test_earnings_freshness_uses_checked_at_not_content_fetch_time():
    d = full(fetched=(T - timedelta(hours=1)).isoformat())
    old = (T - timedelta(days=30)).isoformat()
    for e in d["earnings"]:
        e["fetched_at"] = old                       # 内容获取很久以前
        e["checked_at"] = (T - timedelta(hours=1)).isoformat()   # 但刚刚复核过
    v = assess_eligibility(iv_of(d), ctx(freshness_policy="daily"), CAL)
    assert all(s.ttm is not None for s in v.securities)
    for e in d["earnings"]:
        del e["checked_at"]
    v = assess_eligibility(iv_of(d), ctx(freshness_policy="daily"), CAL)
    assert all(s.ttm is None for s in v.securities)


def test_to_input_rows_carry_checked_at():
    from nasdaq100_pe.identity.models import SecurityIdentity
    from nasdaq100_pe.normalize.quarters import select_ttm
    from nasdaq100_pe.validate.earnings import EarningsBatch, validate_earnings
    from tests.sec_fixtures import facts, four_quarters
    b = EarningsBatch("i1", "1", "USD", None, select_ttm(facts(four_quarters())), checked_at="2026-11-09T00:00:00+00:00",
                      content_fetched_at="2026-10-01T00:00:00+00:00")
    r = validate_earnings(b, [SecurityIdentity("a", "i1", "common", "A", "a", "T", "p")]).to_input_rows()[0]
    assert r["checked_at"] == "2026-11-09T00:00:00+00:00" and r["fetched_at"] == "2026-10-01T00:00:00+00:00"


# ---- #7 研究发布累积 + 修订取最大 ----
def cli(root, *a):
    env = dict(os.environ, NDX_PE_DATA_ROOT=str(root))
    return subprocess.run([sys.executable, "-m", "nasdaq100_pe.cli", *a], capture_output=True, text=True, env=env)


def test_second_day_snapshot_builds_cumulatively(tmp_path):
    root = tmp_path / "d"
    a = write(tmp_path, full(), "a.json")
    ra = json.loads(cli(root, "import", "--file", str(a), "--basket-date", "2026-11-06", "--price-date", "2026-11-06",
                        "--observed-at", "2026-11-08T12:00:00+00:00").stdout)
    assert cli(root, "build-local", "--snapshot", ra["snapshot_id"]).returncode == 0
    d = full()
    d["weights"]["date"] = d["universe"]["as_of"] = "2026-11-05"
    for p in d["prices"]: p["date"] = "2026-11-05"
    b = write(tmp_path, d, "b.json")
    rb = json.loads(cli(root, "import", "--file", str(b), "--basket-date", "2026-11-05", "--price-date", "2026-11-05",
                        "--observed-at", "2026-11-08T12:00:00+00:00").stdout)
    r = cli(root, "build-local", "--snapshot", rb["snapshot_id"])
    assert r.returncode == 0, r.stdout
    rel = json.loads(r.stdout)["release_id"]
    man = json.loads((root / "releases" / rel / "manifest.json").read_text())
    assert {s["D"] for s in man["snapshots"]} == {"2026-11-05", "2026-11-06"}


def test_regression_uses_max_revision_per_key(tmp_path):
    from nasdaq100_pe.publisher.pointer import _regresses
    cur = {"kind": "research", "snapshots": [{"series_key": "s", "D": "d", "revision_seq": 2, "snapshot_id": "zzz"},
                                              {"series_key": "s", "D": "d", "revision_seq": 1, "snapshot_id": "aaa"}]}
    new = {"kind": "research", "snapshots": [{"series_key": "s", "D": "d", "revision_seq": 2, "snapshot_id": "b"}]}
    assert _regresses(new, cur) is False


# ---- #8 交易日历 ----
def test_non_trading_or_unknown_D_rejected_for_current_and_strict():
    sat = date(2026, 11, 7)
    d = full()
    d["weights"]["date"] = d["universe"]["as_of"] = sat.isoformat()
    for p in d["prices"]: p["date"] = sat.isoformat()
    with pytest.raises(EligibilityError) as e:
        assess_eligibility(iv_of(d), ctx(W=sat, D=sat), CAL)
    assert e.value.code == "D_NOT_TRADING_DAY"
    d2 = full(); d2["weights"]["date"] = d2["universe"]["as_of"] = "2027-03-01"
    with pytest.raises(EligibilityError) as e:
        assess_eligibility(iv_of(d2), ctx(W=date(2027, 3, 1), D=date(2027, 3, 1)), CAL)
    assert e.value.code == "CALENDAR_UNKNOWN"


def test_calendar_loads_and_merges_all_year_files(tmp_path):
    for y in (2026, 2027):
        (tmp_path / f"calendar_us_{y}.json").write_text(json.dumps({
            "version": f"t{y}", "source": "t", "covers_from": f"{y}-01-01", "covers_to": f"{y}-12-31", "closed": [f"{y}-01-01"], "half_days": []}))
    c = TradingCalendar.load_dir(tmp_path)
    assert c.covers_from == date(2026, 1, 1) and c.covers_to == date(2027, 12, 31)
    assert not c.is_trading_day(date(2027, 1, 1)) and c.is_trading_day(date(2027, 1, 4))
