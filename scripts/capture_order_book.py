"""Collect SSI quote snapshots on a one-second grid during a HOSE session."""

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from src.ssi_stream import DataStream, VN


def main():
    symbols = set(os.environ.get("CAPTURE_SYMBOLS", "SSI").split(","))
    symbols = sorted({symbol.strip().upper() for symbol in symbols})
    if len(symbols) > 10 or any(not re.fullmatch(r"[A-Z0-9]{1,12}", s) for s in symbols):
        raise SystemExit("Specify one to ten valid HOSE ticker symbols.")

    now = datetime.now(VN)
    minute = now.hour * 60 + now.minute
    windows = ((9 * 60, 11 * 60 + 30), (12 * 60 + 45, 14 * 60 + 30))
    end = next((end for start, end in windows if start <= minute < end), None)
    if now.weekday() >= 5 or end is None:
        print("Outside the configured capture windows (Vietnam time).")
        return
    deadline = now.replace(hour=end // 60, minute=end % 60, second=0, microsecond=0)

    folder = Path("data/order_book_capture")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (now.strftime("%Y%m%dT%H%M%S") + ".jsonl")
    stream = DataStream()
    stream.watch_groups["book"] = set(symbols)
    stream.start()
    if stream.thread is None:
        raise SystemExit("SSI stream did not start. Check the configured credentials.")
    counts = dict.fromkeys(symbols, 0)
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
                    output.write(json.dumps({
                        "sampled_at": sampled.isoformat(), "symbol": symbol,
                        "status": status, "session_flag": flag,
                        "session_flag_at": flag_time.isoformat() if flag_time else None,
                        "connection_epoch": epoch, "quote": quote,
                    }) + "\n")
    finally:
        stream.stop()
    print("Fresh two-sided quote samples:", counts, "| Raw records dropped:", stream.dropped)
    if not all(counts.values()) or stream.dropped:
        raise SystemExit("Incomplete SSI capture. Review the local session files.")


if __name__ == "__main__":
    main()
