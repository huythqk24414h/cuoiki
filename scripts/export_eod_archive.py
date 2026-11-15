"""Export validated SSI daily OHLCV for a per-symbol static archive."""
import json
import re
import sys
from pathlib import Path

from src.history_store import active, rows
from src.universe import catalog

FIELDS = ("date","open_vnd","high_vnd","low_vnd","close_vnd","volume_shares")


def main(output):
    _, quality = active()
    if not quality:
        raise ValueError("No validated SSI snapshot")
    output.mkdir(parents=True, exist_ok=True)
    metadata = {r["symbol"]:r for r in catalog()["securities"]}
    directory = {}
    for symbol in sorted(quality["symbols_loaded"]):
        if not re.fullmatch(r"[A-Z0-9]{1,12}", symbol) or symbol not in metadata:
            continue
        observations = rows(symbol)
        if not observations:
            continue
        packed = [[row[field] for field in FIELDS] for row in observations]
        (output / f"{symbol}.json").write_text(json.dumps(packed,separators=(",",":")),encoding="utf-8")
        entry = metadata[symbol]
        directory[symbol] = {k:entry.get(k) for k in ("symbol","board","stockType","symbolNameVi","symbolNameEn")}
        directory[symbol].update(first=packed[0][0],last=packed[-1][0],count=len(packed))
    (output / "catalog.json").write_text(json.dumps(directory,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print(f"Archived {len(directory)} SSI symbols from {quality['first']} to {quality['last']}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
