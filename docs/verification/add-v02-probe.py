"""ADD v0.2 architecture probe. Synthetic releases only, with no production data."""
import csv
import fcntl
import hashlib
from http.client import HTTPConnection
import io
import json
import os
import plistlib
import signal
import subprocess
import sys
import time
import unittest
import uuid
from datetime import date, datetime, time as wall_time, timedelta
from decimal import Decimal, localcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socket import socket
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
DAY = date(2026, 11, 6)
SCRIPT = Path(__file__).resolve()
BACKOFF = (15, 60, 180, 360)


def atomic_json(path, value):
    scratch = path.with_suffix(".tmp")
    scratch.write_text(json.dumps(value), encoding="utf-8")
    scratch.replace(path)


def serve(root):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            port = self.server.server_port
            hosts = {host for name in ("127.0.0.1", "localhost")
                     for host in (name, f"{name}:{port}")}
            host = self.headers.get_all("Host", [])
            if len(host) != 1 or host[0].lower() not in hosts:
                self.send_error(403)
                return
            if self.path == "/health":
                body = json.dumps({"pid": os.getpid(), "ready": True}).encode()
            elif self.path in ("/", "/latest.json"):
                pointer = root / "latest.json"
                body = (pointer.read_bytes() if pointer.is_file()
                        else b'{"state":"empty","deployment_mode":"local_private"}')
            else:
                parts = self.path.split("/")
                if (len(parts) != 4 or parts[1] != "releases"
                        or not parts[2].isascii() or not parts[2].isalnum()
                        or parts[3] not in ("snapshot.json", "details.csv")):
                    self.send_error(404)
                    return
                file = root.joinpath(*parts[1:])
                if not file.is_file() or not file.resolve().is_relative_to((root / "releases").resolve()):
                    self.send_error(404)
                    return
                body = file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/csv" if self.path.endswith(".csv")
                             else "application/json")
            self.end_headers()
            self.wfile.write(body)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        atomic_json(root.parent / "address.json", {"port": server.server_port})
        server.serve_forever()


def http(port, path, host=None):
    conn = HTTPConnection("127.0.0.1", port, timeout=1)
    try:
        conn.request("GET", path, headers={"Host": host or f"127.0.0.1:{port}"})
        response = conn.getresponse()
        return response.status, response.read(), dict(response.getheaders())
    finally:
        conn.close()


