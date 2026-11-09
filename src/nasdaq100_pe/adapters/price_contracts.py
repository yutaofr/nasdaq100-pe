"""认证价格供应商的离线请求契约（契约通过 ≠ 供应商实接通过）。"""
from __future__ import annotations

from datetime import date
from typing import Sequence


def build_request_params(vendor: str, target: date, symbols: Sequence[str], **override) -> dict:
    if vendor == "alpaca":
        feed = override.get("feed", "sip")
        adjustment = override.get("adjustment", "raw")
        if feed != "sip" or adjustment != "raw":
            raise ValueError("Alpaca 须使用 SIP 与 raw；不自动以 IEX 或 adjusted 代替")
        return {"symbols": ",".join(symbols), "timeframe": "1Day", "start": target.isoformat(), "end": target.isoformat(),
                "feed": "sip", "adjustment": "raw"}
    if vendor == "massive":
        if override.get("adjusted", "false") not in ("false", False) or override.get("adjusted") is True:
            raise ValueError("Massive 须使用 adjusted=false")
        return {"tickers": ",".join(symbols), "date": target.isoformat(), "adjusted": "false"}
    raise ValueError(f"未知或未认证的价格供应商: {vendor}")
