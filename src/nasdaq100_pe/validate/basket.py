"""完整篮子校验：身份、权重、排除项、舍入修正与代理归一化（不产生PE）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from nasdaq100_pe.dec import CTX, ONE, ZERO, D, BadDecimal, add, div, dsum, mul, sub
from nasdaq100_pe.identity.models import Universe, WeightSet
from nasdaq100_pe.method import MethodSpec

NON_EQUITY = {"cash", "other", "derivative", "bond"}
MODES = {"official_full", "qqq_equity_proxy", "qqq_fixed_basket"}


@dataclass
class BasketResult:
    qualified: bool
    structural_error: bool
    weights: WeightSet | None
    diagnostics: list[dict] = field(default_factory=list)
    denominator_known: bool = False
    coverage_ratio: str | None = None    # 无可信完整权重恒为 None


def _d(code, path, msg): return {"code": code, "path": path, "message": msg}


def validate_basket(universe: Universe, weights: dict, method: MethodSpec) -> BasketResult:
    diags: list[dict] = []
    structural = False
    ids = [s.security_id for s in universe.securities]

    # 身份
    seen = set()
    for i, s in enumerate(universe.securities):
        if s.security_id in seen:
            diags.append(_d("DUPLICATE_SECURITY", f"universe.securities[{i}]", s.security_id)); structural = True
        seen.add(s.security_id)
        if s.cusip and s.security_id == s.cusip:
            diags.append(_d("CUSIP_AS_ID", f"universe.securities[{i}]", "CUSIP 不得代替内部永久ID")); structural = True
        if s.is_adr and not s.adr_ratio:
            diags.append(_d("ADR_RATIO_UNKNOWN", f"universe.securities[{i}]", "ADR比例无证据，不猜测"))

    # 完整性证据
    qualified = universe.complete
    if not universe.complete:
        diags.append(_d("UNKNOWN_UNIVERSE", "universe", "缺少完整名单证据（listing_scope 须为 full 且来源可核）"))

    mode = weights.get("mode")
    if mode not in MODES:
        diags.append(_d("UNKNOWN_MODE", "weights.mode", str(mode))); structural = True

    # 原权重
    raw: dict[str, Decimal] = {}
    for i, it in enumerate(weights.get("items", [])):
        sid = it.get("security_id")
        try:
            w = D(it.get("weight"))
        except BadDecimal:
            diags.append(_d("BAD_WEIGHT", f"weights.items[{i}].weight", "非有限十进制字符串")); structural = True; continue
        if w < 0:
            diags.append(_d("NEGATIVE_WEIGHT", f"weights.items[{i}].weight", sid)); structural = True
        if sid in raw:
            diags.append(_d("DUPLICATE_WEIGHT", f"weights.items[{i}]", sid)); structural = True
        if sid not in seen:
            diags.append(_d("UNKNOWN_SECURITY_IN_WEIGHTS", f"weights.items[{i}]", sid)); structural = True
        raw[sid] = w
    for sid in ids:
        if sid not in raw:
            diags.append(_d("MISSING_WEIGHT", "weights.items", f"成分 {sid} 缺少权重（不得当作现金排除）")); structural = True

    # 排除项
    known_excl = ZERO
    unknown_items: list[str] = []
    excluded = []
    for i, ex in enumerate(weights.get("excluded", [])):
        ac = ex.get("asset_class")
        if ac not in NON_EQUITY:
            diags.append(_d("UNKNOWN_ASSET_CLASS", f"weights.excluded[{i}]", f"资产类别 {ac!r} 未知，整个权重集不合格"))
            structural = True; qualified = False
        if ex.get("weight") is None:
            unknown_items.append(ex.get("label", f"#{i}"))
        else:
            try:
                known_excl = add(known_excl, D(ex["weight"]))
            except BadDecimal:
                diags.append(_d("BAD_WEIGHT", f"weights.excluded[{i}].weight", "非有限十进制字符串")); structural = True
        excluded.append(ex)

    if structural:
        return BasketResult(False, True, None, diags)

    eq_sum = dsum(raw.values())
    ws = WeightSet(mode=mode, date=weights.get("date", ""), source_id=weights.get("source_id", ""), raw=dict(raw),
                   excluded=excluded, known_excluded_weight=known_excl if weights.get("excluded") else None,
                   unknown_excluded_items=unknown_items,
                   total_excluded_weight=None if unknown_items else (known_excl if weights.get("excluded") else ZERO))
    tol = D(method.weight_sum_tolerance)

    # 官方权重和舍入修正：所有资产权重已知才可核对总和
    if not unknown_items:
        total = add(eq_sum, known_excl)
        if abs(sub(total, ONE)) > tol:
            diags.append(_d("WEIGHT_SUM_OUT_OF_TOLERANCE", "weights", f"权重和 {total} 与1之差超过 {tol}"))
            return BasketResult(False, True, None, diags)
        ws.official_rounding_factor = div(ONE, total)
    else:
        ws.official_rounding_factor = ONE
        if eq_sum > add(ONE, tol):
            diags.append(_d("WEIGHT_SUM_OUT_OF_TOLERANCE", "weights", "股票权重和超过1"))
            return BasketResult(False, True, None, diags)
        diags.append(_d("EXCLUDED_WEIGHT_PARTIALLY_UNKNOWN", "weights.excluded", "非股票权重部分未知；不作舍入修正"))

    corrected = {k: mul(v, ws.official_rounding_factor) for k, v in raw.items()}
    if mode == "official_full":
        ws.proxy_normalization_factor = ONE
        ws.final = corrected
    else:  # 代理：对全部股票按股票权重和归一化
        c_sum = dsum(corrected.values())
        if c_sum == ZERO:
            diags.append(_d("ZERO_EQUITY_WEIGHT", "weights", "股票权重和为0")); return BasketResult(False, True, None, diags)
        ws.proxy_normalization_factor = div(ONE, c_sum)
        ws.final = {k: mul(v, ws.proxy_normalization_factor) for k, v in corrected.items()}
    return BasketResult(qualified, False, ws, diags, denominator_known=qualified)


def coverage_ratio(valid_weight: Decimal | None, basket: BasketResult) -> str | None:
    """无可信完整权重时为 None（显示“完整权重未知”），绝不返回 0 或用证券数充当分母。"""
    if not basket.denominator_known or valid_weight is None or basket.weights is None:
        return None
    from nasdaq100_pe.dec import dstr
    return dstr(div(valid_weight, dsum(basket.weights.final.values())))
