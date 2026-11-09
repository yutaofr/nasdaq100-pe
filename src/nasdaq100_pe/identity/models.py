from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class SourceEvidence:
    source_id: str
    content_sha256: str
    fetched_at: str
    locator: str = ""


@dataclass(frozen=True)
class SecurityIdentity:
    security_id: str          # 内部永久ID，不得等于 CUSIP/代码
    issuer_id: str
    share_class: str
    ticker: str
    name: str
    sector: str | None = None
    sector_source: str | None = None
    cusip: str | None = None
    is_adr: bool = False
    adr_ratio: str | None = None
    ticker_history: tuple = ()   # ({"ticker","from","to"},...)


@dataclass
class Universe:
    as_of: str
    source_id: str
    listing_scope: str            # full | top_n | partial | unknown
    securities: list[SecurityIdentity]
    complete: bool                # 仅当有完整性证据（listing_scope=full 且来源存在）时为真


@dataclass
class WeightSet:
    mode: str
    date: str
    source_id: str
    raw: dict[str, Decimal]                       # 原始权重（股票）
    excluded: list[dict] = field(default_factory=list)
    known_excluded_weight: Decimal | None = None
    unknown_excluded_items: list[str] = field(default_factory=list)
    total_excluded_weight: Decimal | None = None
    official_rounding_factor: Decimal | None = None   # 官方权重和舍入修正
    proxy_normalization_factor: Decimal | None = None  # 代理按股票和归一化
    final: dict[str, Decimal] = field(default_factory=dict)
