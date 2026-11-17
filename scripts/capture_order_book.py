"""Collect SSI quote snapshots on a one-second grid during a HOSE session."""

import json
import os
import re
import time
from datetime import datetime, time as clock_time, timedelta
from decimal import Decimal, InvalidOperation
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.ssi_stream import DataStream, VN
from scripts.market_store import archive_book, publish, redis
from src.ssi_client import SSIReadonly
from src.depth_watch import source_sample, source_window


def full_book(quote):
    try:
        return all(len(quote[side]) >= 3 and all(
            value.is_finite() and value > 0 for level in quote[side][:3]
            for value in map(lambda item: Decimal(str(item)), level)
        ) for side in ("bids", "asks"))
    except (InvalidOperation, TypeError):
        return False


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
    session = os.environ.get("SSI_CAPTURE_SESSION", "morning")
    windows = {"morning":(clock_time(9), clock_time(11, 30)),
               "afternoon":(clock_time(13), clock_time(14, 45))}
    opens, closes = windows[session]
    earliest = clock_time(6) if session == "morning" else clock_time(11, 30)
    if now.time() < earliest:
        raise SystemExit(f"Start {session} at or after {earliest:%H:%M} ICT.")
    deadline = datetime.combine(now.date(), closes, VN)
    if now >= deadline:
        print(f"SSI {session}: session has ended; no capture.", flush=True)
        return
    capture_session(symbols, now.date(), opens, deadline, session)


