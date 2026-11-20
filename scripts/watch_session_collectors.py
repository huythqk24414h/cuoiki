"""Keep chart collectors running alongside the SSI capture session."""
import os
import time
from datetime import datetime, time as clock
from scripts.reconcile_collectors import VN, reconcile


def main():
    now = datetime.now(VN)
    if now.weekday() >= 5:
        return
    session = os.getenv("SSI_WATCH_SESSION") or ("morning" if now.hour < 12 else "afternoon")
    deadline = datetime.combine(now.date(), clock(11,35) if session == "morning" else clock(15,10), VN)
    print("Watching SSI collectors until", deadline.isoformat(), flush=True)
    while datetime.now(VN) < deadline:
        now = datetime.now(VN)
        if now.time() >= clock(9,17):
            try:
                reconcile(now)
            except Exception as error:
                print("Collector check failed; retrying:", type(error).__name__, flush=True)
        for _ in range(3):
            if datetime.now(VN) >= deadline:
                return
            time.sleep(60)


if __name__ == "__main__":
    main()
