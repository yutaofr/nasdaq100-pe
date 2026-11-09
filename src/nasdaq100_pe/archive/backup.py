"""本地备份/恢复：复制私有归档、方法与身份映射到独立本地目录；恢复后从清单重建索引。不含异地备份。"""
from __future__ import annotations

import json
import os
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path

from nasdaq100_pe.archive.store import ArchiveStore, canonical, sha256

DIRS = ["raw", "observations", "batches", "research_inputs", "snapshots", "checks", "runs", "sec_cache"]
CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


class BackupError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code


def _state_path(store: ArchiveStore) -> Path:
    return store.root / "backup_state.json"


def backup_status(store: ArchiveStore) -> dict:
    p = _state_path(store)
    if not p.exists():
        return {"configured": False, "last_success_at": None, "note": "未配置备份，无恢复保障"}
    s = json.loads(p.read_text())
    return {"configured": True, "last_success_at": s["last_success_at"], "last_dest": s["dest_name"],
            "note": "仅本地备份；无异地备份，不构成灾难恢复保障"}


def backup(store: ArchiveStore, dest: Path) -> dict:
    dest = Path(dest).resolve()
    root = store.root.resolve()
    if dest == root or root in dest.parents:
        raise BackupError("DEST_INSIDE_DATA_ROOT")
    if dest.exists():
        raise BackupError("DEST_EXISTS", "不覆盖已有备份目录")
    tmp = dest.with_name(dest.name + ".partial")
    if tmp.exists():
        shutil.rmtree(tmp)
    files: dict[str, str] = {}
    for d in DIRS:
        src = root / d
        if not src.exists():
            continue
        for p in sorted(src.rglob("*")):
            if p.is_file():
                rel = p.relative_to(root)
                (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, tmp / rel)
                files[str(rel)] = sha256(p.read_bytes())
    for p in sorted(CONFIG_DIR.glob("*.json")):
        (tmp / "config").mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, tmp / "config" / p.name)
        files[f"config/{p.name}"] = sha256(p.read_bytes())
    if (root / "index.sqlite").exists():
        shutil.copy2(root / "index.sqlite", tmp / "index.sqlite")
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "files": files}
    (tmp / "backup-manifest.json").write_bytes(canonical(manifest))
    os.rename(tmp, dest)
    _state_path(store).write_text(json.dumps({"last_success_at": manifest["created_at"], "dest_name": dest.name}))
    return {"files": len(files), "dest": str(dest)}


def restore(src: Path, target: Path) -> ArchiveStore:
    src, target = Path(src), Path(target)
    mf = json.loads((src / "backup-manifest.json").read_text())
    for rel, h in mf["files"].items():
        p = src / rel
        if not p.exists() or sha256(p.read_bytes()) != h:
            raise BackupError("HASH_MISMATCH", rel)
    if target.exists() and any(target.iterdir()):
        raise BackupError("TARGET_NOT_EMPTY")
    target.mkdir(parents=True, exist_ok=True)
    for rel in mf["files"]:
        if rel.startswith("config/"):
            continue                       # 方法配置随软件版本管理；备份中的副本仅供核对
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / rel, dst)
    store = ArchiveStore(target)
    store.rebuild_index()
    return store
