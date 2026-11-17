"""Append SSI daily observations newer than the static archive."""
import json
from datetime import date, timedelta
from pathlib import Path

from scripts.market_store import redis
from scripts.market_universe import SYMBOL

ROOT = Path(__file__).resolve().parents[1]
KEY = "liquiditylab:market-eod-updates"
START = date(2022, 1, 1)
FIELDS = ("date", "open_vnd", "high_vnd", "low_vnd", "close_vnd", "volume_shares")


def update(client, end, directory, already_published, fetch):
    manifest = ROOT / "demo/eod-archive-catalog.json"
    if not manifest.exists():
        return
    archive = json.loads(manifest.read_bytes())
    # Continue collecting current equities and retain history for inactive instruments.
    active = [row["symbol"] for row in directory["securities"] if row["status"] == "listed"]
    pending = [s for s in sorted(set(active) - set(already_published)) if SYMBOL.fullmatch(s)]
    failures = []
    for symbol in pending:
        try:
            old = json.loads(redis(["HGET", KEY, symbol]) or '{"rows":[]}')
            if old.get("rows") and old["rows"][-1][0] >= end.isoformat():
                continue
            anchor = archive.get(symbol, {}).get("last")
            start = date.fromisoformat(anchor) + timedelta(days=1) if anchor else START
            known = {row[0]:row for row in old["rows"]}
            query_from = max(start, date.fromisoformat(old["checked_through"]) - timedelta(days=7)) if old.get("checked_through") else start
            fresh = fetch(client, symbol, query_from, end, set()) if query_from <= end else {}
            known.update({day:[row[key] for key in FIELDS] for day,row in fresh.items()})
            checked_through = max(known, default=anchor or "")
            if not checked_through:
                continue
            payload = json.dumps({"checked_through":checked_through,"rows":[known[day] for day in sorted(known)]},separators=(",",":"))
            if redis(["HSET", KEY, symbol, payload]) not in (0, 1):
                raise RuntimeError("Redis delta write was not acknowledged")
        except Exception as error:
            failures.append(symbol)
            print(f"{symbol}: market archive refresh {type(error).__name__}", flush=True)
    print(f"Market archive refresh through {end}: {len(pending)-len(failures)}/{len(pending)} equity checks passed", flush=True)
    if failures:
        raise RuntimeError(f"{len(failures)} market history refreshes failed")
