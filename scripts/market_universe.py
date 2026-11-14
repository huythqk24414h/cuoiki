"""Refresh SSI's current equity directory and select a bounded collection universe."""
import json
import os
import re
import time
from datetime import date, datetime

from scripts.market_store import publish, redis
from src.ssi_client import safe_error
from src.ssi_stream import VN

BOARDS = ("HOSE", "HNX", "UPCOM")
BASE_DAILY = ("SSI", "HPG", "FPT", "REE", "SAM")
BASE_INTRADAY = ("SSI", "FPT", "HPG")
SYMBOL = re.compile(r"[A-Z0-9]{1,12}")
RETRYABLE = {429, 500, 502, 503, 504}


def stored(key, fallback=None):
    value = redis(["GET", "liquiditylab:" + key])
    return json.loads(value) if value is not None else fallback


def request(call, *args, **kwargs):
    for attempt in range(4):
        try:
            return call(*args, **kwargs)
        except Exception as error:
            status = safe_error(error)["http_status"]
            if attempt == 3 or status not in RETRYABLE:
                raise
            delay = (15 if status == 429 else 2) * 2**attempt
            retry_after = getattr(error, "retry_after_ms", None)
            if retry_after is not None:
                if retry_after > 120_000:
                    raise
                delay = max(delay, retry_after / 1000)
            time.sleep(delay)


def metadata_date(value):
    if not value:
        return None
    return date.fromisoformat(str(value)[:10].replace("/", "-")).isoformat()


def directory(client, now, previous):
    current = {}
    index = set()
    for field, value in [("board", board) for board in BOARDS] + [("index", "VN30")]:
        rows = request(client.get, "/api/v3/data/securitiesByBoard", {field: value})
        if not isinstance(rows, list) or not rows:
            raise ValueError("SSI returned an empty or invalid directory")
        securities = [row for row in rows if row.get("stockType") == "Stock"
                      and SYMBOL.fullmatch(str(row.get("symbol", "")))]
        if not securities:
            raise ValueError("SSI directory contains no equities")
        for row in securities:
            symbol = row["symbol"]
            if field == "index":
                index.add(symbol)
                continue
            item = {key: row.get(key) for key in ("symbol", "symbolNameVi", "symbolNameEn", "stockType")}
            item.update(board=value, status="listed",
                        firstTradingDate=metadata_date(row.get("firstTradingDate")),
                        lastTradingDate=metadata_date(row.get("lastTradingDate")))
            if item["lastTradingDate"] and item["lastTradingDate"] < now.date().isoformat():
                item["status"] = "ended"
            if item["firstTradingDate"] and item["firstTradingDate"] > now.date().isoformat():
                item["status"] = "pending"
            if symbol in current and current[symbol]["board"] != value:
                # SSI sometimes returns aliases for transferred symbols. Keep the board
                # explicitly identified by SSI, and fail if both boards claim the record.
                if row.get("board") != value:
                    continue
                raise ValueError(f"SSI directory lists {symbol} on multiple boards")
            current[symbol] = item
    if len(index) != 30 or not index <= current.keys() or any(current[s]["board"] != "HOSE" for s in index):
        raise ValueError("SSI returned inconsistent VN30 membership")
    for row in previous.get("securities", []):
        current.setdefault(row["symbol"], {**row, "status":"absent" if row["status"] != "ended" else "ended"})
    return {"source":"SSI FastConnect V3", "updated_at":now.isoformat(),
            "securities":sorted(current.values(), key=lambda row: row["symbol"]),
            "index_memberships":{"VN30":sorted(index)}}


def refresh_directory(client, now):
    previous = stored("catalog", {})
    result = directory(client, now, previous)
    count = sum(row["status"] == "listed" for row in result["securities"])
    print(f"SSI catalogue: {count} listed equities, 30 VN30 constituents.", flush=True)
    if any(previous.get(key) != result[key] for key in ("securities", "index_memberships")):
        publish("catalog", result)
        return result
    return previous


def select_symbols(catalog, variable, base):
    rows = {row["symbol"]: row for row in catalog["securities"]}
    requested = [value.strip().upper() for value in os.environ.get(variable, "VN30").split(",") if value.strip()]
    result = list(base)
    for value in requested:
        group = catalog["index_memberships"].get(value)
        if group is None and value not in rows:
            raise ValueError(f"Unknown SSI symbol or group in {variable}")
        result.extend(group if group is not None else [value])
    return [symbol for symbol in dict.fromkeys(result)
            if symbol not in rows or rows[symbol]["status"] == "listed"], rows


def report_requests(client, start):
    entries = client.evidence
    limits = sorted({row["x-ratelimit-limit"] for row in entries if "x-ratelimit-limit" in row})
    print(f"SSI HTTP requests={len(entries)} limits={limits} elapsed_s={time.monotonic()-start:.1f}", flush=True)
