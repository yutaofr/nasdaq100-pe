"""唯一计算内核。不读网络/系统时钟，不访问引用指标。确定性：按稳定证券ID排序遍历。"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from nasdaq100_pe.dec import CTX, ONE, ZERO, D, add, div, dsum, dstr, mul, sub
from nasdaq100_pe.identity.models import SecurityIdentity
from nasdaq100_pe.method import MethodSpec

KINDS = ("ttm", "fy1")
ENGINE_VERSION = "1"


@dataclass
class EarningsInput:
    eps: Decimal | None = None
    price: Decimal | None = None
    pe: Decimal | None = None
    profit: Decimal | None = None
    market_cap: Decimal | None = None
    profit_path_verified: bool = False


@dataclass
class SecurityInputs:
    security: SecurityIdentity
    weight: Decimal
    ttm: EarningsInput | None = None
    fy1: EarningsInput | None = None
    company_market_cap: Decimal | None = None
    cap_currency: str = "USD"


@dataclass
class ValidatedInputs:
    securities: list[SecurityInputs]
    basket_complete: bool
    synthetic: bool = False          # 合成对象须明确标识
    accounting_comparable: bool = False
    diagnostics: list = field(default_factory=list)
    index_comparability: str = "n/a"
    context: dict = field(default_factory=dict)


@dataclass
class SecResult:
    security_id: str
    weight: Decimal
    valid: bool
    yield_: Decimal | None = None
    contribution: Decimal | None = None
    contribution_points: Decimal | None = None
    pe: Decimal | None = None          # 个股PE；EPS=0 时无意义为 None；负值表示亏损
    flags: list[str] = field(default_factory=list)


@dataclass
class SectorResult:
    name: str
    weight: Decimal
    valid_weight: Decimal
    known_contribution: Decimal
    complete: bool
    sector_yield: Decimal | None
    pe: Decimal | None
    pe_state: str
    note: str = ""
    member_ids: list[str] = field(default_factory=list)


@dataclass
class MetricResult:
    eligibility: str
    quality_flags: list[str]
    valid_weight: Decimal
    coverage_ratio: Decimal | None
    known_contribution: Decimal
    portfolio_yield: Decimal | None
    pe: Decimal | None
    pe_state: str
    missing_security_ids: list[str]
    securities: dict[str, SecResult]
    sectors: list[SectorResult] = field(default_factory=list)


@dataclass
class CalculationResult:
    metrics: dict[str, MetricResult]
    derived: dict
    total_market_cap: Decimal | None
    market_cap_flags: list[str]
    method_version: str
    engine_version: str = ENGINE_VERSION
    basket_complete: bool = False

    def to_dict(self) -> dict:
        return _plain({"metrics": self.metrics, "derived": self.derived, "total_market_cap": self.total_market_cap,
                       "market_cap_flags": self.market_cap_flags, "method_version": self.method_version,
                       "engine_version": self.engine_version, "basket_complete": self.basket_complete})


def _plain(o):
    if isinstance(o, Decimal):
        return dstr(o)
    if isinstance(o, dict):
        return {k: _plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_plain(v) for v in o]
    if hasattr(o, "__dataclass_fields__"):
        return {k: _plain(getattr(o, k)) for k in o.__dataclass_fields__}
    return o


def _security_yield(e: EarningsInput | None, tol: Decimal) -> tuple[Decimal | None, list[str], Decimal | None]:
    """返回 (收益率, 标记, 个股PE)。多路径冲突不平均、判无效；PE=0 不推导零盈利；未验证利润/市值路径不启用。"""
    flags: list[str] = []
    if e is None:
        return None, ["MISSING_FIELD"], None
    paths: list[Decimal] = []
    if e.eps is not None and e.price is not None:
        if e.price > 0:
            paths.append(div(e.eps, e.price))
        else:
            flags.append("BAD_PRICE")
    if e.pe is not None:
        if e.pe == 0:
            flags.append("PE_ZERO_NOT_ZERO_EARNINGS")
        else:
            paths.append(div(ONE, e.pe))
    if e.profit is not None and e.market_cap is not None:
        if e.profit_path_verified and e.market_cap > 0:
            paths.append(div(e.profit, e.market_cap))
        else:
            flags.append("PROFIT_PATH_UNVERIFIED")
    if not paths:
        return None, flags or ["MISSING_FIELD"], None
    if any(abs(sub(p, paths[0])) > tol for p in paths[1:]):
        return None, flags + ["PATH_CONFLICT"], None
    y = paths[0]
    pe_i = None if y == 0 else div(ONE, y)
    return y, flags, pe_i


def _metric(kind: str, inputs: ValidatedInputs, tol: Decimal) -> MetricResult:
    from nasdaq100_pe.engine.sectors import sector_results
    rows = sorted(inputs.securities, key=lambda r: r.security.security_id)
    secs: dict[str, SecResult] = {}
    for r in rows:
        y, flags, pe_i = _security_yield(getattr(r, kind), tol)
        sid = r.security.security_id
        if y is None:
            secs[sid] = SecResult(sid, r.weight, False, flags=flags)
        else:
            c = mul(r.weight, y)
            secs[sid] = SecResult(sid, r.weight, True, y, c, mul(D("100"), c), pe_i, flags)
    valid = [s for s in secs.values() if s.valid]
    missing = sorted(s.security_id for s in secs.values() if not s.valid)
    C = dsum(s.weight for s in valid)
    K = dsum(s.contribution for s in valid)
    total_w = dsum(s.weight for s in secs.values())
    flags: list[str] = []
    if not inputs.basket_complete:
        flags.append("UNKNOWN_UNIVERSE")
    all_valid = bool(secs) and not missing
    complete = all_valid and inputs.basket_complete
    elig = "complete" if complete else ("partial" if valid else "unavailable")
    cov = div(C, total_w) if inputs.basket_complete and total_w != 0 else None
    Y = K if complete else None
    pe, state = None, "incomplete"
    if complete:
        if Y > 0:
            pe, state = div(ONE, Y), "value"
        else:
            state = "non_positive"
    m = MetricResult(elig, flags, C, cov, K, Y, pe, state, missing, secs)
    m.sectors = sector_results(rows, secs)
    return m


def _market_cap(inputs: ValidatedInputs) -> tuple[Decimal | None, list[str]]:
    by_issuer: dict[str, set] = {}
    cur = {r.cap_currency for r in inputs.securities}
    flags: set[str] = set()
    for r in inputs.securities:
        by_issuer.setdefault(r.security.issuer_id, set())
        if r.company_market_cap is not None:
            by_issuer[r.security.issuer_id].add(r.company_market_cap)
    for vals in by_issuer.values():
        if not vals:
            flags.add("MARKET_CAP_MISSING")
        elif len(vals) > 1:
            flags.add("MARKET_CAP_CONFLICT")
    if len(cur) > 1:
        flags.add("MARKET_CAP_CURRENCY_MIXED")
    if flags or not by_issuer:
        return None, sorted(flags)
    return dsum(next(iter(v)) for _, v in sorted(by_issuer.items())), []


def calculate(inputs: ValidatedInputs, method: MethodSpec) -> CalculationResult:
    from nasdaq100_pe.engine.derived import derive
    tol = Decimal(method.calc_tolerance)
    metrics = {k: _metric(k, inputs, tol) for k in KINDS}
    total, mflags = _market_cap(inputs)
    return CalculationResult(metrics, derive(metrics, inputs), total, mflags, method.method_version, basket_complete=inputs.basket_complete)
