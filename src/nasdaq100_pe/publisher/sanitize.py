from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|passwd)\b\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{6,}"),
    re.compile(r"Traceback \(most recent call"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
]


def scan_for_secrets(text: str, *, forbidden: tuple[str, ...] = ()) -> list[str]:
    """返回命中描述（不含命中内容本身）。forbidden 为不得出现的子串（如 DATA_ROOT）。"""
    hits = [f"pattern:{i}" for i, p in enumerate(_PATTERNS) if p.search(text)]
    hits += [f"forbidden:{i}" for i, s in enumerate(forbidden) if s and s in text]
    return hits
