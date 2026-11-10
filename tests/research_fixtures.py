"""研究输入合成夹具（仅测试；data_mode 由调用方标明为合成）。"""
import copy
import json
from datetime import date, timedelta
from decimal import Decimal

H = "c" * 64


def ttm_evidence(eps, latest_quarter_end="2026-09-30"):
    """Four synthetic consecutive reported quarters whose sum is eps."""
    end = date.fromisoformat(latest_quarter_end)
    value = str(Decimal(str(eps)) / 4)
    quarters = []
    for n in reversed(range(4)):
        qend = end - timedelta(days=91 * n)
        start = qend - timedelta(days=90)
        quarters.append({"start": start.isoformat(), "end": qend.isoformat(), "val": value,
                         "filed": (qend + timedelta(days=30)).isoformat(), "accn": f"synthetic-{n}",
                         "form": "10-Q", "fp": f"Q{4-n}", "manual": False})
    return {"quarters": quarters, "calculation_path": "reported_quarter_eps_sum",
            "evidence": {"cik": "synthetic", "content_sha256": H,
                         "locator": "us-gaap/EarningsPerShareDiluted/USD/shares", "quarters": quarters},
            "source_id": "s1"}


def sec(sid, issuer=None, cls="common", ticker=None, sector="Tech", **kw):
    d = {"security_id": sid, "issuer_id": issuer or sid, "share_class": cls, "ticker": ticker or sid.upper(),
         "name": f"{sid} Inc", "sector": sector, "sector_source": "provider", "asset_class": "equity"}
    d.update(kw)
    return d


def base_input(weights=("0.5", "0.3", "0.2"), mode="official_full", scope="full", excluded=None):
    ids = ["a", "b", "c"][: len(weights)]
    return {
        "schema_version": "1", "method_version": "1", "data_mode": "synthetic",
        "sources": [{"source_id": "s1", "content_sha256": H, "fetched_at": "2026-11-09T00:00:00+00:00", "locator": "t1"}],
        "universe": {"as_of": "2026-11-06", "source_id": "s1", "listing_scope": scope, "securities": [sec(i) for i in ids]},
        "weights": {"mode": mode, "date": "2026-11-06", "source_id": "s1",
                    "items": [{"security_id": i, "weight": w} for i, w in zip(ids, weights)],
                    "excluded": excluded or []},
        "prices": [], "earnings": [],
    }


def dump(d):
    return json.dumps(d).encode()


def mod(d, fn):
    d = copy.deepcopy(d); fn(d); return d
