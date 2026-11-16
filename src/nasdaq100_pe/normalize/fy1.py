"""FY1（下一财年）一致预期 EPS 的选择：只做期间判定与口径取证，不推算任何数值。

来源是 Nasdaq 个股“Earnings”页所调用的两个接口（数据由其供应商提供）：
- earnings-forecast：按财年列出的一致预期 EPS 均值、估计数与财年末月份；
- earnings-surprise：最近几个季度“来源口径的已报告 EPS”，用来与 SEC 的 GAAP 稀释 EPS 对照，
  证明该序列是调整后（normalized）口径还是与 GAAP 相同。

下一财年的判定不依赖行序：先由 SEC 申报得到最近一个已结束财年末 L（年报期间；没有年报时用季报累计期起点推出），
含 D 的财年 = 第一个不早于 D 的 L+k 年，FY1 = 其后一个财年；再在来源表里找财年末月份相符的唯一一行。
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from nasdaq100_pe.dec import BadDecimal, D, dstr

FORECAST_HEADERS = {"fiscalEnd": "Fiscal Year End", "consensusEPSForecast": "Consensus EPS* Forecast"}
SURPRISE_HEADERS = {"fiscalQtrEnd": "Fiscal Quarter End", "eps": "Earnings Per Share*",
                    "consensusForecast": "Consensus EPS* Forecast"}
ANNUAL_FORMS = ("10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A")
INTERIM_FORMS = ("10-Q", "10-Q/A", "6-K")
ANNUAL_DAYS = (350, 380)
QUARTER_DAYS = (70, 125)
BOUNDARY_DAYS = 7          # 52/53 周财年的期末漂移；D 落在推算财年末 ±7 天内无法判定所属财年
MONTH_SLACK_DAYS = 10      # 推算财年末与来源“月份”之间允许的漂移
USD_PROFIT_TAGS = (("us-gaap", "NetIncomeLoss"), ("us-gaap", "ProfitLoss"),
                   ("us-gaap", "NetIncomeLossAvailableToCommonStockholdersBasic"), ("ifrs-full", "ProfitLoss"),
                   ("ifrs-full", "ProfitLossAttributableToOwnersOfParent"))
BASIS_TOL = Decimal("0.015")   # 来源口径 EPS 与 GAAP 稀释 EPS 之差超过此值记为“有调整”
_MONTHS = {m: i for i, m in enumerate(calendar.month_abbr) if m}


@dataclass
class Fy1Selection:
    status: str                       # ok | no_forecast | no_fiscal_reference | ambiguous | currency_unverified | basis_unverified
    eps: Decimal | None = None
    fiscal_year_end: str | None = None           # 来源只给到月份：取该月最后一天
    estimates: int | None = None
    reasons: list[str] = field(default_factory=list)
    period_evidence: dict = field(default_factory=dict)
    basis_evidence: dict = field(default_factory=dict)


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _add_years(d: date, k: int) -> date:
    y = d.year + k
    return date(y, d.month, min(d.day, calendar.monthrange(y, d.month)[1]))


def parse_month(label) -> tuple[int, int] | None:
    """'Sep 2027' → (2027, 9)。"""
    try:
        mon, year = str(label).split()
        return int(year), _MONTHS[mon[:3].title()]
    except (ValueError, KeyError):
        return None


def fiscal_year_reference(cf: dict, as_of: date, filed_cutoff: date) -> dict | None:
    """最近一个已结束财年的期末及其依据。

    优先取已申报年报里最近的 350–380 天期间；上市不足一个财年、还没有年报的发行人，
    用最新季报的本财年累计期起点推出上一财年末（起点前一天）。
    """
    annual, interim = None, []
    for tax, tags in (cf.get("facts") or {}).items():
        if tax == "dei":
            continue
        for tag, node in tags.items():
            for unit, entries in (node.get("units") or {}).items():
                for e in entries:
                    if not e.get("start") or not e.get("end") or not e.get("filed"):
                        continue
                    try:
                        s, en, f = _d(e["start"]), _d(e["end"]), _d(e["filed"])
                    except ValueError:
                        continue
                    if en > as_of or f > filed_cutoff:
                        continue
                    days = (en - s).days + 1
                    rec = {"start": e["start"], "end": e["end"], "form": e.get("form"), "filed": e["filed"],
                           "accn": e.get("accn"), "locator": f"{tax}/{tag}/{unit}"}
                    if e.get("form") in ANNUAL_FORMS and ANNUAL_DAYS[0] <= days <= ANNUAL_DAYS[1]:
                        if annual is None or rec["end"] > annual["end"]:
                            annual = rec
                    elif e.get("form") in INTERIM_FORMS and days < ANNUAL_DAYS[0]:
                        interim.append(rec)
    if annual:
        return dict(annual, basis="annual_report")
    if not interim:
        return None
    latest = max(r["end"] for r in interim)
    ytd = min((r for r in interim if r["end"] == latest), key=lambda r: r["start"])     # 累计期起点 = 本财年起点
    return {"end": (_d(ytd["start"]) - timedelta(days=1)).isoformat(), "basis": "interim_ytd_start", "interim_period": ytd}


def reports_in_usd(cf: dict) -> str | None:
    """发行人最近一期利润只以 USD 报告时返回该事实的定位；否则 None（预测币种无从核对）。

    同一期同时有本币与 USD 折算值（如 20-F 的便利折算）不算以 USD 报告。
    """
    facts = cf.get("facts") or {}
    for tax, tag in USD_PROFIT_TAGS:
        units = ((facts.get(tax) or {}).get(tag) or {}).get("units") or {}
        ends = {u: max((e.get("end") or "" for e in es), default="") for u, es in units.items() if es}
        if not ends:
            continue
        latest = max(ends.values())
        return f"{tax}/{tag}/USD" if {u for u, e in ends.items() if e == latest} == {"USD"} else None
    return None


def _gaap_quarter_eps(cf: dict, filed_cutoff: date) -> dict[tuple[int, int], str]:
    """(年, 月) → 已报告单季 GAAP 稀释 EPS（同月多值时取最新申报）。"""
    entries = ((((cf.get("facts") or {}).get("us-gaap") or {}).get("EarningsPerShareDiluted") or {}).get("units") or {}).get("USD/shares") or []
    out: dict[tuple[int, int], tuple[str, str]] = {}
    for e in entries:
        try:
            s, en, f = _d(e["start"]), _d(e["end"]), _d(e["filed"])
        except (KeyError, ValueError, TypeError):
            continue
        if f > filed_cutoff or not QUARTER_DAYS[0] <= (en - s).days + 1 <= QUARTER_DAYS[1]:
            continue
        # 52/53 周财年的季末可能落在下月头几天：归到最近的月末
        key_date = en if en.day > 7 else en - timedelta(days=en.day)
        k = (key_date.year, key_date.month)
        if k not in out or e["filed"] > out[k][0]:
            out[k] = (e["filed"], str(e["val"]))
    return {k: v for k, (_, v) in out.items()}


def basis_evidence(surprise: dict | None, cf: dict, filed_cutoff: date) -> dict | None:
    """来源口径已报告 EPS 与 GAAP 稀释 EPS 的逐季对照。来源表头不符或无数据返回 None。"""
    try:
        tbl = surprise["data"]["earningsSurpriseTable"]
        if any(tbl["headers"].get(k) != v for k, v in SURPRISE_HEADERS.items()):
            return None
        rows = tbl["rows"]
    except (KeyError, TypeError):
        return None
    gaap = _gaap_quarter_eps(cf, filed_cutoff)
    cmp_rows, adjusted, same = [], 0, 0
    for r in rows or []:
        ym = parse_month(r.get("fiscalQtrEnd"))
        try:
            src = D(str(r.get("eps")))
        except BadDecimal:
            continue
        if ym is None:
            continue
        item = {"fiscal_quarter_end": r["fiscalQtrEnd"], "source_eps": dstr(src), "gaap_diluted_eps": gaap.get(ym)}
        if item["gaap_diluted_eps"] is not None:
            if abs(src - D(item["gaap_diluted_eps"])) > BASIS_TOL:
                adjusted += 1
            else:
                same += 1
        cmp_rows.append(item)
    if not cmp_rows:
        return None
    return {"method": "来源“Earnings Per Share*”（与一致预期同一星号口径）对照 SEC us-gaap/EarningsPerShareDiluted 单季值",
            "quarters": cmp_rows, "quarters_differing_from_gaap": adjusted, "quarters_equal_to_gaap": same}


def select_fy1(forecast: dict, surprise: dict | None, cf: dict, as_of: date, filed_cutoff: date) -> Fy1Selection:
    try:
        yearly = forecast["data"]["yearlyForecast"]
        if any(yearly["headers"].get(k) != v for k, v in FORECAST_HEADERS.items()):
            return Fy1Selection("no_forecast", reasons=["UNEXPECTED_FORECAST_HEADER"])
        rows = yearly["rows"] or []
    except (KeyError, TypeError):
        return Fy1Selection("no_forecast", reasons=["NO_YEARLY_FORECAST"])
    if not rows:
        return Fy1Selection("no_forecast", reasons=["NO_YEARLY_FORECAST"])
    ref = fiscal_year_reference(cf, as_of, filed_cutoff)
    if ref is None:
        return Fy1Selection("no_fiscal_reference", reasons=["NO_REPORTED_FISCAL_YEAR"])
    last_end = _d(ref["end"])
    k = 1
    while _add_years(last_end, k) < as_of - timedelta(days=BOUNDARY_DAYS):
        k += 1
    current_end = _add_years(last_end, k)
    if abs((current_end - as_of).days) <= BOUNDARY_DAYS:
        return Fy1Selection("ambiguous", reasons=["FISCAL_YEAR_BOUNDARY_AMBIGUOUS"])
    target = _add_years(last_end, k + 1)
    matches = []
    for r in rows:
        ym = parse_month(r.get("fiscalEnd"))
        if ym is None:
            continue
        first = date(ym[0], ym[1], 1)
        last = date(ym[0], ym[1], calendar.monthrange(*ym)[1])
        if first - timedelta(days=MONTH_SLACK_DAYS) <= target <= last + timedelta(days=MONTH_SLACK_DAYS):
            matches.append((r, last))
    if len(matches) != 1:
        return Fy1Selection("no_forecast" if not matches else "ambiguous",
                            reasons=["NEXT_FISCAL_YEAR_NOT_IN_SOURCE" if not matches else "MULTIPLE_PERIOD_MATCHES"])
    row, month_end = matches[0]
    try:
        eps = D(str(row.get("consensusEPSForecast")))
        n = int(row.get("noOfEstimates"))
    except (BadDecimal, TypeError, ValueError):
        return Fy1Selection("no_forecast", reasons=["BAD_FORECAST_VALUE"])
    if n < 1:
        return Fy1Selection("no_forecast", reasons=["NO_ESTIMATES"])
    period = {"source_label": row["fiscalEnd"], "source_field": "yearlyForecast.rows[fiscalEnd].consensusEPSForecast",
              "number_of_estimates": n, "last_completed_fiscal_year": ref,
              "current_fiscal_year_end_projected": current_end.isoformat(),
              "next_fiscal_year_end_projected": target.isoformat(),
              "rule": "FY1 = 含 D 的财年之后的下一财年；来源只给财年末月份，fiscal_year_end 取该月最后一天"}
    usd = reports_in_usd(cf)
    if usd is None:
        return Fy1Selection("currency_unverified", reasons=["FORECAST_CURRENCY_UNVERIFIED"], period_evidence=period)
    period["reporting_currency_evidence"] = usd
    basis = basis_evidence(surprise, cf, filed_cutoff)
    if basis is None:
        return Fy1Selection("basis_unverified", reasons=["FORECAST_BASIS_UNVERIFIED"], period_evidence=period)
    return Fy1Selection("ok", eps, month_end.isoformat(), n, period_evidence=period, basis_evidence=basis)
