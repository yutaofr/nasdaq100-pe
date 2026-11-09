"""SEC companyfacts 形态的合成夹具（测试用，数值为虚构）。"""
import json
from datetime import date, timedelta


def q(start, end, val, accn, filed, form="10-Q", fp="Q1"):
    return {"start": start, "end": end, "val": val, "accn": accn, "fy": int(end[:4]), "fp": fp, "form": form, "filed": filed}


def facts(entries, tag="EarningsPerShareDiluted", unit="USD/shares"):
    return {"cik": 1234, "entityName": "TestCo", "facts": {"us-gaap": {tag: {"units": {unit: entries}}}}}


def four_quarters(vals=(1.10, 1.20, 1.30, 1.40), last_end="2026-09-30"):
    e = date.fromisoformat(last_end)
    out = []
    for i, v in enumerate(reversed(vals)):
        end = e - timedelta(days=91 * i)
        start = end - timedelta(days=90)
        out.append(q(start.isoformat(), end.isoformat(), v, f"0001-26-{i}", (end + timedelta(days=30)).isoformat()))
    return sorted(out, key=lambda x: x["end"])


def contiguous(periods, vals):
    """periods: list of (start,end); 校验由测试自己保证连续。"""
    return [q(s, e, v, f"a-{i}", e) for i, ((s, e), v) in enumerate(zip(periods, vals))]


def body(d):
    return json.dumps(d).encode()
