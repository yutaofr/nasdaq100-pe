from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from nasdaq100_pe.dec import BadDecimal, D, dstr
from nasdaq100_pe.identity.models import SecurityIdentity


@dataclass
class EarningsBatch:
    issuer_id: str
    cik: str
    currency: str
    split_basis_date: str | None
    ttm: object                       # TtmSelection
    class_evidence: dict = field(default_factory=dict)   # 股类 → 证据定位（同CIK多股类的口径证据）
    checked_at: str | None = None
    content_fetched_at: str | None = None
    content_sha256: str | None = None
    versions: list = field(default_factory=list)
    flags: list = field(default_factory=list)
    freshness: str = "n/a"


GAP_CATEGORY = {"MISSING_Q4": "MISSING_Q4", "MISSING_QUARTER": "MISSING_Q4", "MISSING_LABEL": "MISSING_LABEL",
                "CURRENCY_MISMATCH": "CURRENCY_ADR", "ADR_RATIO_UNKNOWN": "CURRENCY_ADR", "AMBIGUOUS_SHARE_SCOPE": "SHARE_CLASS",
                "MANUAL_REVIEW": "MISSING_TTM", "SPLIT_BASIS_MISMATCH": "MISSING_TTM"}


@dataclass
class EarningsValidation:
    rows: list[dict]
    batch: EarningsBatch

    def to_input_rows(self) -> list[dict]:
        b = self.batch
        return [{"security_id": r["security_id"], "kind": "ttm", "eps": r["eps"], "accounting_basis": "gaap", "currency": r["currency"],
                 "split_basis_date": b.split_basis_date, "latest_quarter_end": r["latest_quarter_end"],
                 "fetched_at": b.content_fetched_at, "checked_at": b.checked_at, "calculation_path": r["calculation_path"],
                 "evidence": {"cik": b.cik, "content_sha256": b.content_sha256, "quarters": r["quarters"]}}
                for r in self.rows if r["status"] == "ok"]

    def gaps(self) -> list[dict]:
        return [{"security_id": r["security_id"], "reason": GAP_CATEGORY.get(r["reason"], "MISSING_TTM")}
                for r in self.rows if r["status"] != "ok"]


def validate_earnings(batch: EarningsBatch, identities: Sequence[SecurityIdentity],
                      expected_split_basis: str | None = None) -> EarningsValidation:
    mine = [i for i in identities if i.issuer_id == batch.issuer_id]
    classes = {i.share_class for i in mine}
    t = batch.ttm
    rows = []
    for i in sorted(mine, key=lambda x: x.security_id):
        reason = None
        if t.status != "ok":
            reason = ("MISSING_Q4" if "MISSING_Q4" in t.reasons else "MISSING_QUARTER") if t.status == "missing_quarter" \
                else "MANUAL_REVIEW" if t.status == "needs_manual_review" else "MISSING_LABEL"
        elif batch.currency != "USD":
            reason = "CURRENCY_MISMATCH"
        elif i.is_adr and not i.adr_ratio:
            reason = "ADR_RATIO_UNKNOWN"
        elif len(classes) > 1 and i.share_class not in batch.class_evidence:
            reason = "AMBIGUOUS_SHARE_SCOPE"
        elif expected_split_basis is not None and batch.split_basis_date != expected_split_basis:
            reason = "SPLIT_BASIS_MISMATCH"
        rows.append({"security_id": i.security_id, "status": "invalid" if reason else "ok", "reason": reason or "",
                     "eps": dstr(t.ttm_eps) if not reason else None, "currency": batch.currency,
                     "latest_quarter_end": t.latest_quarter_end, "calculation_path": t.calculation_path,
                     "quarters": t.quarters if not reason else []})
    return EarningsValidation(rows, batch)


def validate_fy1_rows(rows: Sequence[dict]) -> tuple[list[dict], list[dict]]:
    """FY1：须有期间、财年末、mean、币种/单位及 normalized 证据；forwardPE/NTM/非GAAP标签不足以证明 FY1。"""
    ok, bad = [], []
    for r in rows:
        sid = r.get("security_id")
        fp = r.get("forecast_period")
        reason = None
        if fp is None:
            reason = "FY1_EVIDENCE_INSUFFICIENT"
        elif fp != "FY1":
            reason = "WRONG_FORECAST_PERIOD"
        elif not r.get("fiscal_year_end") or r.get("statistic") != "mean" or not r.get("currency") or not r.get("unit"):
            reason = "FY1_EVIDENCE_INSUFFICIENT"
        elif r.get("accounting_basis") not in ("gaap", "normalized"):
            reason = "UNKNOWN_ACCOUNTING_BASIS"
        elif r["accounting_basis"] == "normalized" and not r.get("normalized_evidence"):
            reason = "FY1_EVIDENCE_INSUFFICIENT"
        else:
            try:
                D(r.get("eps"))
            except BadDecimal:
                reason = "BAD_NUMBER"
        if reason:
            bad.append({"security_id": sid, "reason": reason}); continue
        flags = [] if r.get("source_updated_at") else ["FORECAST_FRESHNESS_UNVERIFIED"]
        ok.append({**r, "kind": "fy1", "quality_flags": flags})
    return ok, bad
