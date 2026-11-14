#!/usr/bin/env python3
"""Run bounded fresh-process HTTP/3 requests against the fixed lab Caddy host."""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import math
import subprocess
import time
from collections import Counter
from typing import Any

CLIENT_IP, ORIGIN_IP, HOSTNAME = "192.168.80.29", "192.168.80.28", "mysite.local"
DEFAULT_CURL = "/home/netpro/netpro-thesis/http3/prefix/bin/curl"
ALLOWED_CONCURRENCY = (1, 4, 8, 16)
MAX_REQUESTS = 500


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * p
    lower, upper = math.floor(rank), math.ceil(rank)
    value = ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)
    return round(value, 6)


def curl_command(curl: str) -> list[str]:
    return [
        curl, "--http3-only", "--noproxy", "*", "--interface", CLIENT_IP,
        "--resolve", f"{HOSTNAME}:443:{ORIGIN_IP}", "-k", "--silent", "--show-error",
        "--connect-timeout", "3", "--max-time", "6", "--output", "/dev/null",
        "--write-out", "%{http_code}\t%{http_version}\t%{time_total}\n",
        f"https://{HOSTNAME}/",
    ]


def run_one(curl: str, index: int) -> dict[str, Any]:
    start = time.monotonic()
    try:
        proc = subprocess.run(curl_command(curl), capture_output=True, text=True,
                              timeout=8, check=False)
        elapsed = time.monotonic() - start
        fields = proc.stdout.strip().split("\t")
        status = fields[0] if len(fields) > 0 else "000"
        version = fields[1] if len(fields) > 1 else ""
        try:
            total = float(fields[2]) if len(fields) > 2 else elapsed
        except ValueError:
            total = elapsed
        return {"index": index, "curl_code": proc.returncode, "http_status": status,
                "http_version": version, "time_total": round(total, 6),
                "runner_timeout": False}
    except subprocess.TimeoutExpired:
        return {"index": index, "curl_code": "runner_timeout", "http_status": "000",
                "http_version": "", "time_total": round(time.monotonic() - start, 6),
                "runner_timeout": True}
    except OSError as exc:
        return {"index": index, "curl_code": "launch_error", "http_status": "000",
                "http_version": "", "time_total": round(time.monotonic() - start, 6),
                "runner_timeout": False, "error": str(exc)[:240]}


def summarize(results: list[dict[str, Any]], expected: str, requests: int,
              concurrency: int, curl: str, started_utc: str) -> dict[str, Any]:
    def is_http3_200(row: dict[str, Any]) -> bool:
        return row["curl_code"] == 0 and row["http_status"] == "200" and row["http_version"].startswith("3")

    def matched_expectation(row: dict[str, Any]) -> bool:
        if expected == "allow":
            return is_http3_200(row)
        # A denied connection should produce no HTTP response. A 403/other HTTP
        # response means the request reached an HTTP server and is not a gate pass.
        return row["curl_code"] != 0 and row["http_status"] == "000"

    times = [row["time_total"] for row in results]
    codes = Counter(str(row["curl_code"]) for row in results)
    statuses = Counter(row["http_status"] for row in results)
    versions = Counter(row["http_version"] or "none" for row in results)
    return {
        "started_utc": started_utc,
        "finished_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "target": f"https://{HOSTNAME}/", "origin_ip": ORIGIN_IP,
        "interface_ip": CLIENT_IP, "expected": expected, "curl": curl,
        "requests": requests, "concurrency": concurrency,
        "attempted": len(results), "http3_200": sum(is_http3_200(row) for row in results),
        "curl_failures": sum(row["curl_code"] != 0 for row in results),
        "expectation_failures": sum(not matched_expectation(row) for row in results),
        "curl_codes": dict(codes), "http_statuses": dict(statuses),
        "http_versions": dict(versions),
        "time_total_seconds": {"p50": percentile(times, 0.50),
                               "p95": percentile(times, 0.95),
                               "p99": percentile(times, 0.99)},
        "expectation_met": all(matched_expectation(row) for row in results),
        "results": results,
    }


def run_benchmark(curl: str, requests: int, concurrency: int, expected: str) -> dict[str, Any]:
    if not 1 <= requests <= MAX_REQUESTS:
        raise ValueError(f"requests must be between 1 and {MAX_REQUESTS}")
    if concurrency not in ALLOWED_CONCURRENCY:
        raise ValueError(f"concurrency must be one of {ALLOWED_CONCURRENCY}")
    if expected not in ("allow", "deny"):
        raise ValueError("expect must be allow or deny")
    started_utc = dt.datetime.now(dt.timezone.utc).isoformat()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(run_one, curl, index) for index in range(requests)]
        results = [future.result() for future in futures]
    results.sort(key=lambda row: row["index"])
    return summarize(results, expected, requests, concurrency, curl, started_utc)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--curl", default=DEFAULT_CURL)
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, choices=ALLOWED_CONCURRENCY, default=1)
    parser.add_argument("--expect", choices=("allow", "deny"), required=True)
    args = parser.parse_args()
    try:
        result = run_benchmark(args.curl, args.requests, args.concurrency, args.expect)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
