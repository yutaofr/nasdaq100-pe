"""方法版本 2 的 TTM 备用路径：净利润可加减，EPS 不可。

TTM 净利润 = 最近全年 + 本财年累计 − 上财年同期累计（各项均为 SEC 已报告的归母净利润）。
股数取最新报告期的加权平均稀释股数；收益率 = TTM 净利润 ÷（股数 × 价格）。
本模块不推导、不输出任何“单季 EPS”，也不替代 reported_quarter_eps_sum 路径。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from nasdaq100_pe.dec import CTX, D, BadDecimal

PATH = "net_income_ttm_over_diluted_shares"
NI_TAGS = ("NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLoss")
# ProfitLoss 可能含少数股东损益：只有同期“净利润÷稀释股数”与已报告稀释 EPS 核对相符时才可用
EPS_CHECK_REQUIRED_TAGS = ("ProfitLoss",)
PERIODIC_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A")     # 委托书(DEF 14A)等转述值不作为分量
SHARES_TAG = "WeightedAverageNumberOfDilutedSharesOutstanding"
COVER_TAG = "EntityCommonStockSharesOutstanding"
ANNUAL_DAYS = (350, 380)
QUARTER_DAYS = (70, 125)
YTD_ALIGN_DAYS = 10            # 本期与上年同期累计长度允许的差（52/53 周财年）
COVER_RATIO = (Decimal("0.75"), Decimal("1.25"))   # 封面股数 ÷ 稀释加权股数；超出视为拆股/股类口径存疑
EPS_TAG = "EarningsPerShareDiluted"
EPS_CHECK_ABS, EPS_CHECK_REL = Decimal("0.02"), Decimal("0.03")   # 净利润÷稀释股数 与 已报告稀释EPS 的容差
FACT_KEYS = ("start", "end", "val", "accn", "form", "filed")


class ComponentError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class NetIncomeSelection:
    status: str                        # ok | missing_label | missing_component | needs_manual_review
    profit: Decimal | None = None
    shares: Decimal | None = None
    latest_period_end: str | None = None
    components: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    calculation_path: str = PATH


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _days(e: dict) -> int:
    return (_d(e["end"]) - _d(e["start"])).days + 1


def _dec(v) -> Decimal:
    """SEC 数值是 JSON 数字；金额与股数必须是有限的十进制整数或小数。"""
    if isinstance(v, bool) or not isinstance(v, (int, str)):
        raise ComponentError("BAD_NUMBER")
    try:
        return D(str(v))
    except BadDecimal:
        raise ComponentError("BAD_NUMBER")


def compute_from_components(c: dict) -> tuple[Decimal, Decimal, str]:
    """由证据分量复算 (TTM净利润, 股数, 最新期末)。选择器与输入校验共用，任何不一致都拒绝。"""
    if not isinstance(c, dict):
        raise ComponentError("TTM_EVIDENCE_INSUFFICIENT")
    fy, cur, prev, sh = c.get("fy"), c.get("ytd_current"), c.get("ytd_prior"), c.get("shares")
    for part in (fy, sh) + ((cur, prev) if (cur or prev) else ()):
        if not isinstance(part, dict) or any(part.get(k) in (None, "") for k in FACT_KEYS):
            raise ComponentError("TTM_EVIDENCE_INSUFFICIENT")
    if c.get("net_income_tag") not in NI_TAGS or any(x and x.get("form") not in PERIODIC_FORMS for x in (fy, cur, prev, sh)):
        raise ComponentError("TTM_EVIDENCE_INSUFFICIENT")
    try:
        if not ANNUAL_DAYS[0] <= _days(fy) <= ANNUAL_DAYS[1]:
            raise ComponentError("TTM_PERIOD_MISALIGNED")
        profit, latest = _dec(fy["val"]), fy["end"]
        if cur:
            if _d(cur["start"]) != _d(fy["end"]) + timedelta(days=1) or _days(cur) >= ANNUAL_DAYS[0]:
                raise ComponentError("TTM_PERIOD_MISALIGNED")
            if prev["start"] != fy["start"] or _d(prev["end"]) >= _d(fy["end"]) \
                    or abs(_days(prev) - _days(cur)) > YTD_ALIGN_DAYS:
                raise ComponentError("TTM_PERIOD_MISALIGNED")
            profit = CTX.subtract(CTX.add(profit, _dec(cur["val"])), _dec(prev["val"]))
            latest = cur["end"]
        if sh["end"] != latest:
            raise ComponentError("TTM_PERIOD_MISALIGNED")
        n = _days(sh)
        quarter = QUARTER_DAYS[0] <= n <= QUARTER_DAYS[1]
        annual_only = not cur and ANNUAL_DAYS[0] <= n <= ANNUAL_DAYS[1]
        if not (quarter or annual_only):
            raise ComponentError("TTM_PERIOD_MISALIGNED")
        shares = _dec(sh["val"])
        if shares <= 0:
            raise ComponentError("BAD_SHARE_COUNT")
        cover = c.get("cover_shares")
        if cover is not None:
            if not isinstance(cover, dict) or any(cover.get(k) in (None, "") for k in ("end", "val", "accn", "form", "filed")):
                raise ComponentError("TTM_EVIDENCE_INSUFFICIENT")
            ratio = CTX.divide(_dec(cover["val"]), shares)
            if not COVER_RATIO[0] <= ratio <= COVER_RATIO[1]:
                raise ComponentError("SHARE_COUNT_INCONSISTENT")
        chk = c.get("eps_check")
        if chk is None and c["net_income_tag"] in EPS_CHECK_REQUIRED_TAGS:
            raise ComponentError("COMMON_EARNINGS_UNVERIFIED")
        if chk is not None:
            # 同一期间：归母净利润 ÷ 稀释股数 应与已报告稀释 EPS 相符；不符说明净利润不全归普通股（优先股等）
            ni, eps = (chk or {}).get("net_income"), (chk or {}).get("eps")
            for part in (ni, eps):
                if not isinstance(part, dict) or any(part.get(k) in (None, "") for k in FACT_KEYS) \
                        or part.get("form") not in PERIODIC_FORMS or (part["start"], part["end"]) != (sh["start"], sh["end"]):
                    raise ComponentError("TTM_EVIDENCE_INSUFFICIENT")
            rep = CTX.create_decimal(str(eps["val"]))
            if not rep.is_finite():
                raise ComponentError("BAD_NUMBER")
            if abs(CTX.divide(_dec(ni["val"]), shares) - rep) > max(EPS_CHECK_ABS, abs(rep) * EPS_CHECK_REL):
                raise ComponentError("COMMON_EARNINGS_MISMATCH")
    except (KeyError, TypeError, ValueError, ArithmeticError) as e:
        if isinstance(e, ComponentError):
            raise
        raise ComponentError("TTM_EVIDENCE_INSUFFICIENT")
    return profit, shares, latest


def _resolve(entries: list[dict], as_of: date, filed_cutoff: date, need_start: bool = True) -> list[dict] | None:
    """按期间去重，取截点前最新申报的值；同一申报日出现不同值则返回 None（转人工）。"""
    groups: dict[tuple, list[dict]] = {}
    for e in entries:
        if not e.get("end") or (need_start and not e.get("start")) or not e.get("filed"):
            continue
        if e.get("form") not in PERIODIC_FORMS:
            continue
        if _d(e["end"]) > as_of or _d(e["filed"]) > filed_cutoff:
            continue
        groups.setdefault((e.get("start"), e["end"]), []).append(e)
    out = []
    for g in groups.values():
        latest = max(x["filed"] for x in g)
        top = [x for x in g if x["filed"] == latest]
        if len({str(x["val"]) for x in top}) > 1:
            return None
        out.append(top[0])
    return out


def _fact(e: dict, keys=FACT_KEYS) -> dict:
    return {k: e[k] for k in keys if k in e}


def select_ttm_net_income(cf: dict, as_of: date, filed_cutoff: date) -> NetIncomeSelection:
    """逐个归母净利润标签尝试（最新期末靠后的优先）；所有分量必须出自同一标签。"""
    gaap = cf.get("facts", {}).get("us-gaap", {}) or {}
    sh = ((gaap.get(SHARES_TAG) or {}).get("units") or {}).get("shares")
    cands = []
    for rank, tag in enumerate(NI_TAGS):
        ni = ((gaap.get(tag) or {}).get("units") or {}).get("USD")
        if ni:
            r = _resolve(ni, as_of, filed_cutoff)
            if r is None:
                return NetIncomeSelection("needs_manual_review", reasons=["AMBIGUOUS_VALUE"])
            if r:
                cands.append((max(e["end"] for e in r), -rank, tag, r))
    if not cands:
        return NetIncomeSelection("missing_label", reasons=["MISSING_NET_INCOME_LABEL"])
    if not sh:
        return NetIncomeSelection("missing_label", reasons=["MISSING_DILUTED_SHARES_LABEL"])
    sh_r = _resolve(sh, as_of, filed_cutoff)
    if sh_r is None:
        return NetIncomeSelection("needs_manual_review", reasons=["AMBIGUOUS_VALUE"])
    first = None
    for _, _, tag, ni_r in sorted(cands, key=lambda c: c[:2], reverse=True):
        sel = _select(cf, tag, ni_r, sh_r, as_of, filed_cutoff)
        if sel.status == "ok":
            return sel
        first = first or sel
    return first


def _select(cf: dict, tag: str, ni_r: list[dict], sh_r: list[dict], as_of: date, filed_cutoff: date) -> NetIncomeSelection:
    annual = [e for e in ni_r if ANNUAL_DAYS[0] <= _days(e) <= ANNUAL_DAYS[1]]
    if not annual:
        return NetIncomeSelection("missing_component", reasons=["MISSING_ANNUAL"])
    fy = max(annual, key=lambda e: e["end"])
    comps: dict = {"net_income_tag": tag, "fy": _fact(fy)}
    nxt = (_d(fy["end"]) + timedelta(days=1)).isoformat()
    ytd = [e for e in ni_r if e["start"] == nxt and _days(e) < ANNUAL_DAYS[0]]
    latest = fy["end"]
    if ytd:
        cur = max(ytd, key=lambda e: e["end"])
        prior = [e for e in ni_r if e["start"] == fy["start"] and _d(e["end"]) < _d(fy["end"])
                 and abs(_days(e) - _days(cur)) <= YTD_ALIGN_DAYS]
        if len(prior) != 1:
            return NetIncomeSelection("missing_component", reasons=["MISSING_PRIOR_YTD"])
        comps["ytd_current"], comps["ytd_prior"] = _fact(cur), _fact(prior[0])
        latest = cur["end"]
    at_end = [e for e in sh_r if e["end"] == latest]
    pick = [e for e in at_end if QUARTER_DAYS[0] <= _days(e) <= QUARTER_DAYS[1]]
    if not pick and not ytd:
        pick = [e for e in at_end if ANNUAL_DAYS[0] <= _days(e) <= ANNUAL_DAYS[1]]
    if len(pick) != 1:
        return NetIncomeSelection("missing_component", reasons=["MISSING_DILUTED_SHARES"])
    comps["shares"] = _fact(pick[0])
    flags = []
    cover = _resolve((((cf.get("facts", {}).get("dei", {}) or {}).get(COVER_TAG) or {}).get("units") or {}).get("shares") or [],
                     as_of, filed_cutoff, need_start=False)
    cover = [e for e in (cover or []) if _d(e["end"]) >= _d(latest)]
    if cover:
        comps["cover_shares"] = _fact(max(cover, key=lambda e: e["end"]), ("end", "val", "accn", "form", "filed"))
    else:
        flags.append("COVER_SHARES_UNAVAILABLE")   # 多股类发行人常见：companyfacts 不含分股类封面股数
    span = (comps["shares"]["start"], comps["shares"]["end"])
    eps_r = _resolve((((cf.get("facts", {}).get("us-gaap", {}) or {}).get(EPS_TAG) or {}).get("units") or {}).get("USD/shares") or [],
                     as_of, filed_cutoff)
    eps_at = [e for e in (eps_r or []) if (e["start"], e["end"]) == span]
    ni_at = [e for e in ni_r if (e["start"], e["end"]) == span]
    if len(eps_at) == 1 and len(ni_at) == 1:
        comps["eps_check"] = {"net_income": _fact(ni_at[0]), "eps": _fact(eps_at[0])}
    else:
        flags.append("EPS_CROSSCHECK_UNAVAILABLE")
    try:
        profit, shares, latest = compute_from_components(comps)
    except ComponentError as e:
        status = "needs_manual_review" if e.code in ("SHARE_COUNT_INCONSISTENT", "COMMON_EARNINGS_MISMATCH") else "missing_component"
        return NetIncomeSelection(status, components=comps, reasons=[e.code])
    return NetIncomeSelection("ok", profit, shares, latest, comps, flags=flags)
