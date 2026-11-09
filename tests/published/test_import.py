import copy
import json

import pytest

from nasdaq100_pe.published.importer import MAX_IMPORT_BYTES, validate_published

H = "a" * 64


def obs(**kw):
    base = {
        "observation_id": "o1",
        "provider": "Invesco",
        "instrument": "QQQ",
        "metric_label_original": "P/E (TTM)",
        "metric_kind": "trailing_pe",
        "value": "31.25",
        "unit": "x",
        "source_as_of": "2026-09-30",
        "observed_at": "2026-11-08T10:00:00+00:00",
        "source_url": "https://www.invesco.com/qqq.pdf",
        "evidence_sha256": H,
        "evidence_locator": "p1 table 2",
        "period_basis": "unknown",
        "accounting_basis": "unknown",
        "loss_treatment": "unknown",
        "methodology_status": "unknown",
        "entry_mode": "manual",
    }
    base.update(kw)
    return base


def pack(*observations, **kw):
    p = {"schema_version": "1", "data_mode": "real", "observations": list(observations)}
    p.update(kw)
    return json.dumps(p).encode()


def paths(res):
    return {d["path"] for d in res.diagnostics}


def test_accepts_trailing_and_forward():
    res = validate_published(pack(obs(), obs(observation_id="o2", metric_kind="forward_pe", metric_label_original="Forward PE")))
    assert res.ok and res.exit_code == 0
    assert [o["metric_kind"] for o in res.observations] == ["trailing_pe", "forward_pe"]
    assert res.publication_status == "not_published"


def test_quote_date_not_metric_date():
    # 页面报价日期不得被当作 source_as_of；缺省必须保持 null
    o = obs(source_as_of=None, page_quote_date="2026-11-07")
    res = validate_published(pack(o))
    assert res.ok
    assert res.observations[0]["source_as_of"] is None


def test_quote_date_not_backfilled_when_field_missing():
    o = obs()
    del o["source_as_of"]
    res = validate_published(pack(o))
    assert not res.ok and "observations[0].source_as_of" in paths(res)


def test_unknown_basis_preserved():
    res = validate_published(pack(obs(metric_kind="forward_pe", metric_label_original="forwardPE")))
    o = res.observations[0]
    assert o["period_basis"] == "unknown" and o["accounting_basis"] == "unknown" and o["loss_treatment"] == "unknown"


def test_forward_name_does_not_imply_fy1():
    res = validate_published(pack(obs(metric_kind="forward_pe", period_basis="FY1")))
    # 声明 FY1 须同时给出依据；无依据拒绝
    assert not res.ok and "observations[0].period_basis" in paths(res)


@pytest.mark.parametrize("field,val", [
    ("source_as_of", "2026/09/30"),
    ("source_as_of", "2026-13-40"),
    ("observed_at", "2026-11-08T10:00:00"),
    ("metric_kind", "peg"),
    ("unit", "pct"),
    ("entry_mode", "robot"),
    ("value", 31.25),
    ("value", "NaN"),
    ("value", "Infinity"),
    ("value", "abc"),
    ("source_url", "javascript:alert(1)"),
    ("source_url", "file:///etc/passwd"),
    ("evidence_sha256", "xyz"),
])
def test_invalid_field_rejected_with_path(field, val):
    res = validate_published(pack(obs(**{field: val})))
    assert not res.ok and res.exit_code == 2
    assert f"observations[0].{field}" in paths(res)
    assert res.observations == []


def test_missing_required_fields_rejected():
    for f in ["provider", "metric_label_original", "observed_at", "evidence_sha256", "evidence_locator", "source_url"]:
        o = obs()
        del o[f]
        res = validate_published(pack(o))
        assert not res.ok and f"observations[0].{f}" in paths(res), f


def test_duplicate_observation_id_rejected():
    res = validate_published(pack(obs(), obs()))
    assert not res.ok and "observations[1].observation_id" in paths(res)


def test_oversize_rejected():
    res = validate_published(b" " * (MAX_IMPORT_BYTES + 1))
    assert not res.ok and res.exit_code == 2 and "$" in paths(res)


def test_bad_json_and_non_utf8():
    assert validate_published(b"{nope").exit_code == 2
    assert validate_published(b"\xff\xfe").exit_code == 2


def test_synthetic_mode_marked():
    res = validate_published(pack(obs(), data_mode="synthetic"))
    assert res.ok and res.data_mode == "synthetic"
    assert validate_published(pack(obs(), data_mode="demo")).ok is False


def test_malicious_url_and_path_not_fetched(tmp_path, monkeypatch):
    import socket
    def boom(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(socket, "create_connection", boom)
    res = validate_published(pack(obs(source_url="http://evil.test/x", evidence_locator="../../etc/passwd")))
    assert res.ok  # 仅作为数据保存，不触发访问


def test_completeness_flags_missing_kind():
    res = validate_published(pack(obs()))
    assert res.completeness == {"trailing_pe": True, "forward_pe": False}


def test_unknown_extra_field_ignored_not_kept():
    res = validate_published(pack(obs(secret_token="x")))
    assert res.ok and "secret_token" not in res.observations[0]
