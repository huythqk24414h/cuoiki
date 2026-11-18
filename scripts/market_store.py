"""Publish selected public-facing snapshots using a server-side Redis REST token."""
import base64
import gzip
import json
import os
from urllib.request import Request, urlopen


def encode_value(raw):
    if len(raw.encode("utf-8")) < 1024:
        return raw
    packed = json.dumps({"_ssi_encoding":"gzip-base64-v1",
                         "data":base64.b64encode(gzip.compress(raw.encode("utf-8"), mtime=0)).decode()},
                        separators=(",", ":"))
    return packed if len(packed.encode("utf-8")) < len(raw.encode("utf-8")) else raw


def decode_value(raw):
    if raw is None:
        return None
    value = json.loads(raw)
    if isinstance(value, dict) and value.get("_ssi_encoding") == "gzip-base64-v1":
        return gzip.decompress(base64.b64decode(value["data"])).decode("utf-8")
    return raw


def redis(command, decode=True):
    command = list(command)
    operation = command[0].upper()
    if len(command) > 2 and str(command[1]).startswith("liquiditylab:"):
        positions = [2] if operation == "SET" else range(3, len(command), 2) if operation == "HSET" else []
        for position in positions:
            command[position] = encode_value(command[position])
    url = os.environ["UPSTASH_REDIS_REST_URL"]
    if not url.startswith("https://"):
        raise ValueError("Redis REST requires HTTPS")
    request = Request(
        url,
        data=json.dumps(command, allow_nan=False).encode(),
        headers={"Authorization": "Bearer " + os.environ["UPSTASH_REDIS_REST_TOKEN"],
                 "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=6) as response:
        payload = json.load(response)
    if "error" in payload:
        reason = str(payload["error"]).lower()
        category = "storage capacity" if any(word in reason for word in ("max data", "memory", "capacity")) else "command quota" if "limit" in reason else "command"
        raise RuntimeError("Market store rejected " + category)
    result = payload["result"]
    if decode and operation in ("GET", "HGET"):
        return decode_value(result)
    if decode and operation == "MGET":
        return [decode_value(value) for value in result]
    return result


def publish(kind, data, ttl=None):
    key = "liquiditylab:" + kind
    command = ["SET", key, json.dumps(data, allow_nan=False, separators=(",", ":"))]
    if ttl is not None:
        command.extend(["EX", ttl])
    if redis(command) != "OK":
        raise RuntimeError("Market store did not acknowledge write")
    return len(encode_value(command[2]).encode("utf-8"))


def archive_book(key, snapshot):
    # A checkpoint is immutable, including when a request is retried.
    result = redis(["SET", "liquiditylab:" + key,
                    json.dumps(snapshot, allow_nan=False, separators=(",", ":")), "NX"])
    if result not in ("OK", None):
        raise RuntimeError("Market store did not acknowledge checkpoint")
