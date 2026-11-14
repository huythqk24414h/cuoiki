"""Publish a complete batch of SSI closing prices for the browser demo."""
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

from src.finance import number
from src.ssi_client import SSIReadonly, safe_error
from src.ssi_stream import VN

OUTPUT = Path(__file__).resolve().parents[1] / "demo/prices.json"


def load_batch(client, symbols, session):
    start = session - timedelta(days=10)
    rows = []
    for symbol in symbols:
        response = client.ohlc(
            symbol, f"{start}T00:00:00+07:00", f"{session}T23:59:59+07:00", size=30,
        )
        by_date = {}
        for item in response["data"]:
            date = datetime.strptime(item["tradingDate"][:10], "%Y/%m/%d").date()
            if item["symbol"] != symbol or not start <= date <= session:
                raise ValueError("Unexpected SSI symbol or session")
            values = {key: number(item[key]) for key in ("close", "high", "low", "volume")}
            if not 0 < values["low"] <= values["close"] <= values["high"]:
                raise ValueError("Invalid SSI closing price")
            row = {"symbol": symbol, "date": date.isoformat(), **{k: str(v) for k, v in values.items()}}
            if date in by_date and by_date[date] != row:
                raise ValueError("Conflicting duplicate SSI session")
            by_date[date] = row
        # Never publish a partial batch or present the prior session as current.
        if session not in by_date:
            raise ValueError("No closing bar for the requested session")
        rows.append(by_date[session])
    return rows


def main():
    symbols = sorted({s.strip().upper() for s in os.environ.get("SSI_EOD_SYMBOLS", "SSI,HPG,FPT").split(",")})
    if len(symbols) > 30 or any(not re.fullmatch(r"[A-Z0-9]{1,12}", symbol) for symbol in symbols):
        raise SystemExit("SSI_EOD_SYMBOLS must contain 1–30 comma-separated stock symbols.")
    now = datetime.now(VN)
    if now.weekday() >= 5 or now.hour < 16:
        print("Closing price refresh runs after 16:00 Vietnam time on weekdays.")
        return
    client = None
    try:
        client = SSIReadonly()
        client.authenticate()
        rows = load_batch(client, symbols, now.date())
    except Exception as error:
        raise SystemExit(f"SSI refresh failed. Prior snapshot retained. {safe_error(error)}") from None
    finally:
        if client:
            client.close()
    previous = json.loads(OUTPUT.read_text(encoding="utf-8"))
    if previous.get("source") == "SSI FastConnect" and previous.get("rows") == rows:
        return
    snapshot = {"source": "SSI FastConnect", "updated_at": datetime.now(VN).isoformat(), "rows": rows}
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(f"Validated {len(rows)} closing bars for {now.date()}.")


if __name__ == "__main__":
    main()
