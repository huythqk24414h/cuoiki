import json
import unittest
from unittest.mock import patch
from scripts.market_store import decode_value, encode_value
from scripts.compact_market_store import compact


class StorageEncodingTests(unittest.TestCase):
    def test_existing_and_compressed_values_preserve_all_observations(self):
        raw = json.dumps([{"symbol":"FPT", "date":f"2026-11-{day:02}", "volume":"12345678901234567890", "note":"Dữ liệu SSI"} for day in range(1, 19)], ensure_ascii=False)
        packed = encode_value(raw)
        self.assertLess(len(packed.encode()), len(raw.encode()))
        self.assertEqual(decode_value(packed), raw)
        self.assertEqual(decode_value(raw), raw)
        self.assertEqual(encode_value(packed), packed)
        self.assertIsNone(decode_value(None))

    def test_compaction_uses_compare_and_swap_and_preserves_ttl(self):
        raw = json.dumps([{"close":"12345", "volume":"100000"}] * 100)
        with patch("scripts.compact_market_store.redis", return_value=1) as call:
            self.assertGreater(compact("liquiditylab:history:old:FPT", raw), 0)
            args = call.call_args.args[0]
            self.assertEqual(args[0], "EVAL")
            self.assertIn("KEEPTTL", args[1])
            self.assertEqual(args[-2], raw)
            self.assertEqual(decode_value(args[-1]), raw)
        with patch("scripts.compact_market_store.redis", return_value=0):
            self.assertEqual(compact("liquiditylab:live", raw), 0)

    def test_hash_compaction_preserves_field_and_checks_original(self):
        raw = json.dumps({"rows":[["2026-11-17", "10"]] * 100})
        with patch("scripts.compact_market_store.redis", return_value=1) as call:
            self.assertGreater(compact("liquiditylab:market-eod-updates", raw, "FPT"), 0)
            args = call.call_args.args[0]
            self.assertEqual(args[-3:-1], ["FPT", raw])
            self.assertEqual(decode_value(args[-1]), raw)
