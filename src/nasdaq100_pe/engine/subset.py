from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from nasdaq100_pe.dec import ONE, ZERO, div

NOTE = "并非全指数：仅覆盖已有有效盈利的证券子集，覆盖权重与排除清单见明细"


@dataclass
class SubsetResult:
    name: str
    available: bool
    reason: str = ""
    covered_weight: Decimal | None = None
    covered_count: int = 0
    excluded_ids: list[str] = field(default_factory=list)
    known_contribution: Decimal | None = None
    subset_yield: Decimal | None = None
    pe: Decimal | None = None
    pe_state: str = "incomplete"
    note: str = NOTE
    is_full_index: bool = False
    coverage_ratio: Decimal | None = None
    min_coverage: Decimal | None = None      # 方法版本≥2 的展示门槛；None 表示该方法版本没有此规则
    display_qualified: bool = False          # 覆盖达到门槛且 PE 有数值，首页才可展示“已覆盖部分 PE”


def calculate_subset(result, metric: str, min_coverage: Decimal | None = None) -> SubsetResult:
    m = result.metrics[metric]
    name = f"已覆盖证券子集{'TTM' if metric == 'ttm' else 'FY1'}估值"
    if not result.basket_complete:      # 完整权重未知一律禁止子集覆盖
        return SubsetResult(name, False, "UNKNOWN_FULL_WEIGHTS")
    C, K = m.valid_weight, m.known_contribution
    if C <= ZERO:
        return SubsetResult(name, False, "NO_COVERED_WEIGHT", covered_weight=C)
    y = div(K, C)
    pe, state = (div(C, K), "value") if K > 0 else (None, "non_positive")
    qualified = min_coverage is not None and m.coverage_ratio is not None and m.coverage_ratio >= min_coverage and state == "value"
    return SubsetResult(name, True, "", C, sum(1 for s in m.securities.values() if s.valid), list(m.missing_security_ids),
                        K, y, pe, state, coverage_ratio=m.coverage_ratio, min_coverage=min_coverage, display_qualified=qualified)
