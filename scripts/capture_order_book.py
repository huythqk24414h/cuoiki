"""Collect SSI quote snapshots on a one-second grid during a HOSE session."""

import json
import os
import re
import time
from datetime import datetime, time as clock_time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.ssi_stream import DataStream, VN
from scripts.market_store import publish
from src.ssi_client import SSIReadonly


def main():
    client = SSIReadonly()
    try:
        client.authenticate()
        rows = client.get("/api/v3/data/securitiesByBoard", {"index":"VN30"})
        symbols = sorted({row["symbol"] for row in rows})
    finally:
        client.close()
    if len(symbols) != 30 or any(not re.fullmatch(r"[A-Z0-9]{1,12}", s) for s in symbols):
        raise SystemExit("SSI did not return 30 valid VN30 constituents.")
    print("SSI VN30:", ",".join(symbols), flush=True)

    now = datetime.now(VN)
    if now.weekday() >= 5:
        print("Weekend in Vietnam. Select a trading day.")
        return
    if now.time() < clock_time(8, 55):
        raise SystemExit("Start at or after 08:55 ICT to fit the hosted runner time limit.")
    windows = ((clock_time(9), clock_time(11, 30)), (clock_time(13), clock_time(14, 45)))
    failures = []
    for opens, closes in windows:
        deadline = datetime.combine(now.date(), closes, VN)
        if datetime.now(VN) < deadline:
            try:
                capture_session(symbols, now.date(), opens, deadline)
            except SystemExit as error:
                failures.append(str(error))
    if failures:
        raise SystemExit("; ".join(failures))


def capture_session(symbols, day, opens, deadline):
    start = datetime.combine(day, opens, VN)
    if datetime.now(VN) < start:
        print(f"Waiting for the session at {start.isoformat()}.", flush=True)
        while datetime.now(VN) < start:
            time.sleep(min(30, max(0, (start - datetime.now(VN)).total_seconds())))
    if datetime.now(VN) >= deadline:
        raise SystemExit("The selected capture session ended before collection started.")
    now = datetime.now(VN)


    folder = Path("data/order_book_capture")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (now.strftime("%Y%m%dT%H%M%S") + ".jsonl")
    stream = DataStream()
    stream.watch_groups["book"] = set(symbols)
    stream.start()
    if stream.thread is None:
        raise SystemExit("SSI stream did not start. Check the configured credentials.")
    counts = dict.fromkeys(symbols, 0)
    publish_live = os.environ.get("SSI_PUBLISH_LIVE") == "true"
    last_publish = 0.0
    recent = {symbol: deque(maxlen=300) for symbol in symbols}
    publisher = ThreadPoolExecutor(max_workers=1) if publish_live else None
    pending = None
    try:
        with path.open("x", encoding="utf-8", buffering=1) as output:
            while datetime.now(VN) < deadline:
                time.sleep(max(0.01, 1 - time.time() % 1))
                sampled = datetime.now(VN)
                if sampled >= deadline:
                    break
                with stream.lock:
                    flag, flag_time = stream.flag, stream.flag_time
                    quotes = {symbol: stream.quotes.get(symbol) for symbol in symbols}
                    state, epoch = stream.state, stream.connection_epoch
                    trades = {symbol: stream.trades.get(symbol) for symbol in symbols}
                website_rows = []
                for symbol, quote in quotes.items():
                    status = "no_quote"
                    if quote is not None:
                        event = datetime.fromisoformat(quote["event_time"])
                        received = datetime.fromisoformat(quote["received_at"])
                        if state != "connected_unverified":
                            status = "disconnected"
                        elif not all(0 <= (sampled - t).total_seconds() <= 5 for t in (event, received)):
                            status = "stale_quote"
                        elif flag != "LO" or flag_time is None or flag_time.date() != sampled.date() or event < flag_time:
                            status = "session_unverified"
                        elif not quote["bids"] or not quote["asks"]:
                            status = "incomplete_book"
                        else:
                            status = "fresh_two_sided_quote"
                            counts[symbol] += 1
                    trade = trades[symbol] or {}
                    trade_data = trade.get("data", {})
                    points = recent[symbol]
                    event_time = trade.get("event_time")
                    price = trade_data.get("p")
                    if event_time and price and (not points or points[-1] != [event_time, price]):
                        points.append([event_time, price])
                    website_rows.append({
                        "symbol":symbol, "session":flag, "status":status,
                        "metrics":stream.book(symbol) if publish_live and status == "fresh_two_sided_quote" else None,
                        "quote_time":quote["event_time"] if quote else None,
                        "trade_time":trade.get("event_time"),
                        "bids":quote["bids"] if status == "fresh_two_sided_quote" else [],
                        "asks":quote["asks"] if status == "fresh_two_sided_quote" else [],
                        "last_price":trade_data.get("p"),
                        "last_quantity":trade_data.get("q"),
                        "total_volume":trade_data.get("v"),
                        "high":trade_data.get("h"),"low":trade_data.get("l"),
                    })
                    output.write(json.dumps({
                        "sampled_at": sampled.isoformat(), "symbol": symbol,
                        "status": status, "session_flag": flag,
                        "session_flag_at": flag_time.isoformat() if flag_time else None,
                        "connection_epoch": epoch, "quote": quote,
                    }) + "\n")
                if publisher and time.monotonic() - last_publish >= 3 and (pending is None or pending.done()):
                    if pending and pending.exception():
                        print(f"Live publish failed: {type(pending.exception()).__name__}", flush=True)
                    last_publish = time.monotonic()
                    pending = publisher.submit(publish, "live", {
                        "updated_at":sampled.isoformat(),"rows":website_rows,
                        "recent_trades":{symbol:list(points) for symbol,points in recent.items()},
                    })
    finally:
        stream.stop()
        if publisher:
            publisher.shutdown()
    if pending:
        pending.result()
    print("Fresh two-sided quote samples:", counts, "| Raw records dropped:", stream.dropped)
    if not all(counts.values()) or stream.dropped:
        raise SystemExit("Incomplete SSI capture. Review the local session files.")


if __name__ == "__main__":
    main()
