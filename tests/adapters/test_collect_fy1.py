import importlib.util
import io
import urllib.error
from pathlib import Path

spec = importlib.util.spec_from_file_location("collect_fy1", Path(__file__).resolve().parents[2] / "scripts" / "collect_fy1.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)


def test_archives_both_responses_and_skips_what_is_already_indexed(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url); return b'{"data": 1}'
    idx = mod.collect(["AAPL"], tmp_path, {}, fetch=fetch, sleep=lambda s: None, now=lambda: "t")
    e = idx["AAPL"]
    assert set(e) == {"forecast", "surprise"} and e["forecast"]["fetched_at"] == "t"
    assert (tmp_path / "nasdaq-forecast" / e["forecast"]["file"]).read_bytes() == b'{"data": 1}'
    mod.collect(["AAPL"], tmp_path, idx, fetch=fetch, sleep=lambda s: None)
    assert len(calls) == 2                                  # 已有哈希的不重复请求


def test_refusal_stops_the_run_without_retrying(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        raise urllib.error.HTTPError(url, 403, "Forbidden", None, io.BytesIO(b""))
    idx = mod.collect(["AAPL", "MSFT"], tmp_path, {}, fetch=fetch, sleep=lambda s: None)
    assert len(calls) == 1 and idx["AAPL"]["forecast"]["reason"] == "HTTP_403" and "MSFT" not in idx
