import importlib.util
import json
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('collect_nocp', Path(__file__).resolve().parents[2] / 'scripts/collect_nocp.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def response(day='11/13/2026', price='$171.51'):
    return json.dumps({'data': {'headers': {'price': 'Nasdaq Closing Price'},
                              'nocp': {'nocpTable': [{'date': day, 'price': price}], 'nocpChart': [{'z': {'details': 'DASH Close Price: ' + price}}]}}}).encode()


def test_provider_error_is_not_reported_as_parse_failure():
    body = b'{"data":null,"status":{"bCodeMessage":[{"code":1002,"errorMessage":"Nasdaq Historical NOCP only for Nasdaq Symbols"}]}}'
    assert mod.parse_nocp(body, '2026-11-13') == (None, 'NOCP_UNAVAILABLE_FOR_SYMBOL')


@pytest.mark.parametrize('price', ['-$1.00', 'NaN', '$1oops2', 'Infinity'])
def test_malformed_prices_cannot_become_valid_closes(price):
    assert mod.parse_nocp(response(price=price), '2026-11-13')[0] is None


def test_saved_response_recovers_refusal_without_network(tmp_path, monkeypatch):
    basket = tmp_path / 'input.json'
    basket.write_text(json.dumps({'universe': {'securities': [{'ticker': 'DASH'}]}}))
    saved = tmp_path / 'saved.json'
    saved.write_bytes(response())
    index = tmp_path / 'index.json'
    index.write_text('{"DASH":{"reason":"HTTP_403"}}')
    monkeypatch.setattr(sys, 'argv', ['collect_nocp', '--input', str(basket), '--evidence', str(tmp_path),
        '--target-date', '2026-11-13', '--index', str(index), '--response', f'DASH={saved}'])
    def offline(*args, **kwargs):
        pytest.fail('saved response must not require a network request')
    monkeypatch.setattr(mod.urllib.request, 'urlopen', offline)
    mod.main()
    entry = json.loads(index.read_text())['DASH']
    assert entry['close'] == '171.51'
    assert entry['date'] == '2026-11-13'
    assert entry['previous_failure']['reason'] == 'HTTP_403'
    assert (tmp_path / 'nasdaq-nocp' / f"DASH-d5-{entry['sha256']}.json").read_bytes() == saved.read_bytes()


def test_wrong_date_saved_response_leaves_index_untouched(tmp_path, monkeypatch, capsys):
    basket = tmp_path / 'input.json'
    basket.write_text(json.dumps({'universe': {'securities': [{'ticker': 'DASH'}]}}))
    saved = tmp_path / 'saved.json'
    saved.write_bytes(response(day='11/12/2026'))
    index = tmp_path / 'index.json'
    original = '{"DASH":{"reason":"HTTP_403"}}'
    index.write_text(original)
    monkeypatch.setattr(sys, 'argv', ['collect_nocp', '--input', str(basket), '--evidence', str(tmp_path),
        '--target-date', '2026-11-13', '--index', str(index), '--response', f'DASH={saved}'])
    with pytest.raises(SystemExit):
        mod.main()
    assert index.read_text() == original
    assert 'DATE_NOT_IN_RESPONSE' in capsys.readouterr().err


def test_saved_response_rejects_other_symbol(tmp_path):
    saved = tmp_path / 'wrong.json'
    saved.write_bytes(response().replace(b'DASH Close', b'AAPL Close'))
    with pytest.raises(ValueError, match='SYMBOL_MISMATCH'):
        mod.read_saved_response(saved, 'DASH', '2026-11-13')


def test_saved_response_is_imported_before_other_symbols_refuse(tmp_path, monkeypatch):
    import urllib.error
    basket = tmp_path / 'input.json'
    basket.write_text(json.dumps({'universe': {'securities': [{'ticker': 'AAPL'}, {'ticker': 'DASH'}, {'ticker': 'MSFT'}]}}))
    saved = tmp_path / 'saved.json'
    saved.write_bytes(response())
    index = tmp_path / 'index.json'
    monkeypatch.setattr(sys, 'argv', ['collect_nocp', '--input', str(basket), '--evidence', str(tmp_path),
        '--target-date', '2026-11-13', '--index', str(index), '--response', f'DASH={saved}'])
    calls = []
    def refused(req, **kwargs):
        calls.append(req.full_url)
        raise urllib.error.HTTPError(req.full_url, 403, 'Forbidden', {}, None)
    monkeypatch.setattr(mod.urllib.request, 'urlopen', refused)
    mod.main()
    result = json.loads(index.read_text())
    assert result['DASH']['close'] == '171.51'
    assert result['AAPL']['reason'] == 'HTTP_403'
    assert 'MSFT' not in result
    assert len(calls) == 1


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body


def test_target_date_not_yet_published_stops_after_first_symbol(tmp_path, monkeypatch, capsys):
    basket = tmp_path / 'input.json'
    basket.write_text(json.dumps({'universe': {'securities': [{'ticker': 'AAPL'}, {'ticker': 'MSFT'}]}}))
    index = tmp_path / 'index.json'
    monkeypatch.setattr(sys, 'argv', ['collect_nocp', '--input', str(basket), '--evidence', str(tmp_path),
        '--target-date', '2026-11-16', '--index', str(index)])
    calls = []
    def latest_is_friday(req, **kwargs):
        calls.append(req.full_url)
        return FakeResponse(response(day='11/13/2026'))
    monkeypatch.setattr(mod.urllib.request, 'urlopen', latest_is_friday)
    monkeypatch.setattr(mod.time, 'sleep', lambda s: None)
    mod.main()
    result = json.loads(index.read_text())
    assert result['AAPL']['reason'] == 'TARGET_DATE_NOT_PUBLISHED_YET'
    assert result['AAPL']['latest_date'] == '2026-11-13'
    assert result['AAPL']['close'] is None
    assert 'MSFT' not in result
    assert len(calls) == 1
    assert json.loads(capsys.readouterr().out)['latest_published'] == '2026-11-13'


def test_date_older_than_response_window_is_not_reported_as_unpublished():
    assert mod.parse_nocp(response(day='11/13/2026'), '2026-11-02') == (None, 'DATE_NOT_IN_RESPONSE')


def test_index_directory_is_created_before_any_request(tmp_path, monkeypatch):
    basket = tmp_path / 'input.json'
    basket.write_text(json.dumps({'universe': {'securities': [{'ticker': 'AAPL'}]}}))
    index = tmp_path / 'research-2026-11-13' / 'index.json'
    monkeypatch.setattr(sys, 'argv', ['collect_nocp', '--input', str(basket), '--evidence', str(tmp_path),
        '--target-date', '2026-11-13', '--index', str(index)])
    def fetch(req, **kwargs):
        assert index.parent.is_dir(), 'index directory must exist before the first request'
        return FakeResponse(response().replace(b'DASH Close', b'AAPL Close'))
    monkeypatch.setattr(mod.urllib.request, 'urlopen', fetch)
    monkeypatch.setattr(mod.time, 'sleep', lambda s: None)
    mod.main()
    assert json.loads(index.read_text())['AAPL']['close'] == '171.51'
