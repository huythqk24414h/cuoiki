"""Refresh closed SSI candles at market-time checkpoints."""

import os
import subprocess
import sys
import time
from datetime import datetime, time as clock, timedelta

from scripts.publish_intraday import VN


def session_ticks(day, delay_minutes=0):
    # Allow two minutes for the source to publish each closed candle.
    slots = [(9, 32), (9, 47)]
    slots += [(hour, minute) for hour in (10, 13) for minute in (2, 17, 32, 47)]
    slots += [(11, minute) for minute in (2, 17, 32)]
    slots += [(14, minute) for minute in (2, 17, 32)]
    if delay_minutes:
        slots.extend([(9, 17), (14, 47), (15, 2)])
    delay = timedelta(minutes=delay_minutes)
    return sorted(datetime.combine(day, clock(h, m), VN) + delay for h, m in slots)


def main():
    command = [sys.executable, "-m", "scripts.publish_intraday"]
    if os.getenv("SSI_INTRADAY_FOLLOW_SESSION") != "true":
        return subprocess.call(command, timeout=480)

    now = datetime.now(VN)
    if now.weekday() >= 5:
        print("Weekend: no scheduled intraday collection.", flush=True)
        return 0
    if now.time() < clock(9):
        print("Session refresh starts at 09:32 ICT.", flush=True)
        return 0

    env = {**os.environ, "SSI_INTRADAY_INCREMENTAL": "true"}
    delay = 1 if os.getenv("SSI_INTRADAY_INDEX_BOARD") == "true" else 0
    failures = 0
    while True:
        print(f"Refresh at {datetime.now(VN).isoformat()}", flush=True)
        try:
            failures += subprocess.call(command, env=env, timeout=480) != 0
        except subprocess.TimeoutExpired:
            print("Refresh timeout; continuing at the next checkpoint.", flush=True)
            failures += 1
        now = datetime.now(VN)
        pending = [tick for tick in session_ticks(now.date(), delay) if tick > now]
        if not pending:
            break
        print(f"Next refresh: {pending[0].isoformat()}", flush=True)
        time.sleep((pending[0] - now).total_seconds())
    print(f"Failed refreshes: {failures}", flush=True)
    return int(failures > 0)


if __name__ == "__main__":
    sys.exit(main())
