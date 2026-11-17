"""Incrementally publish closed HOSE candles derived from SSI minute bars."""
import os
import time
from datetime import datetime, timedelta
from decimal import Decimal

import json
from scripts.market_store import publish, redis
from scripts.market_universe import BASE_INTRADAY, report_requests, request, select_symbols, stored
from src.intraday import aggregate, normalize
from src.ssi_client import SSIReadonly, safe_error
from src.ssi_stream import VN

WINDOWS = ((555, 690), (780, 870))
RESOLUTIONS = {"15m":15, "1h":60, "4h":240}
ADDITIONAL_INDEXES = {"VN30":"VN30", "HNXINDEX":"HNXINDEX", "UPCOMINDEX":"HNXUPCOMINDEX"}
SUMMARY_FIELDS = {
    "last_price":"close", "total_volume":"totalMatch", "high":"high", "low":"low",
    "foreign_buy":"totalForeignBuy", "foreign_sell":"totalForeignSell", "foreign_room":"remainForeignRoom",
    "change":"priceChange", "change_pct":"priceChangePercentage",
}


def closed_candles(rows, resolution, now):
    result = []
    for row in aggregate(rows, resolution):
        start = datetime.fromisoformat(row["timestamp"])
        minute = start.hour * 60 + start.minute
        end_minute = next(end for begin, end in WINDOWS if begin <= minute < end)
        length = min(RESOLUTIONS[resolution], end_minute - minute)
        end = start + timedelta(minutes=length)
        if end <= now:
            result.append({**row, "closed_at":end.isoformat(), "session_minutes":length,
                           "partial":row["observed_minutes"] < length})
    return result


def fetch_minutes(client, symbol, start, now):
    raw = []
    previous = None
    for page in range(1, 12):
        params = {"symbol":symbol, "timeFrame":"1m", "from":start.strftime("%Y/%m/%d %H:%M:%S"),
                  "to":now.strftime("%Y/%m/%d %H:%M:%S"), "pageIndex":page, "pageSize":1000}
        response = request(client.get, "/api/v3/data/ohlc", params)
        items = response.get("data")
        if items is None and str(response.get("code")) == "204":
            items = []
        if not isinstance(items, list) or int(response.get("pageIndex") or page) != page:
            raise ValueError("Unexpected SSI minute page")
        if items and items == previous:
            raise ValueError("SSI minute pagination repeated")
        previous = items
        raw.extend(items)
        pages = response.get("pagesCount") or response.get("pageCount")
        if not items or (pages and page >= int(pages)) or (not pages and len(items) < 1000):
            break
    else:
        raise ValueError("SSI minute pagination incomplete")
    rows = normalize(raw, symbol)
    for row in rows:
        ts = datetime.fromisoformat(row["timestamp"])
        if not start <= ts <= now or ts.second or ts.microsecond:
            raise ValueError("SSI minute timestamp outside request or off grid")
    return rows


def merge_candles(previous, recent, cutoff):
    result = {}
    for resolution in RESOLUTIONS:
        merged = {row["timestamp"]:row for row in previous.get(resolution, [])
                  if row["timestamp"] >= cutoff}
        for row in recent[resolution]:
            key = row["timestamp"]
            old = merged.get(key)
            if not old or row["observed_minutes"] >= old["observed_minutes"]:
                merged[key] = row
        result[resolution] = [merged[key] for key in sorted(merged)]
    return result


def update_indexes_and_board(client, now):
    day = now.date().isoformat()
    provider_day = now.strftime("%Y/%m/%d")
    try:
        summary = request(client.get, "/api/v3/data/securitiesSummary",
                          {"index":"VN30", "from":provider_day, "to":provider_day,
                           "pageIndex":1, "pageSize":100})
        items = summary.get("data") if isinstance(summary, dict) else summary
    except Exception as error:
        print(f"SSI securitiesSummary unavailable: {safe_error(error)}", flush=True)
        items = []
    rows = {}
    for row in items or []:
        symbol = row.get("symbol")
        if not symbol or str(row.get("tradingDate"))[:10].replace("/", "-") != day:
            continue
        rows[symbol] = {key:row[field] for key, field in SUMMARY_FIELDS.items()
                        if row.get(field) not in (None, "")}
    print(f"SSI securitiesSummary {day}: {len(rows)} symbols", flush=True)
    catalog = stored("catalog", {})
    members = catalog.get("index_memberships", {}).get("VN30", [])
    if members:
        raw_series = redis(["MGET", *("liquiditylab:intraday:"+symbol for symbol in members)])
        for symbol, raw in zip(members, raw_series):
            candles = json.loads(raw or "{}").get("candles", {}).get("15m", [])
            today = [row for row in candles if row["timestamp"].startswith(day)]
            if not today:
                continue
            record = rows.setdefault(symbol, {})
            record.update(observed_volume=str(sum(Decimal(bar["volume"]) for bar in today)),
                          observed_high=str(max(Decimal(bar["high"]) for bar in today)),
                          observed_low=str(min(Decimal(bar["low"]) for bar in today)),
                          candle_time=today[-1]["closed_at"])
    previous_summary = stored("board-summary", {})
    if previous_summary.get("date") == day:
        rows = {symbol:{**previous_summary.get("rows", {}).get(symbol, {}), **rows.get(symbol, {})}
                for symbol in previous_summary.get("rows", {}).keys() | rows.keys()}
    if rows:
        publish("board-summary", {"date":day, "retrieved_at":now.isoformat(), "rows":rows})
    failures = []
    for symbol, provider in ADDITIONAL_INDEXES.items():
        try:
            previous = stored("intraday:"+symbol, {})
            candles = previous.get("candles", {})
            first = now.replace(hour=0, minute=0, second=0, microsecond=0)
            minutes = fetch_minutes(client, provider, first, now)
            recent = {key:closed_candles(minutes, key, now) for key in RESOLUTIONS}
            if recent["15m"]:
                cutoff = (now - timedelta(days=24)).date().isoformat()
                merged = merge_candles(candles, recent, cutoff)
                if candles != merged:
                    publish("intraday:"+symbol, {"source":"SSI FastConnect V3 1m OHLCV",
                                                 "updated_at":now.isoformat(), "candles":merged})
                print(f"{symbol}: latest closed {merged['15m'][-1]['closed_at']}", flush=True)
            else:
                print(f"{symbol}: SSI returned no closed 15-minute candles for {day}", flush=True)
        except Exception as error:
            print(f"{symbol}: not updated ({safe_error(error)})", flush=True)
            failures.append(symbol)
    if failures:
        raise ValueError("Failed SSI index series: " + ",".join(failures))


