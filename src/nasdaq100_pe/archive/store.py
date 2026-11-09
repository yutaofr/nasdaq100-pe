from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


class ArchiveError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code


class CrashInjected(Exception):
    """测试用：模拟进程在归档中途崩溃。"""


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


LOG_FIELDS = {"ts", "event", "batch_id", "observation_id", "sha256", "code"}


class ArchiveStore:
    """不可变文件为审计依据；SQLite 索引可由 manifest 重建。"""

    def __init__(self, root: Path | str):
        self.root = Path(root)
        for d in ("raw", "observations", "batches", "staging", "logs"):
            (self.root / d).mkdir(parents=True, exist_ok=True)
        self.crash_hook: Callable[[str], None] | None = None
        self._init_index()

    # ---- 基础 ----
    def _crash(self, stage: str):
        if self.crash_hook:
            self.crash_hook(stage)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.root / "index.sqlite")

    def _init_index(self):
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS observations(
                observation_id TEXT PRIMARY KEY, series_key TEXT, observed_at TEXT,
                record_sha256 TEXT, batch_id TEXT)""")

    def write_immutable(self, dest: Path, data: bytes):
        tmp = self.root / "staging" / f"{uuid.uuid4().hex}.tmp"
        tmp.write_bytes(data)
        os.chmod(tmp, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        os.replace(tmp, dest)

    def log(self, event: str, **fields):
        rec = {"ts": datetime.now(timezone.utc).isoformat(), "event": event}
        rec.update({k: v for k, v in fields.items() if k in LOG_FIELDS})
        with open(self.root / "logs" / "import.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ---- 清单（权威）----
    def manifests(self) -> list[dict]:
        out = []
        for p in sorted((self.root / "batches").glob("*.json")):
            out.append(json.loads(p.read_text(encoding="utf-8")))
        return out

    def manifest_digest(self) -> str:
        h = hashlib.sha256()
        for p in sorted((self.root / "batches").glob("*.json")):
            h.update(p.name.encode()); h.update(p.read_bytes())
        return h.hexdigest()

    def record_path(self, observation_id: str) -> Path:
        return self.root / "observations" / f"{sha256(observation_id.encode())}.json"

    def known_records(self) -> dict[str, dict]:
        """仅以 manifest 引用的观察为已归档；暂存/孤立文件不算。"""
        recs: dict[str, dict] = {}
        for m in self.manifests():
            for e in m["observations"]:
                p = self.record_path(e["observation_id"])
                if p.exists() and sha256(p.read_bytes()) == e["record_sha256"]:
                    recs[e["observation_id"]] = json.loads(p.read_text(encoding="utf-8"))
        return recs

    def all_observations(self) -> list[dict]:
        return sorted(self.known_records().values(), key=lambda o: (o["observed_at"], o["observation_id"]))

    # ---- 索引 ----
    def index_observation(self, c: sqlite3.Connection, rec: dict, batch_id: str):
        from nasdaq100_pe.published.history import series_key
        c.execute("INSERT OR REPLACE INTO observations VALUES(?,?,?,?,?)",
                  (rec["observation_id"], series_key(rec), rec["observed_at"],
                   sha256(self.record_path(rec["observation_id"]).read_bytes()), batch_id))

    def rebuild_index(self) -> int:
        n = 0
        with self._conn() as c:
            c.execute("DELETE FROM observations")
            for m in self.manifests():
                for e in m["observations"]:
                    p = self.record_path(e["observation_id"])
                    if not p.exists() or sha256(p.read_bytes()) != e["record_sha256"]:
                        raise ArchiveError("CORRUPT", f"observation file missing/changed: {e['observation_id']}")
                    self.index_observation(c, json.loads(p.read_text(encoding="utf-8")), m["batch_id"])
                    n += 1
        return n

    def index_count(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM observations").fetchone()[0]

    def index_snapshot(self) -> list[tuple]:
        with self._conn() as c:
            return c.execute("SELECT observation_id, series_key, observed_at, record_sha256 FROM observations "
                             "ORDER BY observation_id").fetchall()

    # ---- 来源检查事件（T05 写入；发布包读取）----
    def list_checks(self) -> list[dict]:
        d = self.root / "checks"
        if not d.exists():
            return []
        return sorted((json.loads(p.read_text(encoding="utf-8")) for p in d.glob("*.json")),
                      key=lambda c: (c["series_key"], c["checked_at"], c["check_id"]))
