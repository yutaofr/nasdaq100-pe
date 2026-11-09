from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


class CalendarUnknown(Exception):
    pass


@dataclass(frozen=True)
class TradingCalendar:
    version: str
    covers_from: date
    covers_to: date
    closed: frozenset
    half_days: frozenset

    @staticmethod
    def load(path: Path | None = None) -> "TradingCalendar":
        p = path or Path(__file__).resolve().parent / "config" / "calendar_us_2026.json"
        j = json.loads(p.read_text(encoding="utf-8"))
        return TradingCalendar(j["version"], date.fromisoformat(j["covers_from"]), date.fromisoformat(j["covers_to"]),
                               frozenset(map(date.fromisoformat, j["closed"])), frozenset(map(date.fromisoformat, j["half_days"])))

    def _check(self, d: date):
        if not (self.covers_from <= d <= self.covers_to):
            raise CalendarUnknown(f"{d} 超出日历 {self.version} 覆盖范围，不猜测")

    def is_trading_day(self, d: date) -> bool:
        self._check(d)
        return d.weekday() < 5 and d not in self.closed

    def trading_days_between(self, a: date, b: date) -> int:
        """(a, b] 内的交易日数。"""
        self._check(a); self._check(b)
        n, d = 0, a
        while d < b:
            d += timedelta(days=1)
            n += self.is_trading_day(d)
        return n


def strict_cutoff(d: date) -> datetime:
    """strict 截止：D 后一个自然日纽约 12:00，返回 UTC（自动处理夏令时）。"""
    return datetime.combine(d + timedelta(days=1), time(12, 0), tzinfo=NY).astimezone(timezone.utc)
