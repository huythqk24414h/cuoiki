"""Backfill paginated SSI daily bars and incrementally update the published directory."""
import json
import os
import time
from datetime import date, datetime, timedelta
from decimal import Decimal

from scripts.market_store import encode_value, publish, redis
from scripts.market_universe import (BASE_DAILY, refresh_directory, report_requests,
                                     request, select_symbols, stored)
from src.eod_analytics import enrich_rows
from src.ssi_client import SSIReadonly, safe_error
from src.ssi_stream import VN
from src.universe import canonical_row

START = date(2000, 7, 28)
# HOSE Notice of first trading day under Decision 317/QĐ-SGDHCM (2025-04-29).
# SSI's VPL response also contains a disconnected old listing from 2008–2011.
CURRENT_LISTING_START = {"VPL":date(2025, 5, 13)}
INDEX_CODES = {"VNINDEX":"VNINDEX", "VN30":"VN30", "HNXINDEX":"HNXINDEX",
               "UPCOMINDEX":"HNXUPCOMINDEX"}
FIELDS = ("symbol","date","open_vnd","high_vnd","low_vnd","close_vnd","volume_shares",
          "return_pct","volume_avg20_previous","relative_volume20","volatility20_pct",
          "source_value_vnd","price_adjustment","liquidation_days_100k_5pct")


def backfill(client, symbol, first, last, quarantined):
    rows = {}
    omitted = 0
    for page in range(1, 21):
        response = request(client.ohlc, symbol, f"{first}T00:00:00+07:00",
                           f"{last}T23:59:59+07:00", page=page, size=1000)
        items = response.get("data")
        if items is None and str(response.get("code")) == "204":
            items = []
        if not isinstance(items, list) or int(response.get("pageIndex") or page) != page:
            raise ValueError("Unexpected SSI OHLC page")
        dates = set()
        for item in items:
            day = str(item["tradingDate"])[:10].replace("/", "-")
            if item["symbol"] != symbol or not first <= date.fromisoformat(day) <= last:
                raise ValueError("SSI OHLC symbol/date outside request")
            dates.add(day)
            if symbol in INDEX_CODES.values():
                close = Decimal(str(item["close"]))
                if not close.is_finite() or close <= 0:
                    omitted += 1
                    continue
                row = dict.fromkeys(FIELDS)
                row.update(symbol=symbol, date=day, close_vnd=str(close), price_adjustment="unknown")
                try:
                    opening, high, low = (Decimal(str(item[key])) for key in ("open", "high", "low"))
                    if (all(value.is_finite() and value > 0 for value in (opening, high, low))
                            and low <= min(opening, close) <= max(opening, close) <= high):
                        row.update(open_vnd=str(opening), high_vnd=str(high), low_vnd=str(low))
                except (ArithmeticError, KeyError, TypeError, ValueError):
                    pass
            else:
                try:
                    row = canonical_row(item, symbol, str(first), str(last))
                except (ArithmeticError, KeyError, TypeError, ValueError):
                    quarantined.add(day)
                    continue
            prior = rows.setdefault(day, row)
            if prior != row:
                raise ValueError("Conflicting SSI bars for one date")
        if not dates:
            break
        if page > 1 and min(dates) >= oldest:
            raise ValueError("SSI daily pagination did not advance")
        oldest = min(dates)
        pages = response.get("pagesCount") or response.get("pageCount")
        if (pages and page >= int(pages)) or (not pages and len(items) < 1000):
            break
    else:
        raise ValueError("SSI daily pagination incomplete")
    if omitted:
        print(f"{symbol}: excluded {omitted} invalid index closes", flush=True)
    return rows


def prepare_symbol(client, symbol, provider, start, end, entry, full, refresh_index=False):
    old = []
    if entry:
        raw = redis(["GET", entry["key"]])
        if raw is None:
            raise RuntimeError("Stored series missing")
        old = json.loads(raw)
        if not old or old[-1]["date"] != entry["last"]:
            raise RuntimeError("Stored history does not match checkpoint")
    first = (max(start, min(end, date.fromisoformat(old[-1]["date"])) - timedelta(days=10))
             if old and not full and not refresh_index else start)
    if first > end:
        return old, old, entry.get("quarantined_dates", []) if entry else []
    combined = {} if full else {row["date"]: row for row in old if row["date"] >= start.isoformat()}
    rejected = set()
    fresh = backfill(client, provider, first, end, rejected)
    if symbol in INDEX_CODES:
        old_by_date = {row["date"]: row for row in old}
        for day, row in fresh.items():
            previous = old_by_date.get(day)
            if (previous and row["open_vnd"] is None
                    and Decimal(row["close_vnd"]) == Decimal(previous["close_vnd"])):
                row.update({key: previous.get(key) for key in ("open_vnd", "high_vnd", "low_vnd")})
    combined.update(fresh)
    if rejected:
        print(f"{symbol}: quarantined {len(rejected)} malformed OHLCV bars "
              f"({min(rejected)} to {max(rejected)})", flush=True)
    quarantined = sorted((set(entry.get("quarantined_dates", ())) | rejected) - combined.keys()) if entry else sorted(rejected)
    ordered = [dict(combined[day]) for day in sorted(combined)]
    if full and old and not {row["date"] for row in old if row["date"] >= start.isoformat()}.issubset(combined):
        raise ValueError("Full refresh would drop published dates")
    if symbol in INDEX_CODES:
        for row in ordered:
            row.setdefault("liquidation_days_100k_5pct", None)
        for previous, current in zip(ordered, ordered[1:]):
            current["return_pct"] = str((Decimal(current["close_vnd"])/Decimal(previous["close_vnd"])-1)*100)
    else:
        ordered = enrich_rows(ordered)
    return old, [{field: row[field] for field in FIELDS} for row in ordered], quarantined


