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


def publish(kind, data):
    key = "liquiditylab:" + kind
    if redis(["SET", key, json.dumps(data, allow_nan=False, separators=(",", ":"))]) != "OK":
        raise RuntimeError("Market store did not acknowledge write")