def update(client, now):
    catalog = stored("catalog")
    if not catalog:
        raise ValueError("Run SSI Market History once to refresh the SSI directory")
    selected, metadata = select_symbols(catalog, "SSI_INTRADAY_SYMBOLS", BASE_INTRADAY)
    symbols = [s for s in selected if metadata.get(s, {}).get("board") == "HOSE"]
    cap = int(os.environ.get("SSI_INTRADAY_MAX_SYMBOLS", "32"))
    batch = int(os.environ.get("SSI_INTRADAY_BACKFILL_BATCH", "8"))
    if not 3 <= cap <= 40 or not 1 <= batch <= cap:
        raise ValueError("Invalid SSI intraday limits")
    symbols = ["VNINDEX", *symbols[:cap - 1]]
    cutoff = (now - timedelta(days=24)).date().isoformat()
    event = os.environ.get("GITHUB_EVENT_NAME")
    # Later scheduled runs only process their latest completed trading date. Manual
    # runs and the first run for a symbol seed up to 24 calendar days.
    legacy = stored("intraday", {})
    coverage = stored("intraday-coverage", {})
    entries = dict(coverage.get("symbols", {}))
    failures = []
    total_bytes = 0
    for symbol in symbols:
        entry = entries.get(symbol)
        if not entry and batch == 0 and symbol != "VNINDEX":
            continue
        if not entry and symbol != "VNINDEX":
            batch -= 1
        previous = stored("intraday:"+symbol)
        candles = (previous or {}).get("candles", legacy.get("symbols", {}).get(symbol, {}))
        start = cutoff
        if entry and (event == "schedule" or os.getenv("SSI_INTRADAY_INCREMENTAL") == "true"):
            last = datetime.fromisoformat(entry["last"]).date()
            start = max(cutoff, last.isoformat())
        first = datetime.fromisoformat(start).replace(tzinfo=VN)
        try:
            rows = fetch_minutes(client, symbol, first, now)
            recent = {key:closed_candles(rows, key, now) for key in RESOLUTIONS}
            if not recent["15m"]:
                continue
            merged = merge_candles(candles, recent, cutoff)
        except Exception as error:
            print(f"{symbol}: not updated ({safe_error(error)})", flush=True)
            failures.append(symbol)
            continue
        last = merged["15m"][-1]["closed_at"]
        if not previous or candles != merged:
            total_bytes += publish("intraday:"+symbol, {"source":"SSI FastConnect V3 1m OHLCV",
                                "updated_at":now.isoformat(), "candles":merged})
        latest_session = [row for row in merged["15m"] if row["timestamp"][:10] == last[:10]]
        entries[symbol] = {
            "last":last, "sessions":len({row["timestamp"][:10] for row in merged["15m"]}),
            "session_volume":str(sum(Decimal(row["volume"]) for row in latest_session)),
            "observed_minutes":sum(row["observed_minutes"] for row in latest_session),
            "expected_minutes":sum(row["session_minutes"] for row in latest_session),
        }
        print(f"{symbol}: {entries[symbol]['sessions']} sessions, latest closed {last}", flush=True)

    if entries != coverage.get("symbols", {}):
        publish("intraday-coverage", {"updated_at":now.isoformat(), "symbols":entries})
    print(f"Intraday coverage: {len(entries)} equities; updates stored={total_bytes} bytes", flush=True)
    if failures:
        raise ValueError("Failed SSI intraday series: " + ",".join(failures))
    if not entries:
        raise ValueError("No closed SSI intraday bars available")


def main():
    start = time.monotonic()
    client = None
    try:
        client = SSIReadonly()
        client.authenticate()
        updater = update_indexes_and_board if os.getenv("SSI_INTRADAY_INDEX_BOARD") == "true" else update
        updater(client, datetime.now(VN))
    except Exception as error:
        diagnostic = str(error) if isinstance(error, ValueError) else safe_error(error)
        raise SystemExit(f"SSI intraday refresh failed: {diagnostic}") from None
    finally:
        if client:
            report_requests(client, start)
            client.close()


if __name__ == "__main__":
    main()
