"""研究资格与时钟政策：把 InputValidation 变成可交给内核的 ValidatedInputs。"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from nasdaq100_pe.calendar import CalendarUnknown, TradingCalendar, strict_cutoff
from nasdaq100_pe.dec import D, dstr
from nasdaq100_pe.engine.core import EarningsInput, SecurityInputs, ValidatedInputs
from nasdaq100_pe.method import MethodSpec
from nasdaq100_pe.validate.input import InputValidation


class EligibilityError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code


@dataclass(frozen=True)
class AnalysisContext:
    W: date                      # 篮子（权重）日
    D: date                      # 价格日
    T: datetime                  # 观察时点（带时区）
    analysis_profile: str        # strict | research
    basket_policy: str           # current | fixed
    coverage_policy: str         # full | subset
    freshness_policy: str        # daily | weekly
    method_version: str
    data_mode: str               # real | synthetic
    policy: MethodSpec = MethodSpec()

    def __post_init__(self):
        if self.T.tzinfo is None:
            raise EligibilityError("NAIVE_TIME", "T 须带时区")
        if self.analysis_profile not in ("strict", "research") or self.basket_policy not in ("current", "fixed") \
                or self.coverage_policy not in ("full", "subset") or self.freshness_policy not in ("daily", "weekly"):
            raise EligibilityError("INVALID_COMBINATION", "未知模式取值")
        if self.analysis_profile == "strict" and (self.basket_policy, self.coverage_policy, self.freshness_policy) != ("current", "full", "daily"):
            raise EligibilityError("INVALID_COMBINATION", "strict 固定为 current/full/daily")

    def as_dict(self) -> dict:
        return {"W": self.W.isoformat(), "D": self.D.isoformat(), "T": self.T.isoformat(), "analysis_profile": self.analysis_profile,
                "basket_policy": self.basket_policy, "coverage_policy": self.coverage_policy,
                "freshness_policy": self.freshness_policy, "method_version": self.method_version, "data_mode": self.data_mode}


def series_key(c: AnalysisContext) -> str:
    return "|".join([c.method_version, c.analysis_profile, c.basket_policy, c.coverage_policy, c.freshness_policy, c.data_mode])


def input_identity(c: AnalysisContext, inputs: InputValidation) -> str:
    sec_set = sorted(s.security_id for s in inputs.universe.securities)
    body = {"ctx": c.as_dict(), "set": hashlib.sha256(json.dumps(sec_set).encode()).hexdigest(),
            "weights": {k: dstr(v) for k, v in sorted(inputs.basket.weights.final.items())} if inputs.basket.weights else {},
            "prices": sorted(inputs.prices, key=lambda r: json.dumps(r, sort_keys=True)),
            "earnings": sorted(inputs.earnings, key=lambda r: json.dumps(r, sort_keys=True))}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def assess_eligibility(inputs: InputValidation, context: AnalysisContext, calendar: TradingCalendar) -> ValidatedInputs:
    if not inputs.ok or inputs.basket is None or inputs.basket.weights is None:
        raise EligibilityError("INPUT_INVALID", "输入结构未通过，不能评估资格")
    c, pol = context, context.policy
    if c.analysis_profile == "strict" and c.T > strict_cutoff(c.D):
        raise EligibilityError("STRICT_CUTOFF_EXCEEDED", "strict 截止为 D 后一个自然日纽约12:00")
    try:
        if c.basket_policy == "current":
            if c.W != c.D:
                raise EligibilityError("WEIGHT_DATE_MISMATCH", "current 篮子要求权重日等于价格日")
        else:
            if c.W > c.D:
                raise EligibilityError("WEIGHT_DATE_MISMATCH", "W 不得晚于 D")
            if calendar.trading_days_between(c.W, c.D) > pol.fixed_basket_max_lag_trading_days:
                raise EligibilityError("FIXED_BASKET_TOO_OLD", "固定篮子最多滞后5个交易日")
    except CalendarUnknown as e:
        raise EligibilityError("CALENDAR_UNKNOWN", str(e))
    if c.coverage_policy == "full" and not inputs.basket.qualified:
        raise EligibilityError("UNKNOWN_UNIVERSE", "full 覆盖要求完整名单与可信权重")

    diags = list(inputs.diagnostics)
    used_fetch: list[datetime] = []

    def fresh(row, sid, kind=None) -> bool:
        f = _dt(row["fetched_at"])
        code = None
        if f > c.T:
            code = "SOURCE_AFTER_CUTOFF"
        elif c.freshness_policy == "weekly" and c.T - f > timedelta(days=pol.weekly_max_age_days):
            code = "STALE_FETCH"
        elif c.freshness_policy == "daily" and c.T - f >= timedelta(hours=pol.daily_freshness_hours):
            code = "STALE_FETCH"
        if code:
            diags.append({"code": code, "security_id": sid, "kind": kind})
            return False
        used_fetch.append(f)
        return True

    prices: dict[str, dict] = {}
    for p in inputs.prices:
        sid = p["security_id"]
        if p.get("date") != c.D.isoformat():
            diags.append({"code": "PRICE_DATE_MISMATCH", "security_id": sid}); continue
        if p.get("price_type") != "regular_close":
            diags.append({"code": "PRICE_TYPE_INVALID", "security_id": sid}); continue
        if sid in prices:
            diags.append({"code": "PRICE_DUPLICATE", "security_id": sid}); prices.pop(sid); continue
        if fresh(p, sid, "price"):
            prices[sid] = p

    earn: dict[tuple, EarningsInput] = {}
    bases: dict[str, set] = {"ttm": set(), "fy1": set()}
    for e in inputs.earnings:
        sid, kind = e["security_id"], e["kind"]
        p = prices.get(sid)
        bad = None
        if p is None:
            continue
        if not fresh(e, sid, kind):
            continue
        if e.get("accounting_basis") not in ("gaap", "normalized"):
            bad = "UNKNOWN_ACCOUNTING_BASIS"
        elif e["currency"] != p["currency"]:
            bad = "CURRENCY_MISMATCH"
        elif e.get("split_basis_date") != p.get("split_basis_date"):
            bad = "SPLIT_BASIS_MISMATCH"
        elif kind == "ttm":
            q = e.get("latest_quarter_end")
            if not q:
                bad = "MISSING_FIELD"
            elif (c.D - date.fromisoformat(q)).days > pol.ttm_max_age_days:
                bad = "STALE_EARNINGS"
        else:
            if e.get("forecast_period") != "FY1":
                bad = "WRONG_FORECAST_PERIOD"
            elif e.get("source_updated_at"):
                if (c.D - date.fromisoformat(e["source_updated_at"])).days > pol.fy1_revision_max_age_days:
                    bad = "STALE_FORECAST"
            else:
                diags.append({"code": "FORECAST_FRESHNESS_UNVERIFIED", "security_id": sid, "kind": kind})
        if bad:
            diags.append({"code": bad, "security_id": sid, "kind": kind}); continue
        if (sid, kind) in earn:
            diags.append({"code": "EARNINGS_DUPLICATE", "security_id": sid, "kind": kind}); earn.pop((sid, kind)); continue
        earn[(sid, kind)] = EarningsInput(eps=D(e["eps"]), price=D(p["close"]))
        bases[kind].add(e["accounting_basis"])

    if c.freshness_policy == "weekly" and used_fetch and max(used_fetch) - min(used_fetch) > timedelta(days=pol.weekly_max_span_days):
        raise EligibilityError("WEEKLY_SPAN_EXCEEDED", "周度观察跨度超过7日")

    ws = inputs.basket.weights.final
    rows = [SecurityInputs(s, ws[s.security_id], earn.get((s.security_id, "ttm")), earn.get((s.security_id, "fy1")))
            for s in inputs.universe.securities]
    comparable = (c.freshness_policy != "weekly" and len(bases["ttm"] | bases["fy1"]) == 1 and bool(bases["ttm"]) and bool(bases["fy1"]))
    return ValidatedInputs(rows, basket_complete=inputs.basket.qualified, synthetic=(c.data_mode == "synthetic"),
                           accounting_comparable=comparable, diagnostics=diags,
                           index_comparability="unverified" if c.basket_policy == "fixed" else "n/a", context=c.as_dict())
