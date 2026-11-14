"""Backfill SSI daily bars, then refresh recent sessions in the external store."""
import json
import os
import re
from datetime import date, datetime, timedelta

from scripts.market_store import publish, redis
from src.eod_analytics import enrich_rows
from src.ssi_client import SSIReadonly, safe_error
from src.ssi_stream import VN
from src.universe import canonical_row

START = date(2000, 7, 28)
INDEX_CODES = {"VNINDEX": "VNINDEX", "VN30": "VN30", "HNXINDEX": "HNXINDEX",
               "UPCOMINDEX": "HNXUPCOMINDEX"}


def backfill(client, symbol, first, last):
    rows = {}
    chunk = first
    while chunk <= last:
        end = min(chunk + timedelta(days=365), last)
        # A calendar year has fewer than 500 trading days.
        response = client.ohlc(symbol, f"{chunk}T00:00:00+07:00", f"{end}T23:59:59+07:00", size=500)
        items = response.get("data") if isinstance(response, dict) else None
        if items is None and isinstance(response, dict) and str(response.get("code")) == "204":
            items = []
        if not isinstance(items, list):
            raise ValueError("Unexpected SSI OHLC response")
        if len(items) >= 500 or int(response.get("pagesCount") or response.get("pageCount") or 1) > 1:
            raise ValueError("Incomplete SSI page")
        for item in items:
            row = canonical_row(item, symbol, str(chunk), str(end))
            prior = rows.setdefault(row["date"], row)
            if prior != row:
                raise ValueError("Conflicting SSI records for one date")
        chunk = end + timedelta(days=1)
    return rows


def main():
    symbols = sorted({s.strip().upper() for s in os.environ.get("SSI_EOD_SYMBOLS", "SSI,HPG,FPT,REE,SAM").split(",")})
    if len(symbols) > 30 or any(not re.fullmatch(r"[A-Z0-9]{1,12}", symbol) or symbol in INDEX_CODES for symbol in symbols):
        raise ValueError("Invalid SSI_EOD_SYMBOLS")
    now = datetime.now(VN)
    end = now.date() if now.hour >= 16 else now.date() - timedelta(days=1)
    saved = json.loads(redis(["GET", "liquiditylab:history"]) or "{}")
    series = {}
    client = None
    try:
        client = SSIReadonly()
        client.authenticate()
        for symbol, provider in {**{s:s for s in symbols}, **INDEX_CODES}.items():
            old = json.loads(redis(["GET", saved["symbols"][symbol]["key"]]) or "[]") if os.environ.get("SSI_FULL_BACKFILL") != "true" and symbol in saved.get("symbols", {}) else []
            # Refresh enough recent days to recover missed scheduled runs.
            first = max(START, min(end, date.fromisoformat(old[-1]["date"])) - timedelta(days=10)) if old else START
            fresh = backfill(client, provider, first, end)
            combined = {row["date"]:row for row in old}
            combined.update(fresh)
            if not combined:
                print(f"{symbol}: SSI returned no bars.")
                continue
            ordered = [combined[day] for day in sorted(combined)]
            key = f"history:{now.strftime('%Y%m%d%H%M%S%f')}:{symbol}"
            fields = ("symbol","date","open_vnd","high_vnd","low_vnd","close_vnd","volume_shares",
                      "return_pct","volume_avg20_previous","relative_volume20","volatility20_pct",
                      "source_value_vnd","price_adjustment")
            publish(key, [{field: row[field] for field in fields} for row in enrich_rows(ordered)])
            series[symbol] = {"key":"liquiditylab:"+key,"first":ordered[0]["date"],
                              "last":ordered[-1]["date"],"count":len(ordered),
                              "close":{"symbol":symbol,"date":ordered[-1]["date"],
                                       **{k:ordered[-1][k+"_vnd"] for k in ("close","high","low")},
                                       "volume":ordered[-1]["volume_shares"]}}
            print(f"{symbol}: {len(ordered)} bars, {ordered[0]['date']} to {ordered[-1]['date']}", flush=True)
        if not any(symbol in series for symbol in symbols):
            raise ValueError("No equity history available")
        publish("history", {"source":"SSI FastConnect V3","updated_at":now.isoformat(),
                            "query_start":str(START),"indexes":list(INDEX_CODES),"symbols":series})
        obsolete = [entry["key"] for entry in saved.get("symbols", {}).values()]
        for key in obsolete:
            try:
                redis(["EXPIRE", key, 86400])
            except Exception:
                print("Previous series could not be scheduled for expiration.")
    except Exception as error:
        raise SystemExit(f"History update failed. Prior snapshot retained. {safe_error(error)}") from None
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    main()
