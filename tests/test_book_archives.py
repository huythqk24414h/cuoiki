import gzip
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.audit_book_archives import audit


class BookArchiveTests(unittest.TestCase):
    def test_archive_audit_separates_checkpoints_duplicates_and_conflicts(self):
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            rows = []
            for time, status in (("09:14:59", "no_quote"), ("09:15:00", "fresh_two_sided_quote"),
                                 ("09:15:00", "fresh_two_sided_quote"), ("09:15:02", "no_quote"),
                                 ("09:15:02", "fresh_two_sided_quote")):
                rows.append(json.dumps({"sampled_at": f"2026-11-24T{time}+07:00",
                                        "symbol": "TEST", "status": status}))
            files = {"1-morning-order_book_capture-sample.jsonl.gz": "\n".join(rows),
                     "1-morning-book-checkpoint.json.gz": "{}"}
            entries = []
            for name, contents in files.items():
                blob = gzip.compress(contents.encode())
                (folder / name).write_bytes(blob)
                entries.append({"file": name, "sha256": sha256(blob).hexdigest()})
            manifest = {"date": "2026-11-24", "session": "morning", "files": entries}
            for name in ("one-manifest.json", "duplicate-manifest.json"):
                (folder / name).write_text(json.dumps(manifest), encoding="utf-8")
            result = audit(folder)
            self.assertEqual(result["checkpoint_files_by_day"], {"2026-11-24": 1})
            symbol = result["sessions"][0]["symbols"][0]
            self.assertEqual(symbol["sample_rows"], 4)
            self.assertEqual(symbol["observed_seconds"], 2)
            self.assertEqual(symbol["fresh_session_flag_seconds"], 1)
            self.assertEqual(symbol["longest_missing_seconds"], 8097)
            self.assertEqual(symbol["status_seconds"]["conflicting_samples"], 1)
            (folder / next(iter(files))).write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
                audit(folder)
