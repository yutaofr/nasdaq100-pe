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


def calculate_subset(result, metric: str) -> SubsetResult:
    m = result.metrics[metric]
    name = f"已覆盖证券子集{'TTM' if metric == 'ttm' else 'FY1'}估值"
    if not result.basket_complete:      # 完整权重未知一律禁止子集覆盖
        return SubsetResult(name, False, "UNKNOWN_FULL_WEIGHTS")
    C, K = m.valid_weight, m.known_contribution
    if C <= ZERO:
        return SubsetResult(name, False, "NO_COVERED_WEIGHT", covered_weight=C)
    y = div(K, C)
    pe, state = (div(C, K), "value") if K > 0 else (None, "non_positive")
    return SubsetResult(name, True, "", C, sum(1 for s in m.securities.values() if s.valid), list(m.missing_security_ids),
                        K, y, pe, state)
