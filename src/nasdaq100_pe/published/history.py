from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nasdaq100_pe.archive.store import ArchiveStore

SERIES_FIELDS = ("provider", "instrument", "metric_label_original", "metric_kind", "period_basis",
                 "accounting_basis", "loss_treatment", "data_mode")


def series_key(o: dict) -> str:
    """来源、原名、口径、真实/演示任一改变都产生新序列；不拼接。"""
    return "|".join(str(o.get(f, "")).replace("|", "/") for f in SERIES_FIELDS)


def list_observations(key: str, store: "ArchiveStore") -> list[dict]:
    return [o for o in store.all_observations() if series_key(o) == key]
