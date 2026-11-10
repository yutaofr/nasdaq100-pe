from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import InvalidOperation
from typing import Sequence

from nasdaq100_pe.dec import BadDecimal, D, dstr
from nasdaq100_pe.identity.models import SecurityIdentity
from nasdaq100_pe.normalize.net_income import ComponentError, compute_from_components
from nasdaq100_pe.normalize.quarters import select_ttm


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
                 "evidence": {"cik": b.cik, "content_sha256": b.content_sha256, "quarters": r["quarters"],
                              "locator": "us-gaap/EarningsPerShareDiluted/USD/shares"},
                 "quarters": r["quarters"], "class_evidence": b.class_evidence}
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


def validate_ttm_input_row(row: dict, identity: SecurityIdentity, issuer_identities: Sequence[SecurityIdentity],
                           price_split_basis: str | None, as_of: date, observed_at: datetime) -> str | None:
    """Re-select the reported four quarters before an imported TTM EPS reaches the engine."""
    if row.get("accounting_basis") != "gaap":
        return "WRONG_ACCOUNTING_BASIS"
    quarters = row.get("quarters") or (row.get("evidence") or {}).get("quarters")
    if not isinstance(quarters, list) or len(quarters) != 4:
        return "MISSING_QUARTER"
    needed = ("start", "end", "val", "filed", "accn", "form")
    try:
        if any(not isinstance(q, dict) or any(q.get(k) is None or q.get(k) == "" for k in needed) for q in quarters):
            return "TTM_EVIDENCE_INSUFFICIENT"
        if any(date.fromisoformat(q["end"]) > as_of for q in quarters):
            return "SOURCE_AFTER_PRICE_DATE"
        if any(date.fromisoformat(q["filed"]) < date.fromisoformat(q["end"]) for q in quarters):
            return "TTM_EVIDENCE_INSUFFICIENT"
        if any(date.fromisoformat(q["filed"]) > observed_at.date() for q in quarters):
            return "SOURCE_AFTER_CUTOFF"
        for q in quarters:
            D(str(q["val"]))  # SEC companyfacts uses JSON numbers; normalized input EPS stays a decimal string.
        if any(q.get("manual") and not (q.get("evidence_sha256") and q.get("locator")) for q in quarters):
            return "TTM_EVIDENCE_INSUFFICIENT"
        # The existing selector checks quarter lengths, continuity, conflicts and derives EPS.
        facts = {"facts": {"us-gaap": {"EarningsPerShareDiluted": {"units": {"USD/shares": quarters}}}}}
        ttm = select_ttm(facts)
        if ttm.status != "ok":
            return "MISSING_QUARTER" if ttm.status == "missing_quarter" else "TTM_EVIDENCE_INSUFFICIENT"
        if ttm.latest_quarter_end != row.get("latest_quarter_end") or D(row.get("eps")) != ttm.ttm_eps:
            return "TTM_EPS_MISMATCH"
        evidence = row.get("evidence") or {}
        batch = EarningsBatch(identity.issuer_id, evidence.get("cik", ""), row.get("currency", ""),
                              row.get("split_basis_date"), ttm, row.get("class_evidence") or {})
        verdict = next(v for v in validate_earnings(batch, issuer_identities, price_split_basis).rows
                       if v["security_id"] == identity.security_id)
        return verdict["reason"] or None
    except (ValueError, TypeError, KeyError, AttributeError, BadDecimal, InvalidOperation):
        return "TTM_EVIDENCE_INSUFFICIENT"


def validate_net_income_row(row: dict, identity: SecurityIdentity, issuer_identities: Sequence[SecurityIdentity],
                            price_split_basis: str | None, as_of: date, observed_at: datetime) -> str | None:
    """方法版本2：由证据分量复算 TTM 净利润与股数，再做与 EPS 路径相同的时点、币种、股类检查。"""
    if row.get("accounting_basis") != "gaap":
        return "WRONG_ACCOUNTING_BASIS"
    comps = (row.get("evidence") or {}).get("components")
    try:
        profit, shares, latest = compute_from_components(comps)
        parts = [comps[k] for k in ("fy", "ytd_current", "ytd_prior", "shares", "cover_shares") if comps.get(k)]
        chk = comps.get("eps_check") or {}
        parts += [chk[k] for k in ("net_income", "eps") if k in chk]
        if any(date.fromisoformat(p["end"]) > as_of for p in parts if p is not comps.get("cover_shares")):
            return "SOURCE_AFTER_PRICE_DATE"
        if any(date.fromisoformat(p["filed"]) > observed_at.date() for p in parts):
            return "SOURCE_AFTER_CUTOFF"
        if latest != row.get("latest_quarter_end") or D(row.get("profit")) != profit or D(row.get("shares")) != shares:
            return "TTM_PROFIT_MISMATCH"
    except ComponentError as e:
        return e.code
    except (ValueError, TypeError, KeyError, AttributeError, BadDecimal, InvalidOperation):
        return "TTM_EVIDENCE_INSUFFICIENT"
    if row.get("currency") != "USD":
        return "CURRENCY_MISMATCH"
    if identity.is_adr and not identity.adr_ratio:
        return "ADR_RATIO_UNKNOWN"
    if len({i.share_class for i in issuer_identities}) > 1 and identity.share_class not in (row.get("class_evidence") or {}):
        return "AMBIGUOUS_SHARE_SCOPE"
    if row.get("split_basis_date") != price_split_basis:
        return "SPLIT_BASIS_MISMATCH"
    return None


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
        elif not r.get("fiscal_year_end") or r.get("statistic") != "mean" or not r.get("currency") or r.get("unit") != "per_share":
            reason = "FY1_EVIDENCE_INSUFFICIENT"
        elif r.get("accounting_basis") != "normalized":
            reason = "WRONG_ACCOUNTING_BASIS" if r.get("accounting_basis") == "gaap" else "UNKNOWN_ACCOUNTING_BASIS"
        elif not r.get("normalized_evidence"):
            reason = "FY1_EVIDENCE_INSUFFICIENT"
        else:
            try:
                date.fromisoformat(r["fiscal_year_end"])
                D(r.get("eps"))
            except (BadDecimal, ValueError, TypeError):
                reason = "BAD_NUMBER"
        if reason:
            bad.append({"security_id": sid, "reason": reason}); continue
        flags = [] if r.get("source_updated_at") else ["FORECAST_FRESHNESS_UNVERIFIED"]
        ok.append({**r, "kind": "fy1", "quality_flags": flags})
    return ok, bad
