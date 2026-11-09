"""Offline evidence intake and reference checks for ADD v0.3, not an estimator."""
import argparse
import csv
import io
import json
import re
from collections import Counter
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation, localcontext
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
EQUITY_TYPES = {"Common Stock", "American Depository Receipt",
                "American Depository Receipt - NY"}
EXCLUDED_TYPES = {"Currency", "Index Future", "Currency Collateral", "Synthetic Cash"}
MAX_INPUT = 20 * 1024 * 1024


def capture_slots(close):
    close = close.astimezone(NY)
    next_day = close.date() + timedelta(days=1)
    return tuple(close + timedelta(minutes=minutes) for minutes in (90, 180, 360)) + tuple(
        datetime.combine(next_day, time(hour, 15), NY) for hour in (0, 6, 11))


def source_state(close, observed, available):
    day = close.astimezone(NY).date()
    cutoff = datetime.combine(day + timedelta(days=1), time(12), NY)
    if observed > cutoff:
        return "missed_window"
    if observed < close:
        return "before_close"
    return "waiting_source" if observed < available else "due"


def decimal_text(value):
    if not isinstance(value, str):
        raise ValueError("amount must be decimal text")
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("invalid decimal amount") from error
    if not number.is_finite():
        raise ValueError("nonfinite amount")
    return number


def parse_holdings(text):
    lines = text.removeprefix("\ufeff").splitlines()
    dates = [line.strip()[8:] for line in lines if line.strip().startswith("# as of ")]
    if len(dates) != 1:
        raise ValueError("expected one holdings as-of date")
    fields = {"Ticker", "% TNA", "Class of shares", "CUSIP"}
    reader = csv.DictReader(io.StringIO("\n".join(
        line for line in lines if line.strip() and not line.startswith("#"))), strict=True)
    if not fields <= set(reader.fieldnames or []):
        raise ValueError("missing holdings columns")
    securities, stock, excluded = {}, [], []
    for row in reader:
        if None in row or any(row[key] is None for key in fields):
            raise ValueError("invalid holdings row")
        kind, symbol, identity = (row[key].strip() for key in ("Class of shares", "Ticker", "CUSIP"))
        raw = row["% TNA"].strip()
        if raw == "--":
            value = None
        elif raw.endswith("%"):
            value = decimal_text(raw[:-1])
        else:
            raise ValueError("weight must be a percentage or --")
        if kind in EQUITY_TYPES:
            if (not symbol or symbol == "--" or not re.fullmatch(r"[A-Z0-9]{9}", identity)
                    or identity in securities or symbol in securities.values() or value is None
                    or value < 0):
                raise ValueError("invalid equity identity or weight")
            securities[identity] = symbol
            stock.append(value)
        elif kind in EXCLUDED_TYPES:
            excluded.append(value)
        else:
            raise ValueError("unknown asset class")
    total = sum(stock)
    if not stock or total <= 0:
        raise ValueError("no positive equity weight")
    known_excluded = sum(value for value in excluded if value is not None)
    return {"weight_date": date.fromisoformat(dates[0]), "rows": len(stock) + len(excluded),
            "securities": securities, "equity_weight_pct": total,
            "known_excluded_weight_pct": known_excluded,
            "unknown_excluded_count": excluded.count(None),
            "total_excluded_weight_pct": None if None in excluded else known_excluded}


def aware_timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("timestamp requires an offset")
    return parsed


def verified_file(directory, name, digest):
    if not isinstance(name, str) or Path(name).is_absolute():
        return False
    directory = directory.resolve()
    file = (directory / name).resolve()
    return (file.is_relative_to(directory) and file.is_file()
            and file.stat().st_size <= MAX_INPUT and sha256(file.read_bytes()).hexdigest() == digest)