def update(client, now):
    end = now.date() if now.hour >= 16 else now.date() - timedelta(days=1)
    saved = stored("history", {})
    series = dict(saved.get("symbols", {}))
    directory = refresh_directory(client, now)
    symbols, metadata = select_symbols(directory, "SSI_EOD_SYMBOLS", BASE_DAILY)
    full = os.environ.get("SSI_FULL_BACKFILL") == "true"
    index_only = os.environ.get("SSI_EOD_INDEX_ONLY") == "true"
    limit = int(os.environ.get("SSI_EOD_BACKFILL_BATCH", "8"))
    if not 1 <= limit <= 40 or len(symbols) > 80:
        raise ValueError("EOD limits: at most 80 configured equities and 1–40 new series per run")

    providers = INDEX_CODES if index_only else {**INDEX_CODES, **{s:s for s in symbols}}
    failures = []
    pending = limit
    for symbol, provider in providers.items():
        entry = series.get(symbol)
        if not entry:
            if pending == 0:
                continue
            pending -= 1
        first_trading = metadata.get(symbol, {}).get("firstTradingDate")
        start = max(date.fromisoformat(first_trading) if first_trading and not entry else START, CURRENT_LISTING_START.get(symbol, START))
        try:
            old, rows, quarantined = prepare_symbol(client, symbol, provider, start, end, entry, full,
                                                    refresh_index=index_only)
        except Exception as error:
            print(f"{symbol}: not updated ({safe_error(error)})", flush=True)
            failures.append(symbol)
            continue
        if not rows or (rows == old and quarantined == (entry or {}).get("quarantined_dates", [])):
            continue

        prior_bytes = sum(item.get("bytes", 3_000_000) for code, item in series.items() if code != symbol)
        if prior_bytes + len(encode_value(json.dumps(rows, separators=(",", ":"))).encode()) > 90_000_000:
            raise ValueError("Daily storage budget reached; review Upstash usage before adding more symbols")
        # Stage the new value before moving the pointer. A failed pointer update leaves an expiring key.
        key = f"history:{now.strftime('%Y%m%d%H%M%S%f')}:{symbol}"
        size = publish(key, rows, ttl=172800)
        latest = rows[-1]
        series[symbol] = {"key":"liquiditylab:"+key, "first":rows[0]["date"], "last":latest["date"],
                          "count":len(rows), "quarantined_dates":quarantined, "bytes":size, "revision":key.rsplit(":", 1)[0],
                          "close":{"symbol":symbol, "date":latest["date"],
                                   **{name:latest[name+"_vnd"] for name in ("close","high","low")},
                                   "volume":latest["volume_shares"]}}
        # Referenced data must remain available even if an older snapshot gets cleaned up.
        if redis(["PERSIST", "liquiditylab:"+key]) != 1:
            raise RuntimeError("Staged SSI history could not be persisted")
        try:
            publish("history", {"source":"SSI FastConnect V3", "updated_at":now.isoformat(),
                                "query_start":str(START), "indexes":list(INDEX_CODES), "symbols":series})
        except Exception:
            # The Redis server may have committed a write even if the response timed out.
            # Keep both series so whichever pointer is live can still be read.
            raise
        if entry:
            redis(["EXPIRE", entry["key"], 86400])
        print(f"{symbol}: {len(rows)} bars, {rows[0]['date']} to {latest['date']}; {size} bytes", flush=True)
    print(f"Daily coverage: {sum(symbol not in INDEX_CODES for symbol in series)} equities; "
          f"pending in configured universe: {sum(symbol not in series for symbol in symbols)}", flush=True)
    vn30 = directory.get("index_memberships", {}).get("VN30", [])
    official = series.get("VNINDEX", {}).get("last")
    if official:
        missing = [symbol for symbol in vn30 if series.get(symbol, {}).get("last") != official]
        print(f"SSI EOD {official}: {len(vn30) - len(missing)}/{len(vn30)} VN30 symbols", flush=True)
        if missing:
            print("::warning::VN30 EOD missing for " + official + ": " + ",".join(missing), flush=True)
        if now.weekday() < 5 and now.hour >= 16 and official < end.isoformat():
            print(f"::warning::SSI VNINDEX has not published EOD for {end}; last available {official}.", flush=True)
    if not index_only:
        from scripts.update_market_archive import update as update_archive
        update_archive(client, min(end, date.fromisoformat(official)) if official else end, directory, providers, backfill)
    if failures:
        raise ValueError("Failed SSI series: " + ",".join(failures))
    if not index_only and not any(symbol in series for symbol in symbols):
        raise ValueError("No equity history available")


def main():
    start = time.monotonic()
    client = None
    try:
        client = SSIReadonly()
        client.authenticate()
        update(client, datetime.now(VN))
    except Exception as error:
        diagnostic = str(error) if isinstance(error, ValueError) else safe_error(error)
        raise SystemExit(f"SSI history update failed: {diagnostic}") from None
    finally:
        if client:
            report_requests(client, start)
            client.close()


if __name__ == "__main__":
    main()
