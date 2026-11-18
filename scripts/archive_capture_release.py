"""Preserve SSI evidence as compressed release assets, outside the web database."""
import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from scripts.market_store import redis
from src.ssi_stream import VN


def package(source, target):
    with source.open("rb") as incoming, target.open("wb") as destination:
        with gzip.GzipFile(fileobj=destination, mode="wb", mtime=0) as compressed:
            shutil.copyfileobj(incoming, compressed)
    return {"file":target.name, "source_bytes":source.stat().st_size,
            "compressed_bytes":target.stat().st_size,
            "sha256":hashlib.file_digest(target.open("rb"), "sha256").hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(VN).date().isoformat())
    parser.add_argument("--checkpoints", action="store_true")
    args = parser.parse_args()
    day = date.fromisoformat(args.date).isoformat()
    run = os.getenv("GITHUB_RUN_ID", "local") + "-" + os.getenv("GITHUB_RUN_ATTEMPT", "1")
    session = os.getenv("SSI_CAPTURE_SESSION", "export")
    folder = Path("data/research_exports") / day / (run + "-" + session)
    folder.mkdir(parents=True, exist_ok=True)
    files = []
    manifest = {"date":day, "run":run, "session":session, "files":files,
                "source":"SSI", "created_at":datetime.now(VN).isoformat()}
    sources = []
    if args.checkpoints:
        keys = set()
        cursor = "0"
        while True:
            cursor, batch = redis(["SCAN", cursor, "MATCH", "liquiditylab:book-archive:"+day+":*", "COUNT", 100])
            keys.update(batch)
            if str(cursor) == "0":
                break
        keys.update("liquiditylab:book-"+part for part in ("morning", "afternoon"))
        for key in sorted(keys):
            raw = redis(["GET", key])
            if raw is None or json.loads(raw).get("date") != day:
                continue
            source = folder / (key.replace(":", "_") + ".json")
            source.write_text(raw, encoding="utf-8")
            sources.append(source)
        manifest["granularity"] = "Saved checkpoints only; continuous one-second samples are unavailable in this export."
    else:
        sources = sorted(Path("data/order_book_capture").glob("*.jsonl"))
        sources += sorted(Path("data/live_snapshots").glob(day+".jsonl"))
        manifest["granularity"] = "Captured one-second book samples and original SSI event logs. Coverage must be audited."
    for source in sources:
        destination = folder / (run+"-"+session+"-"+source.parent.name+"-"+source.name+".gz")
        entry = package(source, destination)
        if source.suffix == ".jsonl":
            states = Counter()
            count = 0
            with source.open(encoding="utf-8") as rows:
                for line in rows:
                    if line.strip():
                        row = json.loads(line)
                        states[row.get("status", row.get("topic", "unknown"))] += 1
                        count += 1
            entry.update(records=count, states=dict(states))
        files.append(entry)
    if not files:
        print("No saved SSI data found for", day, flush=True)
        return
    manifest_path = folder / (run+"-"+session+"-manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    tag = "ssi-data-" + day
    if subprocess.run(["gh", "release", "view", tag], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        subprocess.run(["gh", "release", "create", tag, "--target", os.environ["GITHUB_SHA"],
                        "--title", "SSI research data " + day,
                        "--notes", "SSI evidence archives with SHA-256 manifests. Inspect each manifest for granularity and coverage."], check=True)
    subprocess.run(["gh", "release", "upload", tag, str(manifest_path),
                    *(str(folder / entry["file"]) for entry in files)], check=True)
    print(json.dumps({"date":day,"files":len(files),"raw_bytes":sum(f["source_bytes"] for f in files),
                      "compressed_bytes":sum(f["compressed_bytes"] for f in files),"release":tag}), flush=True)


if __name__ == "__main__":
    main()
