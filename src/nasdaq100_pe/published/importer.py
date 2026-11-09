"""引用指标（PublishedMetricObservation）导入校验。只校验，不发布，不访问网络或本地路径。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from importlib import resources
from pathlib import Path

from jsonschema import Draft202012Validator

MAX_IMPORT_BYTES = 20 * 1024 * 1024
KINDS = ("trailing_pe", "forward_pe")
_FIELDS = (
    "observation_id", "provider", "instrument", "metric_label_original", "metric_kind", "value", "unit",
    "source_as_of", "observed_at", "source_url", "evidence_sha256", "evidence_locator", "period_basis",
    "accounting_basis", "loss_treatment", "methodology_status", "entry_mode", "basis_evidence",
    "corrects_observation_id", "correction_reason",
)


def _schema() -> dict:
    here = Path(__file__).resolve()
    for parent in here.parents:
        p = parent / "schemas" / "published-observation.schema.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError("published-observation.schema.json")


_VALIDATOR = None


def _validator() -> Draft202012Validator:
    global _VALIDATOR
    if _VALIDATOR is None:
        _VALIDATOR = Draft202012Validator(_schema())
    return _VALIDATOR


@dataclass
class PublishedImportResult:
    ok: bool
    exit_code: int
    data_mode: str | None = None
    observations: list[dict] = field(default_factory=list)
    diagnostics: list[dict] = field(default_factory=list)
    completeness: dict = field(default_factory=lambda: {k: False for k in KINDS})
    publication_status: str = "not_published"

    def to_json(self) -> dict:
        return {
            "ok": self.ok, "exit_code": self.exit_code, "data_mode": self.data_mode,
            "observations": self.observations, "diagnostics": self.diagnostics,
            "completeness": self.completeness, "publication_status": self.publication_status,
        }


def _fail(diags: list[dict]) -> PublishedImportResult:
    return PublishedImportResult(ok=False, exit_code=2, diagnostics=diags)


def _path(err) -> str:
    out = ""
    for p in err.absolute_path:
        out += f"[{p}]" if isinstance(p, int) else (f".{p}" if out else str(p))
    if err.validator == "required":
        missing = re.search(r"'([^']+)'", err.message)
        if missing:
            out = f"{out}.{missing.group(1)}" if out else missing.group(1)
    return out or "$"


def validate_published(payload: bytes) -> PublishedImportResult:
    if len(payload) > MAX_IMPORT_BYTES:
        return _fail([{"path": "$", "code": "TOO_LARGE", "message": "导入文件超过20MiB"}])
    try:
        data = json.loads(payload.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError) as e:
        return _fail([{"path": "$", "code": "BAD_JSON", "message": f"无法解析为UTF-8 JSON: {type(e).__name__}"}])
    diags = [{"path": _path(e), "code": "SCHEMA", "message": e.message[:200]}
             for e in sorted(_validator().iter_errors(data), key=lambda e: list(map(str, e.absolute_path)))]
    if diags:
        return _fail(diags)

    seen: set[str] = set()
    for i, o in enumerate(data["observations"]):
        base = f"observations[{i}]"
        if o["observation_id"] in seen:
            diags.append({"path": f"{base}.observation_id", "code": "DUPLICATE_ID", "message": "重复 observation_id"})
        seen.add(o["observation_id"])
        if o["source_as_of"] is not None:
            try:
                date.fromisoformat(o["source_as_of"])
            except ValueError:
                diags.append({"path": f"{base}.source_as_of", "code": "BAD_DATE", "message": "非法日期"})
        try:
            dt = datetime.fromisoformat(o["observed_at"])
            if dt.tzinfo is None:
                raise ValueError
        except ValueError:
            diags.append({"path": f"{base}.observed_at", "code": "BAD_TIMESTAMP", "message": "须为带时区的ISO 8601时间"})
        if (o["period_basis"] == "fy1" or o["accounting_basis"] == "normalized") and not o.get("basis_evidence"):
            fld = "period_basis" if o["period_basis"] == "fy1" else "accounting_basis"
            diags.append({"path": f"{base}.{fld}", "code": "BASIS_UNSUPPORTED",
                          "message": "声明FY1/normalized须提供 basis_evidence；不得依据指标名称推断"})
        if ("corrects_observation_id" in o) != ("correction_reason" in o):
            diags.append({"path": f"{base}.correction_reason", "code": "CORRECTION_INCOMPLETE",
                          "message": "更正须同时给出 corrects_observation_id 与 correction_reason"})
    if diags:
        return _fail(diags)

    obs = [{k: o[k] for k in _FIELDS if k in o} for o in data["observations"]]
    for o in obs:   # 归档统一 UTC（ADD §4.1），避免混合偏移导致字符串排序错误
        o["observed_at"] = datetime.fromisoformat(o["observed_at"]).astimezone(timezone.utc).isoformat()
    kinds = {o["metric_kind"] for o in obs}
    return PublishedImportResult(
        ok=True, exit_code=0, data_mode=data["data_mode"], observations=obs,
        completeness={k: k in kinds for k in KINDS},
    )


def _reject_constant(name: str):
    raise ValueError(f"non-finite constant {name}")