def import_prices(bundle, basket, close, directory):
    """Check declared evidence and consistency. A separate reviewer verifies the source semantics."""
    def result(status, **detail):
        return {"status": status, "formal_snapshot_eligible": False, **detail}

    target = close.astimezone(NY).date()
    if bundle.get("target_date") != target.isoformat() or basket["weight_date"] != target:
        return result("date_mismatch")
    try:
        observed = aware_timestamp(bundle["observed_at"])
    except (KeyError, TypeError, ValueError):
        return result("invalid_evidence")
    state = source_state(close, observed, close)
    if state != "due":
        return result(state)
    if (bundle.get("data_mode") not in {"real", "synthetic"}
            or not isinstance(bundle.get("source"), str) or not bundle["source"].strip()
            or not verified_file(directory, bundle.get("raw_file"), bundle.get("sha256"))):
        return result("invalid_evidence")
    source = bundle["source"]
    if source == "alpaca_sip" and (bundle.get("feed"), bundle.get("adjustment")) != ("sip", "raw"):
        return result("invalid_source_contract")
    if source == "massive" and (bundle.get("adjusted") is not False
                                or not bundle.get("close_mapping_evidence")):
        return result("invalid_source_contract")
    prices = bundle.get("prices")
    if not isinstance(prices, list) or any(not isinstance(row, dict) for row in prices):
        return result("invalid_rows")

    known = basket["securities"]
    counts = Counter(row.get("security_id") for row in prices if isinstance(row.get("security_id"), str))
    missing = sorted(known.keys() - counts.keys())
    issues = []
    for position, row in enumerate(prices, start=1):
        identity = row.get("security_id")
        evidence = ("source_locator", "identity_evidence", "split_evidence")
        try:
            amount = decimal_text(row.get("close"))
        except ValueError:
            amount = Decimal(0)
        if (not isinstance(identity, str) or identity not in known or counts[identity] != 1
                or row.get("ticker") != known[identity] or amount <= 0
                or row.get("price_date") != target.isoformat() or row.get("currency") != "USD"
                or row.get("price_type") != "regular_close" or row.get("trading_status") != "traded"
                or row.get("split_basis_date") != target.isoformat()
                or any(not isinstance(row.get(key), str) or not row[key].strip() for key in evidence)):
            issues.append(position)
    return result("invalid_rows" if missing or issues else "structurally_valid",
                  expected=len(known), missing=missing, invalid_rows=issues)


def research_basket_age(weight_day, price_day, verified_sessions):
    if weight_day not in verified_sessions or price_day not in verified_sessions:
        return None
    age = verified_sessions.index(price_day) - verified_sessions.index(weight_day)
    return age if 0 <= age <= 5 else None


def forecast_subset(full_weights, yields):
    if not full_weights or yields.keys() - full_weights.keys():
        return None
    with localcontext(prec=34):
        if (any(not weight.is_finite() or weight < 0 for weight in full_weights.values())
                or abs(sum(full_weights.values()) - Decimal(1)) > Decimal("1e-30")):
            return None
        coverage = sum(full_weights[key] for key in yields)
        if coverage <= 0:
            return None
        known_contribution = sum(full_weights[key] * value for key, value in yields.items())
        return coverage, known_contribution / coverage, (
            coverage / known_contribution if known_contribution > 0 else None)


def weekly_observations(observed, revisions, cutoff):
    if not observed or len(observed) != len(revisions):
        return False
    last_day = cutoff.astimezone(NY).date()
    for time_observed, revised in zip(observed, revisions, strict=True):
        age = (last_day - time_observed.astimezone(NY).date()).days
        if time_observed > cutoff or age > 7 or (revised and not 0 <= (last_day - revised).days <= 30):
            return False
    return True


def sequence_key(version, profile, basket, coverage, freshness):
    if (profile not in {"strict", "research"} or basket not in {"current", "fixed"}
            or coverage not in {"full", "subset"} or freshness not in {"daily", "weekly"}
            or (profile == "strict" and (basket, coverage, freshness) != ("current", "full", "daily"))):
        raise ValueError("invalid mode")
    return version, profile, basket, coverage, freshness


def ttm_check_fresh(checked_at, cutoff, *, online_recheck):
    return online_recheck and timedelta(0) <= cutoff - checked_at < timedelta(hours=24)


def read_input(path):
    if path.stat().st_size > MAX_INPUT:
        raise ValueError("input exceeds 20 MiB")
    return path.read_bytes()


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("holdings_csv", type=Path)
    cli.add_argument("--close", type=aware_timestamp, required=True, help="actual target close with offset")
    cli.add_argument("--observed-at", type=aware_timestamp, required=True, help="holdings observation time")
    cli.add_argument("--prices", type=Path, help="normalized JSON price evidence, no network requests")
    args = cli.parse_args()
    try:
        holdings = read_input(args.holdings_csv)
        basket = parse_holdings(holdings.decode("utf-8-sig"))
        target = args.close.astimezone(NY).date()
        window = source_state(args.close, args.observed_at, args.close)
        digest = sha256(holdings).hexdigest()
        if args.prices:
            bundle = json.loads(read_input(args.prices))
            if not isinstance(bundle, dict):
                raise ValueError("price evidence must be a JSON object")
            result = import_prices(bundle, basket, args.close, args.prices.parent)
        else:
            result = {key: value for key, value in basket.items() if key != "securities"}
            result["equity_count"] = len(basket["securities"])
        result.update(target_date=target, holdings_sha256=digest, holdings_observed_at=args.observed_at,
                      holdings_window=window, holdings_same_day=basket["weight_date"] == target)
        print(json.dumps(result, default=str, indent=2))
        if args.prices and (result["status"] != "structurally_valid" or window != "due"):
            return 2
    except (OSError, ValueError, csv.Error) as error:
        cli.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