def now_ready(address, different_pid=None, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            port = json.loads(address.read_text())["port"]
            code, body, _ = http(port, "/health")
            health = json.loads(body)
            if code == 200 and health["pid"] != different_pid:
                return port, health["pid"]
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(0.1)
    raise AssertionError("HTTP service did not become ready")


def archive(root, release_id, day, revision):
    package = root / "releases" / release_id
    package.mkdir(parents=True)
    payload = {"release_id": release_id, "day": day.isoformat(), "revision": revision,
               "deployment_mode": "local_private", "data_mode": "synthetic",
               "public_display": "unverified", "public_download": "denied",
               "public_derived_metrics": "unverified", "eps": "-1.25"}
    atomic_json(package / "snapshot.json", payload)
    with (package / "details.csv").open("w", newline="", encoding="utf-8") as file:
        csv.writer(file).writerows((("symbol", "eps"), ("DEMO", "-1.25")))
    return {**payload, "hash": hashlib.sha256((package / "snapshot.json").read_bytes()).hexdigest()}


def promote(root, port, candidate, recommended, *, rollback=False):
    with (root.parent / "publish.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        pointer = root / "latest.json"
        active = json.loads(pointer.read_text()) if pointer.exists() else None
        order = lambda item: (item["day"], item["revision"])
        if not rollback and (recommended[candidate["day"]] != candidate["release_id"]
                             or (active and order(candidate) < order(active))):
            return "superseded_no_op"
        try:
            status, body, _ = http(port, f'/releases/{candidate["release_id"]}/snapshot.json')
        except OSError:
            return "retry"
        if status != 200 or hashlib.sha256(body).hexdigest() != candidate["hash"]:
            return "retry"
        atomic_json(pointer, candidate)
        return "published"


def acquisition_state(target, acquired_at, close=wall_time(16)):
    if acquired_at < datetime.combine(target, close, NY):
        return "before_close"
    cutoff = datetime.combine(target + timedelta(days=1), wall_time(12), NY)
    return "missed_window" if acquired_at > cutoff else "in_window"


def fy1(record, target):
    if record.get("period") != "FY1" or record.get("basis") != "normalized":
        return "ineligible"
    if record.get("mean") is None or not record.get("fiscal_year_end"):
        return "ineligible"
    updated = record.get("updated")
    if updated is None:
        return "FORECAST_FRESHNESS_UNVERIFIED"
    return "ineligible" if (target - updated).days > 30 else "eligible"


def quarter_sum(quarters):
    return sum(quarters) if len(quarters) == 4 and None not in quarters else None


class ArchitectureCases(unittest.TestCase):
    def setUp(self):
        (self.root / "latest.json").unlink(missing_ok=True)

    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory(prefix="ndx-add-v02-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.workspace = Path(cls.temp.name)
        cls.root = cls.workspace / "publish"
        cls.root.mkdir()
        cls.secret = cls.workspace / "raw" / "secret.json"
        cls.secret.parent.mkdir()
        cls.secret.write_text('{"test_marker":"synthetic-private"}')
        cls.address = cls.workspace / "address.json"
        cls.label = "com.codex.ndx-add-validation." + uuid.uuid4().hex
        cls.domain = f"gui/{os.getuid()}"
        cls.service = cls.domain + "/" + cls.label
        cls.plist = cls.workspace / "service.plist"
        with cls.plist.open("wb") as file:
            plistlib.dump({"Label": cls.label,
                           "ProgramArguments": [sys.executable, str(SCRIPT), "--serve", str(cls.root)],
                           "RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 1}, file)
        subprocess.run(["plutil", "-lint", str(cls.plist)], check=True)
        cls.addClassCleanup(cls.remove_agent)
        cls.start_agent()

    @classmethod
    def start_agent(cls):
        subprocess.run(["launchctl", "bootstrap", cls.domain, str(cls.plist)], check=True)
        cls.port, cls.pid = now_ready(cls.address)

    @classmethod
    def remove_agent(cls):
        subprocess.run(["launchctl", "bootout", cls.service], capture_output=True)
        status = subprocess.run(["launchctl", "print", cls.service], capture_output=True)
        if status.returncode == 0:
            raise AssertionError("temporary launchd Agent still loaded")

    def test_01_local_unknown_public_policy(self):
        item = archive(self.root, "first", DAY, 1)
        self.assertEqual(promote(self.root, self.port, item, {item["day"]: "first"}), "published")
        self.assertEqual(json.loads(http(self.port, "/latest.json")[1]), item)
        self.assertEqual(http(self.port, "/releases/first/snapshot.json")[0], 200)
        parsed = list(csv.DictReader(io.StringIO(http(self.port, "/releases/first/details.csv")[1].decode())))
        self.assertEqual(parsed, [{"symbol": "DEMO", "eps": "-1.25"}])
        self.assertFalse((self.workspace / "public").exists())

    def test_02_loopback_host_and_traversal(self):
        listeners = subprocess.check_output(
            ["/usr/sbin/lsof", "-nP", "-a", "-p", str(self.pid), "-iTCP", "-sTCP:LISTEN"], text=True)
        sockets = [line for line in listeners.splitlines() if "(LISTEN)" in line]
        self.assertEqual(len(sockets), 1)
        self.assertIn(f"127.0.0.1:{self.port} (LISTEN)", sockets[0])
        self.assertEqual(http(self.port, "/health", f"localhost:{self.port}")[0], 200)
        self.assertEqual(http(self.port, "/health", "attacker.example")[0], 403)
        self.assertNotIn("Access-Control-Allow-Origin", http(self.port, "/health")[2])
        release = self.root / "releases/escape"
        release.mkdir(parents=True)
        (release / "snapshot.json").symlink_to(self.secret)
        for path in ("/raw/secret.json", "/releases/", "/releases/../raw/secret.json",
                     "/releases/%2e%2e/raw/secret.json", "/releases/escape/snapshot.json",
                     "/releases/first/%2e%2e%2fsecret.json"):
            with self.subTest(path=path):
                code, body, _ = http(self.port, path)
                self.assertEqual(code, 404)
                self.assertNotIn(b"synthetic-private", body)

    def test_03_lagged_weights(self):
        item = archive(self.root, "previousday", DAY - timedelta(days=1), 1)
        self.assertEqual(promote(self.root, self.port, item, {item["day"]: "previousday"}), "published")
        last_good = http(self.port, "/latest.json")[1]
        for weight_date in (DAY - timedelta(days=1), DAY - timedelta(days=2)):
            diagnostics = {"weight_date": weight_date, "eligible": weight_date == DAY,
                           "coverage_ratio": None, "estimate_enabled": False}
            self.assertFalse(diagnostics["eligible"])
            self.assertIsNone(diagnostics["coverage_ratio"])
            self.assertFalse(diagnostics["estimate_enabled"])
        self.assertEqual(http(self.port, "/latest.json")[1], last_good)

    def test_04_unknown_non_equity_weight(self):
        equities = [Decimal("70"), Decimal("29.5")]
        exclusions = [Decimal("0.49"), None]
        with localcontext(prec=34):
            weights = [weight / sum(equities) for weight in equities]
        known_excluded = sum(weight for weight in exclusions if weight is not None)
        total_excluded = None if None in exclusions else known_excluded
        self.assertEqual(sum(weights), Decimal(1))
        self.assertEqual(known_excluded, Decimal("0.49"))
        self.assertIsNone(total_excluded)
        self.assertEqual(exclusions.count(None), 1)

    def test_05_apple_quarters_vs_year(self):
        quarters = [Decimal(x) for x in ("2.84", "2.01", "2.02", "2.10")]
        annual = Decimal("8.98")
        result = {"calculation_path": "reported_quarter_eps_sum", "value": quarter_sum(quarters),
                  "reported_fy": annual}
        self.assertEqual(result["value"], Decimal("8.97"))
        self.assertEqual(result["reported_fy"], Decimal("8.98"))
        self.assertNotEqual(annual - sum(quarters[:3]), quarters[3])
        self.assertIsNone(quarter_sum([*quarters[:3], None]))

    def test_06_negative_share_class_and_currency(self):
        self.assertEqual(sum(map(Decimal, ("-2.11", "-3.40", "-1.97", "0.38"))),
                         Decimal("-7.10"))
        securities = {"GOOG": ("0001652044", "Class C", True),
                      "GOOGL": ("0001652044", "Class A", False)}
        self.assertEqual(len({entry[0] for entry in securities.values()}), 1)
        self.assertEqual({k for k, v in securities.items() if not v[2]}, {"GOOGL"})
        currencies, conversion_evidence = ("EUR", "USD"), None
        self.assertFalse(currencies[0] == currencies[1] or bool(conversion_evidence))

    def test_07_fy1_independent_gate(self):
        record = {"period": "FY1", "basis": "normalized", "mean": "0",
                  "fiscal_year_end": "2027-12-31", "updated": DAY - timedelta(days=30)}
        self.assertEqual(fy1({"forwardPE": "22"}, DAY), "ineligible")
        self.assertEqual(fy1({**record, "basis": None}, DAY), "ineligible")
        self.assertEqual(fy1({**record, "period": "NTM"}, DAY), "ineligible")
        self.assertEqual(fy1(record, DAY), "eligible")
        self.assertEqual(fy1({**record, "updated": None}, DAY), "FORECAST_FRESHNESS_UNVERIFIED")
        self.assertEqual(fy1({**record, "updated": DAY - timedelta(days=31)}, DAY), "ineligible")
        self.assertEqual(Decimal("-1.25") / Decimal("10"), Decimal("-0.125"))

    def test_08_late_old_revision_and_explicit_rollback(self):
        older = archive(self.root, "older", DAY, 2)
        newer = archive(self.root, "newer", DAY, 3)
        rec = {newer["day"]: "newer"}
        self.assertEqual(promote(self.root, self.port, newer, rec), "published")
        self.assertEqual(promote(self.root, self.port, older, rec), "superseded_no_op")
        self.assertEqual(json.loads(http(self.port, "/latest.json")[1]), newer)
        self.assertEqual(promote(self.root, self.port, older, rec, rollback=True), "published")
        self.assertEqual(json.loads(http(self.port, "/latest.json")[1]), older)

    def test_09_empty_crash_and_agent_reload(self):
        old_pid = self.pid
        self.assertEqual(json.loads(http(self.port, "/")[1])["state"], "empty")
        started = time.monotonic()
        os.kill(old_pid, signal.SIGKILL)
        cls = type(self)
        cls.port, cls.pid = now_ready(self.address, old_pid)
        print(f"launchd crash recovery: PID {old_pid} -> {cls.pid} in {time.monotonic()-started:.2f}s",
              flush=True)
        self.assertEqual(json.loads(http(self.port, "/")[1])["state"], "empty")
        cls.remove_agent()
        cls.start_agent()
        self.assertEqual(json.loads(http(self.port, "/")[1])["state"], "empty")
        print("launchd bootout/bootstrap: empty state readable", flush=True)

    def test_10_publish_retry_reuses_archived_input(self):
        saved = archive(self.root, "saved", DAY, 4)
        pending = archive(self.root, "pending", DAY, 5)
        rec = {saved["day"]: "saved"}
        self.assertEqual(promote(self.root, self.port, saved, rec), "published")
        rec[saved["day"]] = "pending"
        archived_file = self.root / "releases/pending/snapshot.json"
        archived_bytes = archived_file.read_bytes()
        original_mtime = archived_file.stat().st_mtime_ns
        next_attempt = datetime.combine(DAY, wall_time(23), NY)
        attempts = 0

        def publish_tick(now, port, candidate):
            nonlocal next_attempt, attempts
            if now < next_attempt:
                return "not_due"
            result = promote(self.root, port, candidate, rec)
            if result == "retry":
                next_attempt = now + timedelta(minutes=BACKOFF[min(attempts, len(BACKOFF) - 1)])
                attempts += 1
            return result

        # Bind without listening so this port remains unavailable during the probe.
        with socket() as unavailable:
            unavailable.bind(("127.0.0.1", 0))
            self.assertEqual(publish_tick(next_attempt, unavailable.getsockname()[1], pending), "retry")
        self.assertEqual(next_attempt.time(), wall_time(23, 15))
        self.assertEqual(publish_tick(next_attempt - timedelta(seconds=1), self.port, pending), "not_due")
        self.assertEqual(publish_tick(next_attempt, self.port, {**pending, "hash": "0" * 64}), "retry")
        self.assertEqual(next_attempt.time(), wall_time(0, 15))
        self.assertEqual(json.loads(http(self.port, "/latest.json")[1]), saved)
        self.assertEqual(publish_tick(next_attempt, self.port, pending), "published")
        self.assertEqual(archived_file.read_bytes(), archived_bytes)
        self.assertEqual(archived_file.stat().st_mtime_ns, original_mtime)

    def test_11_late_import(self):
        cutoff = datetime.combine(DAY + timedelta(days=1), wall_time(12), NY)
        self.assertEqual(acquisition_state(DAY, cutoff), "in_window")
        self.assertEqual(acquisition_state(DAY, cutoff + timedelta(seconds=1)), "missed_window")
        sunday = datetime(2026, 11, 8, 22, 35, tzinfo=ZoneInfo("Europe/Paris"))
        self.assertEqual(acquisition_state(DAY, sunday), "missed_window")
        self.assertEqual(acquisition_state(date(2026, 11, 9), sunday), "before_close")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--serve":
        serve(Path(sys.argv[2]))
    else:
        unittest.main(verbosity=2)
