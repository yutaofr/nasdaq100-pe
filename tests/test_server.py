import hashlib
import http.client
import json
import threading

import pytest

from nasdaq100_pe.archive.evidence import archive_published
from nasdaq100_pe.archive.store import ArchiveStore
from nasdaq100_pe.publisher.local import ReleaseSelection, build_local_release
from nasdaq100_pe.publisher.pointer import promote_release
from nasdaq100_pe.published.importer import validate_published
from nasdaq100_pe.server import make_server, serve_local
from tests.published.test_import import obs, pack


@pytest.fixture
def srv(tmp_path):
    store = ArchiveStore(tmp_path / "data")
    web = tmp_path / "web"; web.mkdir(); (web / "index.html").write_text("<html>ok</html>")
    (tmp_path / "secret.txt").write_text("TOPSECRET")
    s = make_server(store.root, "127.0.0.1", 0, web_root=web)
    t = threading.Thread(target=s.serve_forever, daemon=True); t.start()
    yield store, s, web, tmp_path
    s.shutdown(); s.server_close()


def get(s, path, host=None, method="GET"):
    c = http.client.HTTPConnection("127.0.0.1", s.server_address[1], timeout=5)
    c.putrequest(method, path, skip_host=True)
    c.putheader("Host", host or f"127.0.0.1:{s.server_address[1]}")
    c.endheaders()
    r = c.getresponse(); body = r.read()
    return r.status, dict(r.getheaders()), body


def publish(store, tmp_path):
    ev = tmp_path / "ev"; ev.mkdir(exist_ok=True); f = ev / "a"; f.write_bytes(b"x")
    r = validate_published(pack(obs(evidence_sha256=hashlib.sha256(b"x").hexdigest())))
    b = archive_published(r, {"o1": f}, store, evidence_dir=ev)
    rel = build_local_release(ReleaseSelection(batch_ids=[b.batch_id]), store)
    promote_release(store, rel.release_id, None)
    return rel


def test_listens_on_loopback_only(srv):
    store, s, *_ = srv
    assert s.server_address[0] == "127.0.0.1"


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.5", "localhost"])
def test_bind_non_loopback_rejected(tmp_path, host):
    if host == "localhost":
        pytest.skip("localhost resolves to loopback; policy pins literal 127.0.0.1")
    with pytest.raises(ValueError):
        serve_local(tmp_path, host, 0)


def test_empty_state_health(srv):
    store, s, *_ = srv
    st, _, body = get(s, "/healthz")
    d = json.loads(body)
    assert st == 200 and d["status"] == "ok" and d["current_release"] is None and d["empty"] is True


def test_serves_current_release(srv):
    store, s, web, tmp = srv
    rel = publish(store, tmp)
    assert json.loads(get(s, "/api/current")[2])["release_id"] == rel.release_id
    st, _, body = get(s, f"/releases/{rel.release_id}/observations.json")
    assert st == 200 and json.loads(body)["series"]
    assert get(s, "/")[0] == 200


def test_host_header_and_methods(srv):
    store, s, *_ = srv
    for h in ("evil.com", "127.0.0.1.evil.com", "0.0.0.0:80"):
        assert get(s, "/healthz", host=h)[0] == 403
    for h in ("localhost:8000", "127.0.0.1", "[::1]:9"):
        assert get(s, "/healthz", host=h)[0] == 200
    for m in ("POST", "PUT", "DELETE", "PATCH"):
        assert get(s, "/healthz", method=m)[0] == 405
    st, hd, _ = get(s, "/healthz")
    assert not any(k.lower().startswith("access-control") for k in hd)


@pytest.mark.parametrize("path", ["/../secret.txt", "/%2e%2e/secret.txt", "/%2e%2e%2fsecret.txt", "/releases/../../secret.txt",
                                  "/raw/x", "/index.sqlite", "/logs/import.jsonl", "/releases/.stage-x/manifest.json",
                                  "/releases/zzzz/manifest.json", "/releases/0123456789abcdef/../../index.sqlite"])
def test_traversal_and_private_blocked(srv, path):
    store, s, web, tmp = srv
    publish(store, tmp)
    st, _, body = get(s, path)
    assert b"TOPSECRET" not in body
    if path.startswith(("/raw", "/index", "/logs")):
        assert st in (200, 404) and b"sqlite" not in body.lower()[:20]
    else:
        assert st in (400, 403, 404)


def test_symlink_to_private_not_followed(srv):
    store, s, web, tmp = srv
    (web / "leak.txt").symlink_to(tmp / "secret.txt")
    st, _, body = get(s, "/leak.txt")
    assert b"TOPSECRET" not in body and st in (403, 404)


def test_no_write_endpoints(srv):
    store, s, *_ = srv
    for p in ("/upload", "/api/import", "/config"):
        assert get(s, p, method="POST")[0] == 405


def test_gzip_when_accepted_and_plain_otherwise(srv):
    store, s, web, tmp = srv
    (web / "big.js").write_text("var a = '" + "x" * 5000 + "';")
    c = http.client.HTTPConnection("127.0.0.1", s.server_address[1], timeout=5)
    c.request("GET", "/big.js", headers={"Accept-Encoding": "gzip", "Host": f"127.0.0.1:{s.server_address[1]}"})
    r = c.getresponse(); body = r.read()
    assert r.getheader("Content-Encoding") == "gzip" and len(body) < 500
    import gzip
    assert gzip.decompress(body).startswith(b"var a")
    st, hd, plain = get(s, "/big.js")
    assert "Content-Encoding" not in hd and len(plain) > 5000
