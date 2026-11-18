"""Losslessly compress existing SSI values using atomic compare-and-swap."""
import json
from scripts.market_store import decode_value, encode_value, redis

STRING_CAS = "if redis.call('GET',KEYS[1]) == ARGV[1] then redis.call('SET',KEYS[1],ARGV[2],'KEEPTTL'); return 1 else return 0 end"
HASH_CAS = "if redis.call('HGET',KEYS[1],ARGV[1]) == ARGV[2] then redis.call('HSET',KEYS[1],ARGV[1],ARGV[3]); return 1 else return 0 end"


def compact(key, raw, field=None):
    if raw is None:
        return 0
    original = decode_value(raw)
    packed = encode_value(original)
    if len(packed.encode()) >= len(raw.encode()):
        return 0
    if json.loads(decode_value(packed)) != json.loads(original):
        raise ValueError("Compression round-trip failed")
    args = ["EVAL", STRING_CAS, 1, key, raw, packed] if field is None else ["EVAL", HASH_CAS, 1, key, field, raw, packed]
    return (len(raw.encode()) - len(packed.encode())) if redis(args) == 1 else 0


def main():
    print("Storage before:", redis(["INFO", "memory"]), flush=True)
    cursor = "0"
    saved = count = 0
    while True:
        cursor, keys = redis(["SCAN", cursor, "MATCH", "liquiditylab:*", "COUNT", 100])
        for key in keys:
            kind = redis(["TYPE", key])
            if kind == "string":
                saved += compact(key, redis(["GET", key], decode=False))
                count += 1
            elif kind == "hash":
                field_cursor = "0"
                while True:
                    field_cursor, entries = redis(["HSCAN", key, field_cursor, "COUNT", 100])
                    for index in range(0, len(entries), 2):
                        saved += compact(key, entries[index+1], entries[index])
                        count += 1
                    if str(field_cursor) == "0":
                        break
        if str(cursor) == "0":
            break
    print(f"Checked {count} values; saved {saved} stored bytes. All source observations retained.", flush=True)
    print("Storage after:", redis(["INFO", "memory"]), flush=True)


if __name__ == "__main__":
    main()
