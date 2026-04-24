"""Simulate a SmartMat Lite device's call sequence.

Usage:
    python scripts/simulate_device.py                         # one full cycle
    python scripts/simulate_device.py --loop --interval 10    # loop every 10s
    python scripts/simulate_device.py --id W42200500999 --weight 1234.5
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
import urllib.request
from datetime import datetime, timezone


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse(payload: str) -> dict:
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {"_raw": payload}


def post(base: str, path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        base + path,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        payload = resp.read().decode()
    print(f"POST {path} -> {payload}")
    return _parse(payload)


def get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=5) as resp:
        payload = resp.read().decode()
    print(f"GET  {path} -> {payload}")
    return _parse(payload)


def cycle(base: str, device_id: str, weight: float, battery: float, rssi: int, first: bool) -> None:
    common = {"id": device_id, "wv": "2.08", "mv": "15"}
    if first:
        post(base, "/v1/device/version2/i", common)
    post(base, "/v1/device/version2/s", common)
    get(base, "/v1/device/version2/sd")
    post(
        base,
        "/v1/device/version2/m",
        {
            "id": device_id,
            "md": [{"w": f"{weight:.2f}", "d": now_utc()}],
            "b": f"{battery:.2f}",
            "p": "0",
            "r": str(rssi),
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8080")
    parser.add_argument("--id", default="W42200500161")
    parser.add_argument("--weight", type=float, default=1480.0)
    parser.add_argument("--battery", type=float, default=0.43)
    parser.add_argument("--rssi", type=int, default=-40)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=int, default=10)
    parser.add_argument("--jitter", type=float, default=20.0, help="random grams added each loop")
    args = parser.parse_args()

    first = True
    w = args.weight
    try:
        while True:
            cycle(args.base, args.id, w, args.battery, args.rssi, first)
            first = False
            if not args.loop:
                break
            w = max(0.0, w + random.uniform(-args.jitter, args.jitter))
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
