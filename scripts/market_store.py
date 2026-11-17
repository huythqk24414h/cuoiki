"""Publish selected public-facing snapshots using a server-side Redis REST token."""
import json
import os
from urllib.request import Request, urlopen


def redis(command):
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
        raise RuntimeError("Market store rejected command")
    return payload["result"]


def publish(kind, data, ttl=None):
    key = "liquiditylab:" + kind
    command = ["SET", key, json.dumps(data, allow_nan=False, separators=(",", ":"))]
    if ttl is not None:
        command.extend(["EX", ttl])
    if redis(command) != "OK":
        raise RuntimeError("Market store did not acknowledge write")
    return len(command[2].encode("utf-8"))


def archive_book(key, snapshot):
    # A checkpoint is immutable, including when a request is retried.
    result = redis(["SET", "liquiditylab:" + key,
                    json.dumps(snapshot, allow_nan=False, separators=(",", ":")), "NX"])
    if result not in ("OK", None):
        raise RuntimeError("Market store did not acknowledge checkpoint")
