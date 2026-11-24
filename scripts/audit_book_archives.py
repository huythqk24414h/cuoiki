"""Audit preserved SSI archives by date, capture session and symbol."""

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import gzip
from hashlib import file_digest
import json
from pathlib import Path


VN = timezone(timedelta(hours=7))
WINDOWS = {"morning": (9 * 3600 + 15 * 60, 11 * 3600 + 30 * 60),
           "afternoon": (13 * 3600, 14 * 3600 + 30 * 60)}


def longest_missing(observed, start, end):
    edges = [start - 1, *sorted(observed), end]
    return max(right - left - 1 for left, right in zip(edges, edges[1:]))


def audit(folder):
    captures = defaultdict(lambda: defaultdict(list))
    checkpoints = Counter()
    seen = set()
    for manifest_path in sorted(folder.rglob("*-manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        day = date.fromisoformat(manifest["date"]).isoformat()
        session = manifest["session"]
        for entry in manifest["files"]:
            name = entry["file"]
            if Path(name).name != name or "\\" in name:
                raise ValueError("Invalid archive member name")
            path = manifest_path.with_name(name)
            with path.open("rb") as source:
                digest = file_digest(source, "sha256").hexdigest()
            if digest != entry["sha256"]:
                raise ValueError(f"Checksum mismatch: {path}")
            key = day, session, digest
            if key in seen:
                continue
            seen.add(key)
            if name.endswith(".json.gz"):
                checkpoints[day] += 1
            if session not in WINDOWS or not name.endswith(".jsonl.gz") or "-order_book_capture-" not in name:
                continue
            start, end = WINDOWS[session]
            with gzip.open(path, "rt", encoding="utf-8") as source:
                for line in source:
                    row = json.loads(line)
                    stamp = datetime.fromisoformat(row["sampled_at"])
                    if stamp.utcoffset() is None or stamp.astimezone(VN).date().isoformat() != day:
                        raise ValueError(f"Sample timestamp outside manifest day: {path}")
                    stamp = stamp.astimezone(VN)
                    second = stamp.hour * 3600 + stamp.minute * 60 + stamp.second
                    symbol_rows = captures[day, session][row["symbol"]]
                    if start <= second < end:
                        symbol_rows.append((second, row["status"]))

    sessions = []
    for (day, session), symbols in sorted(captures.items()):
        start, end = WINDOWS[session]
        rows = []
        for symbol, samples in sorted(symbols.items()):
            by_second = defaultdict(set)
            for second, status in samples:
                by_second[second].add(status)
            fresh = sum(states == {"fresh_two_sided_quote"} for states in by_second.values())
            status_counts = Counter(next(iter(states)) if len(states) == 1 else "conflicting_samples"
                                    for states in by_second.values())
            rows.append({"symbol": symbol, "expected_seconds": end-start,
                         "sample_rows": len(samples), "observed_seconds": len(by_second),
                         "fresh_session_flag_seconds": fresh,
                         "missing_seconds": end-start-len(by_second),
                         "longest_missing_seconds": longest_missing(by_second, start, end),
                         "status_seconds": dict(status_counts)})
        sessions.append({"date": day, "session": session, "symbols": rows})
    return {"checkpoint_files_by_day": dict(checkpoints), "sessions": sessions,
            "note": "Collector flags measure observed coverage. SSI units and eligibility for model evaluation require separate verification."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", nargs="?", type=Path, default=Path("data/research_exports"))
    print(json.dumps(audit(parser.parse_args().folder), ensure_ascii=False, indent=2))
