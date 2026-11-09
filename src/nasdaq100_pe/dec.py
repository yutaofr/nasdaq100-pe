"""十进制政策：34位有效数字、half-even；拒绝 NaN/Infinity/非字符串。"""
from __future__ import annotations

import re
from decimal import Context, Decimal, DivisionByZero, InvalidOperation, Overflow, ROUND_HALF_EVEN

CTX = Context(prec=34, rounding=ROUND_HALF_EVEN, traps=[InvalidOperation, DivisionByZero, Overflow])
_RE = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$")
ZERO, ONE = Decimal(0), Decimal(1)


class BadDecimal(ValueError):
    pass


def D(s) -> Decimal:
    if not isinstance(s, str) or not _RE.match(s):
        raise BadDecimal(f"not a finite decimal string: {s!r}")
    return CTX.create_decimal(s)


def dstr(d: Decimal | None) -> str | None:
    if d is None:
        return None
    s = format(d, "f")
    return s


def add(a, b): return CTX.add(a, b)
def sub(a, b): return CTX.subtract(a, b)
def mul(a, b): return CTX.multiply(a, b)
def div(a, b): return CTX.divide(a, b)


def dsum(xs) -> Decimal:
    t = ZERO
    for x in xs:
        t = CTX.add(t, x)
    return t
