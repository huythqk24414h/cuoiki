"""Refresh verified SSI minute bars and publish closed HOSE candles."""
import json
import os
import re
import time
from datetime import datetime, timedelta

from scripts.market_store import publish, redis
from src.intraday import aggregate, normalize
from src.ssi_client import SSIReadonly, safe_error
from src.ssi_stream import VN

WINDOWS = ((555, 690), (780, 870))


def closed_candles(rows, resolution, now):
    width = {"15m": 15, "1h": 60, "4h": 240}[resolution]
    result = []
    for row in aggregate(rows, resolution):
        start = datetime.fromisoformat(row["timestamp"])
        minute = start.hour * 60 + start.minute
        end_minute = next(end for begin, end in WINDOWS if begin <= minute < end)
        length = min(width, end_minute - minute)
        end = start + timedelta(minutes=length)
        if end <= now:
            result.append({**row, "closed_at":end.isoformat(), "session_minutes":length,
                           "partial":row["observed_minutes"] < length})
    return result


def fetch_minutes(client, symbol, now):
    start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    raw = []
    for page in range(1, 12):
        params = {"symbol":symbol,"timeFrame":"1m","from":start.strftime("%Y/%m/%d %H:%M:%S"),
                  "to":now.strftime("%Y/%m/%d %H:%M:%S"),"pageIndex":page,"pageSize":1000}
        for attempt in range(3):
            try:
                response = client.get("/api/v3/data/ohlc", params)
                break
            except Exception as error:
                status = safe_error(error)["http_status"]
                if attempt == 2 or status not in (None, 429, 500, 502, 503, 504):
                    raise
                time.sleep(5 * 2**attempt)
        items = response.get("data")
        if not isinstance(items,list):
            raise ValueError("Unexpected SSI minute response")
        raw.extend(items)
        pages = response.get("pagesCount") or response.get("pageCount")
        if not items or (pages and page >= int(pages)) or (not pages and len(items)<1000):
            break
    else:
        raise ValueError("SSI minute pagination incomplete")
    rows = normalize(raw,symbol)
    if any(not start <= datetime.fromisoformat(row["timestamp"]) <= now for row in rows):
        raise ValueError("SSI minute timestamp outside request")
    if any(datetime.fromisoformat(row["timestamp"]).second or datetime.fromisoformat(row["timestamp"]).microsecond for row in rows):
        raise ValueError("SSI bar off the minute grid")
    return rows


def main():
    symbols = sorted({item.strip().upper() for item in os.environ.get("SSI_INTRADAY_SYMBOLS","SSI,FPT,HPG").split(",")})
    if not 1 <= len(symbols) <= 10 or not all(re.fullmatch(r"[A-Z0-9]{1,12}",s) for s in symbols):
        raise SystemExit("Invalid SSI_INTRADAY_SYMBOLS")
    now = datetime.now(VN)
    client = None
    data = {}
    try:
        client = SSIReadonly()
        client.authenticate()
        for symbol in symbols:
            rows = fetch_minutes(client,symbol,now)
            candles = {key:closed_candles(rows,key,now) for key in ("15m","1h","4h")}
            if not candles["15m"]:
                raise ValueError("No closed SSI bars for "+symbol)
            data[symbol] = candles
            print(symbol,len(rows),candles["15m"][-1]["timestamp"],flush=True)
        current = json.loads(redis(["GET", "liquiditylab:intraday"]) or "{}")
        if current.get("symbols") == data:
            print("No changed closed SSI candles. Keeping the published snapshot timestamp.", flush=True)
            return
        publish("intraday",{"source":"SSI FastConnect V3 1m OHLCV","updated_at":now.isoformat(),"symbols":data})
    except Exception as error:
        diagnostic = str(error) if isinstance(error, ValueError) else safe_error(error)
        raise SystemExit(f"SSI intraday refresh failed: {diagnostic}") from None
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    main()

