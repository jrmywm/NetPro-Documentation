import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

import bench_http3


class Http3BenchTests(unittest.TestCase):
    def test_one_request_uses_fresh_curl_process_and_parses_writeout(self):
        fake = SimpleNamespace(returncode=0, stdout="200\t3\t0.125000\n", stderr="")
        with mock.patch.object(bench_http3.subprocess, "run", return_value=fake) as run:
            result = bench_http3.run_one("/lab/curl", 4)
        args, kwargs = run.call_args
        self.assertEqual(args[0][0], "/lab/curl")
        self.assertIn("--http3-only", args[0])
        self.assertIn("--noproxy", args[0])
        self.assertIn("192.168.80.29", args[0])
        self.assertIn("--max-time", args[0])
        self.assertNotIn("--fresh-connect", args[0])
        self.assertNotIn("shell", kwargs)  # subprocess.run defaults to shell=False
        self.assertEqual((result["http_status"], result["http_version"]), ("200", "3"))
        self.assertEqual(result["time_total"], 0.125)

    def test_allow_and_deny_expectations_and_percentiles(self):
        allowed = [
            {"index": 0, "curl_code": 0, "http_status": "200", "http_version": "3",
             "time_total": 0.1, "runner_timeout": False},
            {"index": 1, "curl_code": 0, "http_status": "200", "http_version": "3",
             "time_total": 0.2, "runner_timeout": False},
        ]
        report = bench_http3.summarize(allowed, "allow", 2, 1, "curl", "start")
        self.assertTrue(report["expectation_met"])
        self.assertEqual(report["http3_200"], 2)
        self.assertEqual(report["time_total_seconds"], {"p50": 0.15, "p95": 0.195, "p99": 0.199})

        denied = [{"index": 0, "curl_code": 28, "http_status": "000", "http_version": "",
                   "time_total": 6.0, "runner_timeout": False}]
        report = bench_http3.summarize(denied, "deny", 1, 1, "curl", "start")
        self.assertTrue(report["expectation_met"])
        self.assertEqual(report["curl_failures"], 1)

    def test_request_and_concurrency_caps(self):
        with self.assertRaises(ValueError):
            bench_http3.run_benchmark("curl", 501, 1, "allow")
        with self.assertRaises(ValueError):
            bench_http3.run_benchmark("curl", 20, 2, "allow")

    def test_curl_runner_timeout_is_a_bounded_result(self):
        with mock.patch.object(bench_http3.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("curl", 8)):
            result = bench_http3.run_one("curl", 1)
        self.assertEqual(result["curl_code"], "runner_timeout")
        self.assertEqual(result["http_status"], "000")
        self.assertTrue(result["runner_timeout"])


if __name__ == "__main__":
    unittest.main()
