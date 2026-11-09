from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol, Sequence

REQUIRED_PRICE_FIELDS = ["security_id", "date", "close", "currency", "price_type", "session", "adjustment", "feed",
                         "split_basis_date", "fetched_at", "evidence_sha256", "locator"]


@dataclass
class PriceBatch:
    status: str                      # ok | partial | no_valid_prices | awaiting_user_import | awaiting_credentials
    prices: dict[str, dict] = field(default_factory=dict)       # 合格价格（研究输入 prices 行格式）
    matrix: list[dict] = field(default_factory=list)            # 全名单逐证券状态
    coverage: str | None = None                                  # 仅在完整名单已知时给出
    missing_fields: list[str] = field(default_factory=list)
    missing_security_ids: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"status": self.status, "coverage": self.coverage, "matrix": self.matrix,
                "missing_fields": self.missing_fields, "missing_security_ids": self.missing_security_ids}


class PriceAdapter(Protocol):
    def fetch_prices(self, target_date: date, security_ids: Sequence[str]) -> PriceBatch: ...


class AwaitingCredentials:
    """凭证未提供：不发起任何网络请求，不反复匿名请求。"""
    def __init__(self, vendor: str):
        self.vendor = vendor

    def fetch_prices(self, target_date: date, security_ids: Sequence[str]) -> PriceBatch:
        return PriceBatch("awaiting_credentials", missing_security_ids=list(security_ids),
                          missing_fields=[f"{self.vendor}_credentials"])
