from __future__ import annotations

from nasdaq100_pe.dec import ONE, ZERO, div, dsum

UNCLASSIFIED = "未分类"


def sector_results(rows, secs):
    from nasdaq100_pe.engine.core import SectorResult
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(r.security.sector or UNCLASSIFIED, []).append(r)
    out = []
    for name in sorted(groups):
        members = groups[name]
        sr = [secs[m.security.security_id] for m in members]
        W = dsum(s.weight for s in sr)
        valid = [s for s in sr if s.valid]
        Cs = dsum(s.weight for s in valid)
        Ks = dsum(s.contribution for s in valid)
        complete = len(valid) == len(sr)
        y = pe = None
        state, note = "incomplete", ""
        if W == ZERO:
            note = "行业权重为零"
        elif not complete:
            note = "行业盈利未全部有效，仅显示已知贡献"
        else:
            y = div(Ks, W)
            if y > 0:
                pe, state = div(ONE, y), "value"
            else:
                state = "non_positive"
        out.append(SectorResult(name, W, Cs, Ks, complete and W != ZERO, y, pe, state, note,
                                sorted(m.security.security_id for m in members)))
    return out
