from __future__ import annotations

import json
from dataclasses import dataclass, field

from nasdaq100_pe.dec import BadDecimal, D
from nasdaq100_pe.identity.models import SecurityIdentity, Universe
from nasdaq100_pe.method import MethodSpec
from nasdaq100_pe.validate.basket import BasketResult, validate_basket

MAX_BYTES = 20 * 1024 * 1024
_REQ = ("schema_version", "method_version", "universe", "weights", "sources")


@dataclass
class InputValidation:
    ok: bool
    exit_code: int
    diagnostics: list[dict] = field(default_factory=list)
    universe: Universe | None = None
    basket: BasketResult | None = None
    sources: dict = field(default_factory=dict)
    prices: list[dict] = field(default_factory=list)
    earnings: list[dict] = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    layers: dict = field(default_factory=lambda: {"raw_evidence": False, "normalized": False, "semantic_ok": False, "date_ok": None})


def _fail(code: int, path: str, msg: str) -> InputValidation:
    return InputValidation(False, code, [{"code": "INPUT_ERROR", "path": path, "message": msg}])


def _reject_const(n):
    raise ValueError(n)


def validate_research_input(payload: bytes, policy: MethodSpec) -> InputValidation:
    if len(payload) > MAX_BYTES:
        return _fail(2, "$", "超过20MiB")
    try:
        data = json.loads(payload.decode("utf-8"), parse_constant=_reject_const)
    except (UnicodeDecodeError, ValueError):
        return _fail(2, "$", "无法解析为UTF-8 JSON（含NaN/Infinity）")
    if not isinstance(data, dict) or any(k not in data for k in _REQ):
        return _fail(2, "$", f"缺少必需字段 {[k for k in _REQ if k not in (data or {})]}")

    sources = {s["source_id"]: s for s in data["sources"] if isinstance(s, dict) and "source_id" in s}
    u = data["universe"]
    try:
        secs = [SecurityIdentity(
            security_id=s["security_id"], issuer_id=s["issuer_id"], share_class=s["share_class"], ticker=s["ticker"],
            name=s.get("name", ""), sector=s.get("sector"), sector_source=s.get("sector_source"), cusip=s.get("cusip"),
            is_adr=bool(s.get("is_adr", False)), adr_ratio=s.get("adr_ratio"), ticker_history=tuple(s.get("ticker_history", ())))
            for s in u["securities"]]
    except (KeyError, TypeError) as e:
        return _fail(2, "universe.securities", f"缺少字段 {e}")
    for i, s in enumerate(u["securities"]):
        if s.get("asset_class") != "equity":
            return _fail(4, f"universe.securities[{i}].asset_class", "名单只接受 equity；非股票放入 weights.excluded")
    # 完整性只认证据：listing_scope=full 且来源可核；单独的 complete=true 不算
    complete = u.get("listing_scope") == "full" and u.get("source_id") in sources
    uni = Universe(as_of=u.get("as_of", ""), source_id=u.get("source_id", ""), listing_scope=u.get("listing_scope", "unknown"),
                   securities=secs, complete=complete)

    basket = validate_basket(uni, data["weights"], policy)
    diags = list(basket.diagnostics)
    res = InputValidation(ok=not basket.structural_error, exit_code=4 if basket.structural_error else 0, diagnostics=diags,
                          universe=uni, basket=basket, sources=sources, raw=data)
    res.layers["raw_evidence"] = bool(sources)
    if basket.structural_error:
        return res
    res.layers["normalized"] = True
    res.layers["semantic_ok"] = basket.qualified

    ids = {s.security_id for s in secs}
    for i, p in enumerate(data.get("prices", [])):
        try:
            if p["security_id"] not in ids or D(p["close"]) <= 0:
                raise BadDecimal("price")
            res.prices.append(p)
        except (KeyError, BadDecimal, TypeError):
            diags.append({"code": "BAD_PRICE_ROW", "path": f"prices[{i}]", "message": "价格行无效，已排除"})
    for i, e in enumerate(data.get("earnings", [])):
        try:
            if e["security_id"] not in ids or e["kind"] not in ("ttm", "fy1"):
                raise BadDecimal("earnings")
            D(e["eps"])
            for req in ("accounting_basis", "currency"):
                if req not in e:
                    raise KeyError(req)
            res.earnings.append(e)
        except (KeyError, BadDecimal, TypeError):
            diags.append({"code": "BAD_EARNINGS_ROW", "path": f"earnings[{i}]", "message": "盈利行无效，保留诊断，不进入对应指标"})
    return res
