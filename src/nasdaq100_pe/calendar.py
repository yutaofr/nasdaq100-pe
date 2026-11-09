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
    def _one(p: Path) -> "TradingCalendar":
        j = json.loads(p.read_text(encoding="utf-8"))
        return TradingCalendar(j["version"], date.fromisoformat(j["covers_from"]), date.fromisoformat(j["covers_to"]),
                               frozenset(map(date.fromisoformat, j["closed"])), frozenset(map(date.fromisoformat, j["half_days"])))

    @staticmethod
    def load(path: Path | None = None) -> "TradingCalendar":
        """未指定文件时合并 config/ 下全部 calendar_us_*.json（新增年份只需加文件）。"""
        if path is not None:
            return TradingCalendar._one(Path(path))
        return TradingCalendar.load_dir(Path(__file__).resolve().parent / "config")

    @staticmethod
    def load_dir(d: Path) -> "TradingCalendar":
        cals = [TradingCalendar._one(p) for p in sorted(Path(d).glob("calendar_us_*.json"))]
        if not cals:
            raise FileNotFoundError("无交易日历文件")
        return TradingCalendar("+".join(c.version for c in cals), min(c.covers_from for c in cals), max(c.covers_to for c in cals),
                               frozenset().union(*(c.closed for c in cals)), frozenset().union(*(c.half_days for c in cals)))

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