def capture_session(symbols, day, opens, deadline, session):
    start = datetime.combine(day, opens, VN)
    connect_at = start - timedelta(minutes=3)
    while datetime.now(VN) < connect_at:
        time.sleep(min(30, max(0, (connect_at - datetime.now(VN)).total_seconds())))
    if datetime.now(VN) >= deadline:
        raise SystemExit("The selected capture session ended before collection started.")
    now = datetime.now(VN)


    folder = Path("data/order_book_capture")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (now.strftime("%Y%m%dT%H%M%S%f") + ".jsonl")
    stream = DataStream()
    stream.watch_groups["book"] = set(symbols)
    stream.start()
    if stream.thread is None:
        raise SystemExit("SSI stream did not start. Check the configured credentials.")
    counts = dict.fromkeys(symbols, 0)
    observed = Counter()
    published_books = {}
    session_books = {}
    publish_live = os.environ.get("SSI_PUBLISH_LIVE") == "true"
    if publish_live:
        try:
            previous = json.loads(redis(["GET", "liquiditylab:live"]) or "{}")
            published_books = previous.get("last_books", {})
        except Exception as error:
            print(f"Previous SSI snapshot not loaded: {type(error).__name__}", flush=True)
        print("Publishing SSI snapshots throughout the session.", flush=True)
    last_publish = 0.0
    recent = {symbol: deque(maxlen=300) for symbol in symbols}
    depth_rows = {symbol: deque(maxlen=361) for symbol in symbols}
    publisher = ThreadPoolExecutor(max_workers=1) if publish_live else None
    pending = None
    checkpoint = None
    saved_at = float("-inf")

    def save_books(sampled, books):
        date_key = day.isoformat()
        snapshot = {"date": date_key, "updated_at": sampled.isoformat(), "last_books": books}
        key = f"book-archive:{date_key}:{session}:{path.stem}:{sampled:%H%M%S%f}"
        archive_book(key, snapshot)
        previous = json.loads(redis(["GET", "liquiditylab:book-" + session]) or "{}")
        if previous.get("date") == date_key:
            latest = dict(previous.get("last_books", {}))
            for symbol, book in books.items():
                if book["quote_time"] >= latest.get(symbol, {}).get("quote_time", ""):
                    latest[symbol] = book
            snapshot["last_books"] = latest
        publish("book-" + session, snapshot)

    try:
        while datetime.now(VN) < start:
            time.sleep(min(5, max(0, (start - datetime.now(VN)).total_seconds())))
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
                    rooms = {symbol: stream.rooms.get(symbol) for symbol in symbols}
                website_rows = []
                for symbol, quote in quotes.items():
                    status = "no_quote"
                    levels = False
                    if quote is not None:
                        event = datetime.fromisoformat(quote["event_time"])
                        received = datetime.fromisoformat(quote["received_at"])
                        if state != "connected_unverified":
                            status = "disconnected"
                        elif not all(0 <= (sampled - t).total_seconds() <= 5 for t in (event, received)):
                            status = "stale_quote"
                        elif not quote["bids"] or not quote["asks"]:
                            status = "incomplete_book"
                        else:
                            levels = True
                            verified = (flag == "LO" and flag_time is not None and
                                        flag_time.date() == sampled.date() and event >= flag_time)
                            status = "fresh_two_sided_quote" if verified else "session_unverified"
                            counts[symbol] += 1
                            if publish_live and full_book(quote):
                                entry = {
                                    "bids": quote["bids"], "asks": quote["asks"],
                                    "quote_time": quote["event_time"], "received_at": quote["received_at"],
                                    "session": flag, "status": status, "capture_session": session,
                                }
                                published_books[symbol] = session_books[symbol] = entry
                    observed[status] += 1
                    minute = sampled.hour * 60 + sampled.minute
                    if publish_live and (555 <= minute < 690 or 780 <= minute < 870):
                        session_id = f"{day}:{session}:{epoch}"
                        depth_rows[symbol].append(source_sample(symbol, sampled, session_id, quote if levels else None))
                    trade = trades[symbol] or {}
                    trade_data = trade.get("data", {})
                    room = rooms[symbol] or {}
                    room_data = room.get("data", {})
                    points = recent[symbol]
                    event_time = trade.get("event_time")
                    price = trade_data.get("p")
                    if event_time and price and (not points or points[-1] != [event_time, price]):
                        points.append([event_time, price])
                    website_rows.append({
                        "symbol":symbol, "session":flag, "status":status,
                        "metrics":stream.book(symbol) if publish_live and status == "fresh_two_sided_quote" else None,
                        "quote_time":quote["event_time"] if quote else None,
                        "received_at":quote["received_at"] if quote else None,
                        "trade_time":trade.get("event_time"),
                        "room_time":room.get("event_time"),
                        "foreign_buy":room_data.get("bq"),"foreign_sell":room_data.get("sq"),
                        "foreign_room":room_data.get("cr"),
                        "bids":quote["bids"] if levels else [],
                        "asks":quote["asks"] if levels else [],
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
                        "last_books":dict(published_books),
                        "depth_windows":{symbol:source_window(list(rows)) for symbol,rows in depth_rows.items() if rows},
                        "recent_trades":{symbol:list(points) for symbol,points in recent.items()},
                    })
                if publisher and session_books and time.monotonic() - saved_at >= 900:
                    if checkpoint is None or checkpoint.done():
                        if checkpoint and checkpoint.exception():
                            print(f"SSI archive failed: {type(checkpoint.exception()).__name__}", flush=True)
                        saved_at = time.monotonic()
                        checkpoint = publisher.submit(save_books, sampled, dict(session_books))
    finally:
        stream.stop()
        if publisher:
            publisher.shutdown()
    if publish_live and session_books:
        save_books(datetime.now(VN), session_books)
    if pending:
        pending.result()
    print("Fresh two-sided quote samples:", counts, "| Raw records dropped:", stream.dropped)
    print("Sample states:", dict(observed), "| SSI stream:", stream.status(), flush=True)
    missing = [symbol for symbol, count in counts.items() if not count]
    if missing or stream.dropped:
        print("::warning::Incomplete SSI coverage. Missing symbols: " + ",".join(missing), flush=True)
    if len(missing) == len(symbols):
        raise SystemExit("Incomplete SSI capture. Review the local session files.")


if __name__ == "__main__":
    main()
