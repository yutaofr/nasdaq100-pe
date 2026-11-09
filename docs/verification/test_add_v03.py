import tempfile
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

from add_v03 import (
    capture_slots, forecast_subset, import_prices, parse_holdings, research_basket_age,
    sequence_key, source_state, ttm_check_fresh, weekly_observations,
)

NY = ZoneInfo("America/New_York")
D = date(2026, 11, 6)
CLOSE = datetime(2026, 11, 6, 16, tzinfo=NY)
HOLDINGS = """Ticker,Company,Share/ Par,% TNA,Class of shares,CUSIP,Market value
DEMO,Demo,1,70%,Common Stock,000000001,$1
TEST,Test,1,29%,American Depository Receipt,000000002,$1
CASH,Cash,1,--,Currency,--,$1

# as of 2026-11-06
"""


class DataRules(unittest.TestCase):
    def test_source_wait_and_cutoff(self):
        slots = capture_slots(CLOSE)
        self.assertEqual([s.strftime("%m-%d %H:%M") for s in slots],
                         ["11-06 17:30", "11-06 19:00", "11-06 22:00",
                          "11-07 00:15", "11-07 06:15", "11-07 11:15"])
        half_day = CLOSE.replace(hour=13)
        self.assertEqual(capture_slots(half_day)[3:], slots[3:])
        available = slots[3].replace(minute=0)
        cutoff = slots[-1].replace(hour=12, minute=0)
        self.assertEqual(source_state(CLOSE, slots[2], available), "waiting_source")
        self.assertEqual(source_state(CLOSE, slots[3], available), "due")
        self.assertEqual(source_state(CLOSE, cutoff, available), "due")
        self.assertEqual(source_state(CLOSE, cutoff + timedelta(seconds=1), available), "missed_window")

    def test_official_export_requires_date_and_distinct_ids(self):
        basket = parse_holdings(HOLDINGS)
        self.assertEqual(basket["weight_date"], D)
        self.assertEqual(basket["securities"], {"000000001": "DEMO", "000000002": "TEST"})
        self.assertEqual(basket["equity_weight_pct"], Decimal(99))
        self.assertIsNone(basket["total_excluded_weight_pct"])
        for bad in (HOLDINGS.replace("# as of 2026-11-06", ""),
                    HOLDINGS.replace("000000002", "000000001"),
                    HOLDINGS.replace("Common Stock", "Unknown")):
            with self.assertRaises(ValueError):
                parse_holdings(bad)

    def test_price_import_provenance_and_boundaries(self):
        with tempfile.TemporaryDirectory() as path:
            directory = Path(path)
            raw = b"synthetic original object"
            (directory / "source.csv").write_bytes(raw)
            bundle = {
                "data_mode": "synthetic", "source": "demo",
                "target_date": D.isoformat(), "observed_at": capture_slots(CLOSE)[3].isoformat(),
                "raw_file": "source.csv", "sha256": sha256(raw).hexdigest(),
            }
            securities = parse_holdings(HOLDINGS)
            first = {"security_id": "000000001", "ticker": "DEMO", "price_date": D.isoformat(),
                     "close": "11.25", "currency": "USD", "price_type": "regular_close",
                     "split_basis_date": D.isoformat(), "trading_status": "traded",
                     "source_locator": "row 2", "identity_evidence": "row 2 CUSIP",
                     "split_evidence": "fixture split check"}
            second = {**first, "security_id": "000000002", "ticker": "TEST"}
            bundle["prices"] = [first, second]
            result = import_prices(bundle, securities, CLOSE, directory)
            self.assertEqual(result["status"], "structurally_valid")
            self.assertFalse(result["formal_snapshot_eligible"])
            for update in ({"price_type": "after_hours"}, {"price_type": "implied_holding_mark"},
                           {"close": "NaN"}, {"currency": "EUR"}, {"split_evidence": ""},
                           {"split_basis_date": "2026-11-05"}, {"trading_status": "halted"}):
                result = import_prices({**bundle, "prices": [{**first, **update}, second]},
                                       securities, CLOSE, directory)
                self.assertEqual(result["status"], "invalid_rows")
            self.assertEqual(import_prices({**bundle, "prices": [first]}, securities, CLOSE, directory)["missing"],
                             ["000000002"])
            self.assertEqual(import_prices({**bundle, "prices": [first, first, second]}, securities,
                                           CLOSE, directory)["status"], "invalid_rows")
            self.assertEqual(import_prices({**bundle, "observed_at": "2026-11-07T12:00:01-05:00"},
                                           securities, CLOSE, directory)["status"], "missed_window")
            self.assertEqual(import_prices({**bundle, "sha256": "0" * 64}, securities, CLOSE,
                                           directory)["status"], "invalid_evidence")

            for contract in ({"source": "alpaca_sip", "feed": "sip", "adjustment": "raw"},
                             {"source": "massive", "adjusted": False,
                              "close_mapping_evidence": "fixture daily summary cross-check"}):
                valid = {**bundle, **contract}
                self.assertEqual(import_prices(valid, securities, CLOSE, directory)["status"],
                                 "structurally_valid")
            for contract in ({"source": "alpaca_sip", "feed": "iex", "adjustment": "raw"},
                             {"source": "alpaca_sip", "feed": "sip", "adjustment": "split"},
                             {"source": "massive", "adjusted": False}):
                self.assertEqual(import_prices({**bundle, **contract}, securities, CLOSE,
                                               directory)["status"], "invalid_source_contract")

    def test_fixed_basket_counts_trading_days(self):
        sessions = [date(2026, 11, d) for d in (5, 6, 9, 10, 11, 12, 13)]
        self.assertEqual(research_basket_age(sessions[0], sessions[5], sessions), 5)
        self.assertIsNone(research_basket_age(sessions[0], sessions[6], sessions))
        self.assertIsNone(research_basket_age(sessions[5], sessions[0], sessions))

    def test_subset_has_denominator_and_keeps_negative(self):
        self.assertIsNone(forecast_subset(None, {"A": Decimal("0.2")}))
        self.assertIsNone(forecast_subset({"A": Decimal("0.6")}, {"A": Decimal("0.2")}))
        self.assertIsNone(forecast_subset({"A": Decimal("1.1"), "B": Decimal("-0.1")},
                                          {"A": Decimal("0.2")}))
        weights = {"A": Decimal("0.6"), "B": Decimal("0.4")}
        self.assertEqual(forecast_subset(weights, {"A": Decimal("-0.1")}),
                         (Decimal("0.6"), Decimal("-0.1"), None))
        self.assertEqual(forecast_subset(weights, {"A": Decimal(0)}),
                         (Decimal("0.6"), Decimal(0), None))
        self.assertEqual(forecast_subset(weights, {"A": Decimal("0.1")})[2], Decimal(10))

    def test_weekly_observation_and_revision_limits(self):
        end = datetime(2026, 11, 13, 11, tzinfo=NY)
        old = end - timedelta(days=7)
        self.assertTrue(weekly_observations([old, end], [end.date() - timedelta(days=30), None], end))
        self.assertFalse(weekly_observations([old - timedelta(days=1), end], [None, None], end))
        self.assertFalse(weekly_observations([old, end], [end.date() - timedelta(days=31), None], end))

    def test_method_history_and_freshness_isolation(self):
        strict = sequence_key("v1", "strict", "current", "full", "daily")
        for settings in (("fixed", "full", "daily"), ("current", "subset", "daily"),
                         ("current", "full", "weekly")):
            self.assertNotEqual(strict, sequence_key("v1", "research", *settings))
            with self.assertRaises(ValueError):
                sequence_key("v1", "strict", *settings)
        stale = CLOSE - timedelta(hours=24)
        self.assertFalse(ttm_check_fresh(stale, CLOSE, online_recheck=False))
        self.assertTrue(ttm_check_fresh(CLOSE, CLOSE, online_recheck=True))
        self.assertFalse(ttm_check_fresh(stale, CLOSE, online_recheck=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
