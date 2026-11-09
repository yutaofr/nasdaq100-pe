from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class MethodSpec:
    method_version: str = "1"
    precision: int = 34
    calc_tolerance: str = "1e-10"
    weight_sum_tolerance: str = "0.0001"
    fixed_basket_max_lag_trading_days: int = 5
    weekly_max_age_days: int = 7
    weekly_max_span_days: int = 7
    daily_freshness_hours: int = 24
    ttm_max_age_days: int = 180
    fy1_revision_max_age_days: int = 30
    strict_cutoff_hour_ny: int = 12
    sector_taxonomy: str = "provider-sector-v1"

    @staticmethod
    def load(path: Path | None = None) -> "MethodSpec":
        p = path or Path(__file__).resolve().parent / "config" / "methods.json"
        return MethodSpec(**json.loads(p.read_text(encoding="utf-8"))) if p.exists() else MethodSpec()
