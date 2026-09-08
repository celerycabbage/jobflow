"""Small dependency-free authenticated API latency benchmark for local verification."""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


def request_json(url: str, *, token: str | None = None, data: dict | None = None):
    body = json.dumps(data).encode() if data is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, json.load(response)


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * quantile))
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=20)
    args = parser.parse_args()
    _, login = request_json(
        f"{args.base_url}/auth/login", data={"email": args.email, "password": args.password}
    )
    token = login["access_token"]

    def sample() -> float:
        started = time.perf_counter()
        status, _ = request_json(f"{args.base_url}/applications", token=token)
        if status != 200:
            raise RuntimeError(f"unexpected HTTP {status}")
        return (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        latencies = [future.result() for future in as_completed(
            [executor.submit(sample) for _ in range(args.requests)]
        )]
    elapsed = time.perf_counter() - started
    print(json.dumps({
        "requests": len(latencies),
        "concurrency": args.concurrency,
        "errors": 0,
        "throughput_rps": round(len(latencies) / elapsed, 2),
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 2),
            "p50": round(percentile(latencies, 0.50), 2),
            "p95": round(percentile(latencies, 0.95), 2),
            "max": round(max(latencies), 2),
        },
    }, indent=2))


if __name__ == "__main__":
    main()
