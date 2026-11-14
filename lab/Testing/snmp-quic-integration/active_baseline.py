#!/usr/bin/env python3
"""Staged, bounded SNMP lab policy/RST baseline workflow.

This file is inert by default. Review the implementation and the existing
SNMP/QUIC integration plan before invoking it with --execute-active-test.
It uses only the supported Backend CRUD API for policy changes; Policy SQLite
access is read-only and restricted to IDs plus the exact temporary test row.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import shlex
import struct
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from remote import COMMAND_TIMEOUT, HOSTS, connect_verified, redact, run_remote_command


POLICY_HOST = "192.168.31.31"
BACKEND_HOST = "192.168.31.35"
GATEWAY_HOST = "192.168.31.37"
CLIENT_HOST = "192.168.31.39"
DB_PATH = "/home/ubuntu/NetPro-Policy-Server/policy.db"
API_ROOT = "https://127.0.0.1:3000/ps/blocked-list"
GATEWAY_SERVER = "/home/netpro/netpro-demo/virtual-tap-live-test/server.sh"
GATEWAY_SERVER_SHA256 = "67d4dcb721527105f63113bb20fd2392e84ef52daa9d6fb7194d30a80305b722"
RST_HELPER = "/usr/local/libexec/netpro-dedicated-rst-return/return.sh"
RST_HELPER_SHA256 = "def03bbfddabba1976927cfd209c327519e9bcc6d988d89d73ed1e56e11c3bb2"
TEST_DOMAIN = "netpro-tap.test"
TEST_IP = "192.0.2.123"
TEST_NAME_PREFIX = "snmp-quic-baseline-20261010"
TEST_CATEGORY = "Other"
EXPECTED_API_POLICY_IDS = frozenset({"7f3fbb19-4064-432c-b9b9-72363c5c1cd9"})
EXPECTED_SQLITE_POLICY_IDS = frozenset({
    "kafka-persistence-test",
    "netpro-http-facebook-001",
    "netpro-tls-ui-001",
    "7f3fbb19-4064-432c-b9b9-72363c5c1cd9",
})
SQLITE_WAIT_SECONDS = 20
TRIAL_COUNT = 20


class WorkflowError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_id(value: Any) -> str:
    text = str(value or "")
    if not re.fullmatch(r"[A-Fa-f0-9-]{36}", text):
        raise WorkflowError("API did not return a UUID policy ID; refusing follow-on work")
    return text


def safe_policy_key(value: Any) -> str:
    """Validate an existing opaque policy key for baseline set comparisons."""
    text = str(value or "")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", text):
        raise WorkflowError("baseline contains an unsafe or empty policy key")
    return text


def validate_split_clienthello_pcap(path: Path, expected_flows: int) -> dict[str, Any]:
    """Reassemble the first client TLS record per TCP flow and prove segmentation."""
    data = path.read_bytes()
    endian = {
        b"\xd4\xc3\xb2\xa1": "<", b"\xa1\xb2\xc3\xd4": ">",
        b"\x4d\x3c\xb2\xa1": "<", b"\xa1\xb2\x3c\x4d": ">",
    }.get(data[:4])
    if not endian or len(data) < 24:
        raise WorkflowError("split PCAP has an unsupported or truncated header")
    link_type = struct.unpack_from(endian + "I", data, 20)[0]
    if link_type != 1:
        raise WorkflowError("split PCAP link type is not Ethernet")
    offset = 24
    streams: dict[int, list[tuple[int, bytes]]] = {}
    packets = 0
    while offset + 16 <= len(data):
        _sec, _usec, captured_len, _original_len = struct.unpack_from(endian + "IIII", data, offset)
        offset += 16
        if captured_len > len(data) - offset:
            raise WorkflowError("split PCAP contains a truncated packet record")
        frame = data[offset:offset + captured_len]
        offset += captured_len
        packets += 1
        if len(frame) < 14:
            continue
        ethertype = struct.unpack_from("!H", frame, 12)[0]
        network_offset = 14
        while ethertype in (0x8100, 0x88A8):
            if len(frame) < network_offset + 4:
                break
            ethertype = struct.unpack_from("!H", frame, network_offset + 2)[0]
            network_offset += 4
        if ethertype != 0x0800 or len(frame) < network_offset + 20:
            continue
        ip = frame[network_offset:]
        ihl = (ip[0] & 0x0F) * 4
        if ip[0] >> 4 != 4 or ihl < 20 or ip[9] != 6 or len(ip) < ihl + 20:
            continue
        src = ".".join(str(x) for x in ip[12:16])
        dst = ".".join(str(x) for x in ip[16:20])
        fragment = struct.unpack_from("!H", ip, 6)[0]
        if src != "192.168.80.29" or dst != "192.168.80.28" or fragment & 0x3FFF:
            continue
        ip_total = struct.unpack_from("!H", ip, 2)[0]
        if ip_total < ihl + 20 or ip_total > len(ip):
            raise WorkflowError("split PCAP contains a truncated IP packet")
        tcp = ip[ihl:ip_total]
        source_port, destination_port = struct.unpack_from("!HH", tcp, 0)
        tcp_header_len = (tcp[12] >> 4) * 4
        if destination_port != 8443 or tcp_header_len < 20 or len(tcp) < tcp_header_len:
            continue
        payload = tcp[tcp_header_len:]
        if payload:
            sequence = struct.unpack_from("!I", tcp, 4)[0]
            streams.setdefault(source_port, []).append((sequence, payload))

    validated: list[dict[str, Any]] = []
    failures: list[str] = []
    for port, segments in sorted(streams.items()):
        assembled = bytearray()
        segment_sizes: list[int] = []
        next_sequence: int | None = None
        for sequence, payload in sorted(segments, key=lambda item: item[0]):
            if next_sequence is None:
                next_sequence = sequence
            if sequence > next_sequence:
                failures.append(f"port {port}: sequence gap before first record complete")
                break
            end = sequence + len(payload)
            if end <= next_sequence:
                continue
            overlap = max(0, next_sequence - sequence)
            new_bytes = payload[overlap:]
            if not new_bytes:
                continue
            assembled.extend(new_bytes)
            segment_sizes.append(len(new_bytes))
            next_sequence = end
            if len(assembled) >= 5:
                record_total = 5 + int.from_bytes(assembled[3:5], "big")
                if record_total > 18437 or record_total < 6:
                    failures.append(f"port {port}: invalid TLS record length")
                    break
                if len(assembled) >= record_total:
                    part_sizes: list[int] = []
                    remaining = record_total
                    for size in segment_sizes:
                        take = min(size, remaining)
                        if take:
                            part_sizes.append(take)
                            remaining -= take
                        if remaining == 0:
                            break
                    if assembled[0] != 22 or assembled[5] != 1:
                        failures.append(f"port {port}: first TLS record is not ClientHello")
                    elif len(part_sizes) < 2:
                        failures.append(f"port {port}: first TLS record was not TCP-segmented")
                    else:
                        validated.append({"client_source_port": port,
                                          "tls_record_bytes": record_total,
                                          "tcp_payload_piece_bytes": part_sizes})
                    break
        else:
            failures.append(f"port {port}: first TLS record incomplete")
    passed = len(validated) == expected_flows and not failures
    return {"passed": passed, "pcap_packets": packets, "client_tls_flows": len(streams),
            "validated_split_flows": len(validated), "expected_flows": expected_flows,
            "flows": validated, "failures": failures}


class ActiveBaseline:
    def __init__(self, password: str, evidence_dir: Path, known_hosts: Path,
                 split_clienthello: bool = False):
        self.password = password
        self.evidence_dir = evidence_dir
        self.known_hosts = known_hosts
        self.clients: dict[str, Any] = {}
        self.server_started = False
        self.rst_started = False
        self.split_clienthello = split_clienthello
        self.split_profile: dict[str, dict[str, Any]] = {}
        self.policy_id: str | None = None
        self.policy_deleted = False
        self.capture_paths: list[str] = []
        self.document: dict[str, Any] = {
            "workflow": "active-snmp-policy-rst-baseline",
            "created_utc": utc_now(),
            "test_domain": TEST_DOMAIN,
            "test_ip": TEST_IP,
            "test_name": f"{TEST_NAME_PREFIX}-<run-id>",
            "expected_baseline_api_policy_count": len(EXPECTED_API_POLICY_IDS),
            "expected_baseline_sqlite_policy_count": len(EXPECTED_SQLITE_POLICY_IDS),
            "known_preexisting_api_sqlite_drift": "three legacy SQLite-only rows are preserved; this test does not reconcile them",
            "vmx_note": "Generator adapter 4 startConnected=FALSE is saved VMX state, not proof of live cable state.",
            "events": [],
            "captures": [],
            "outcomes": {},
            "cleanup": [],
            "split_clienthello_requested": split_clienthello,
        }
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8]
        self.test_name = f"{TEST_NAME_PREFIX}-{self.run_id}"
        self.document["test_name"] = self.test_name
        self.evidence_path = evidence_dir / f"active-baseline-{self.run_id}.json"

    def save(self) -> None:
        self.document["updated_utc"] = utc_now()
        self.evidence_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.evidence_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(self.document, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.evidence_path)

    def event(self, name: str, **details: Any) -> None:
        self.document["events"].append({"time_utc": utc_now(), "name": name, **details})
        self.save()

    def connect_all(self) -> None:
        for ip in (POLICY_HOST, BACKEND_HOST, GATEWAY_HOST, CLIENT_HOST):
            expected = HOSTS[ip]
            client, actual = connect_verified(
                ip,
                "netpro",
                self.password,
                self.known_hosts,
                timeout=COMMAND_TIMEOUT,
            )
            self.clients[ip] = client
            self.event("ssh_host_verified", host=ip, expected=expected, actual=actual)

    def command(self, host: str, label: str, command: str, *, sudo: bool = False,
                timeout: int = COMMAND_TIMEOUT, allow_failure: bool = False,
                record_output: bool = True) -> tuple[int, str, str]:
        status, stdout, stderr = run_remote_command(
            self.clients[host], command,
            sudo_password=self.password if sudo else None,
            timeout=timeout,
        )
        self.event(
            "remote_command",
            label=label,
            host=host,
            exit_status=status,
            stdout=redact(stdout[-12000:]) if record_output else "[omitted; parsed in memory]",
            stderr=redact(stderr[-2000:]),
        )
        if status != 0 and not allow_failure:
            raise WorkflowError(f"remote step failed: {label} on {host} (exit {status})")
        return status, stdout, stderr

    def api(self, method: str, policy_id: str | None = None,
            payload: dict[str, str] | None = None) -> Any:
        path = API_ROOT if policy_id is None else f"{API_ROOT}/{safe_id(policy_id)}"
        curl = ["curl", "--insecure", "--silent", "--show-error", "--max-time", "8",
                "--write-out", "\\n__NETPRO_STATUS__%{http_code}"]
        if method != "GET":
            curl.extend(["--request", method])
        if payload is not None:
            curl.extend(["--header", "Content-Type: application/json", "--data-binary",
                         json.dumps(payload, separators=(",", ":"))])
        curl.append(path)
        command = " ".join(shlex.quote(part) for part in curl)
        status, output, _ = self.command(BACKEND_HOST, f"api_{method.lower()}", command,
                                         timeout=12, record_output=False)
        if status != 0:
            raise WorkflowError(f"Backend API {method} failed")
        body, marker, http_status = output.rpartition("\n__NETPRO_STATUS__")
        if not marker or not http_status.strip().isdigit() or not (200 <= int(http_status.strip()) < 300):
            raise WorkflowError(f"Backend API {method} returned an unexpected HTTP status")
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise WorkflowError(f"Backend API {method} returned invalid JSON") from exc

    def policy_api_ids(self) -> tuple[set[str], list[dict[str, Any]]]:
        result = self.api("GET")
        if not isinstance(result, list):
            raise WorkflowError("Backend blocked-list API did not return a list")
        ids = {safe_policy_key(row.get("id")) for row in result if isinstance(row, dict)}
        if len(ids) != len(result):
            raise WorkflowError("Backend API list has duplicate or invalid IDs")
        return ids, result

    def sqlite(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        # SQLite CLI -json is not available on all lab images; Python stdlib is.
        script = ("import json,sqlite3,sys; "
                  "c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True); "
                  "c.row_factory=sqlite3.Row; c.execute('PRAGMA query_only=ON'); "
                  "print(json.dumps([dict(r) for r in c.execute(sys.argv[2],json.loads(sys.argv[3])).fetchall()]))")
        command = "python3 -c " + shlex.quote(script) + " " + shlex.quote(DB_PATH) + " " + shlex.quote(query) + " " + shlex.quote(json.dumps(params))
        status, output, _ = self.command(POLICY_HOST, "policy_db_readonly", command,
                                         sudo=True, timeout=12, record_output=False)
        if status != 0:
            raise WorkflowError("read-only Policy SQLite query failed")
        try:
            result = json.loads(output)
        except json.JSONDecodeError as exc:
            raise WorkflowError("Python sqlite3 did not return valid JSON") from exc
        if not isinstance(result, list):
            raise WorkflowError("sqlite3 returned an unexpected result")
        return result

    def wait_sqlite_row(self, policy_id: str, want_present: bool) -> None:
        exact = "SELECT id, domain, ip_address FROM policies WHERE id = ? AND domain = ? AND ip_address = ?"
        deadline = time.monotonic() + SQLITE_WAIT_SECONDS
        while time.monotonic() < deadline:
            rows = self.sqlite(exact, (policy_id, TEST_DOMAIN, TEST_IP))
            if bool(rows) == want_present and (not rows or len(rows) == 1):
                if rows and (rows[0].get("id") != policy_id or
                             rows[0].get("domain") != TEST_DOMAIN or
                             rows[0].get("ip_address") != TEST_IP):
                    raise WorkflowError("SQLite row did not exactly match the temporary policy")
                self.event("policy_sqlite_reflection", policy_id=policy_id,
                           present=want_present, elapsed_seconds=round(SQLITE_WAIT_SECONDS - max(0, deadline-time.monotonic()), 2))
                return
            time.sleep(1)
        raise WorkflowError(f"temporary policy SQLite presence={want_present} was not observed in time")

    def baseline(self) -> None:
        api_ids, api_rows = self.policy_api_ids()
        sqlite_rows = self.sqlite("SELECT id FROM policies ORDER BY id;")
        sqlite_ids = {safe_policy_key(row.get("id")) for row in sqlite_rows}
        if api_ids != EXPECTED_API_POLICY_IDS:
            raise WorkflowError("Backend API baseline ID set differs from the exact known baseline")
        if sqlite_ids != EXPECTED_SQLITE_POLICY_IDS:
            raise WorkflowError("Policy SQLite baseline ID set differs from the exact known baseline")
        for row in api_rows:
            if row.get("name", "").startswith(TEST_NAME_PREFIX) or row.get("domain") == TEST_DOMAIN or row.get("ip_add") == TEST_IP:
                raise WorkflowError("temporary test name/domain/IP already exists; refusing create")
        conflicts = self.sqlite("SELECT id FROM policies WHERE domain = ? OR ip_address = ?",
                                (TEST_DOMAIN, TEST_IP))
        if conflicts:
            raise WorkflowError("temporary domain or dummy IP already exists in Policy SQLite")
        self.document["baseline_api_policy_ids"] = sorted(api_ids)
        self.document["baseline_sqlite_policy_ids"] = sorted(sqlite_ids)
        self.event("policy_baseline_verified", api_ids=sorted(api_ids), sqlite_ids=sorted(sqlite_ids),
                   sqlite_only_ids=sorted(sqlite_ids - api_ids))

    def start_gateway_server(self) -> None:
        preflight = (
            "set -eu; test \"$(hostname -s)\" = netpro-test-gateway; "
            "test ! -e /run/netpro-tap-live-test; "
            "test \"$(systemctl show -p LoadState --value netpro-tap-live-http.service)\" = not-found; "
            "test \"$(systemctl show -p LoadState --value netpro-tap-live-tls.service)\" = not-found; "
            "if ss -H -ltn | awk '$4 ~ /:(8080|8443)$/ {found=1} END {exit !found}'; then exit 1; fi"
        )
        self.command(GATEWAY_HOST, "gateway_server_ownership_preflight", preflight,
                     sudo=True, timeout=12)
        # State, units and listeners were confirmed absent; any partial start is
        # now ours to stop by this helper's narrow owned-state guard.
        self.server_started = True
        command = (
            "set -eu; f=" + shlex.quote(GATEWAY_SERVER) + "; test -f \"$f\"; "
            "test \"$(sha256sum \"$f\" | cut -d' ' -f1)\" = " + GATEWAY_SERVER_SHA256 +
            "; exec /bin/bash \"$f\" start"
        )
        self.command(GATEWAY_HOST, "gateway_server_start", command, sudo=True, timeout=20)
        # Active systemd units can precede socket readiness, especially under load.
        self.command(GATEWAY_HOST, "gateway_listener_readiness",
                     "set -eu; for n in $(seq 1 20); do "
                     "if ss -H -ltn | awk '$4 == \"192.168.80.28:8080\" {h=1} "
                     "$4 == \"192.168.80.28:8443\" {t=1} END {exit !(h && t)}'; then "
                     "echo TEST_LISTENERS_READY; exit 0; fi; sleep 0.5; done; "
                     "echo TEST_LISTENERS_NOT_READY; ss -H -ltn; exit 1", sudo=True, timeout=15)

    def create_policy(self) -> str:
        payload = {
            "name": self.test_name,
            "domain": TEST_DOMAIN,
            "ip_add": TEST_IP,
            "category": TEST_CATEGORY,
        }
        try:
            response = self.api("POST", payload=payload)
        except Exception:
            # POST may have committed even when the connection timed out. Recover
            # only a unique exact-name/domain/IP row whose ID was not in baseline.
            self.recover_created_policy()
            raise
        created = response.get("createdBlockedList") if isinstance(response, dict) else None
        if not isinstance(created, dict):
            self.recover_created_policy()
            raise WorkflowError("POST response did not contain createdBlockedList")
        try:
            policy_id = safe_id(created.get("id"))
        except WorkflowError:
            self.recover_created_policy()
            raise
        self.policy_id = policy_id
        self.document["temporary_policy"] = {"id": policy_id, "name": self.test_name,
                                               "domain": TEST_DOMAIN, "ip_add": TEST_IP,
                                               "category": TEST_CATEGORY}
        self.save()
        if (created.get("name") != self.test_name or created.get("domain") != TEST_DOMAIN or
                created.get("ip_add") != TEST_IP):
            raise WorkflowError("POST response does not match the exact temporary policy fields")
        self.event("temporary_policy_created_via_api", policy_id=policy_id)
        self.wait_sqlite_row(policy_id, True)
        return policy_id

    def recover_created_policy(self) -> None:
        baseline_ids = (set(self.document.get("baseline_api_policy_ids", [])) |
                        set(self.document.get("baseline_sqlite_policy_ids", [])))
        ids, rows = self.policy_api_ids()
        matches = [r for r in rows if isinstance(r, dict) and r.get("name") == self.test_name
                   and r.get("domain") == TEST_DOMAIN and r.get("ip_add") == TEST_IP]
        if len(matches) == 1:
            candidate = safe_id(matches[0].get("id"))
            if candidate not in baseline_ids:
                self.policy_id = candidate
                self.document["temporary_policy"] = {"id": candidate, "name": self.test_name,
                    "domain": TEST_DOMAIN, "ip_add": TEST_IP, "category": TEST_CATEGORY,
                    "recovered_after_ambiguous_post": True}
                self.event("ambiguous_post_recovered_exact_policy", policy_id=candidate)
                return
        self.document["ambiguous_post"] = {"exact_match_count": len(matches),
            "new_candidate_ids": sorted(ids - baseline_ids),
            "action": "no unknown row deleted; manual review required"}
        self.save()

    def start_return_helper(self) -> None:
        preflight = (
            "set -eu; test \"$(hostname -s)\" = netpro-test-gateway; "
            "test ! -e /run/netpro-dedicated-rst-return; "
            "test ! -e /run/netpro-dedicated-rst-return.timer; "
            "test \"$(systemctl show -p LoadState --value netpro-dedicated-rst-return-stop.timer)\" = not-found; "
            "test \"$(systemctl show -p LoadState --value netpro-dedicated-rst-return-stop.service)\" = not-found; "
            "test ! -e /run/systemd/transient/netpro-dedicated-rst-return-stop.timer; "
            "test ! -e /run/systemd/transient/netpro-dedicated-rst-return-stop.service; "
            "! systemctl is-active --quiet netpro-dedicated-rst-return-stop.timer"
        )
        self.command(GATEWAY_HOST, "rst_helper_ownership_preflight", preflight,
                     sudo=True, timeout=12)
        # Only after proving both helper state files and named units absent do
        # we take cleanup ownership of a potentially partial start.
        self.rst_started = True
        command = (
            "set -eu; f=" + shlex.quote(RST_HELPER) + "; test -f \"$f\"; "
            "test \"$(sha256sum \"$f\" | cut -d' ' -f1)\" = " + RST_HELPER_SHA256 +
            "; exec /bin/bash \"$f\" start"
        )
        self.command(GATEWAY_HOST, "dedicated_rst_return_start", command, sudo=True, timeout=20)

    def snapshot_split_profile(self, host: str, role: str) -> dict[str, Any]:
        command = "set -eu; test \"$(hostname -s)\" = " + HOSTS[host] + "; ip -o link show dev ens37; ethtool -k ens37"
        _, output, _ = self.command(host, f"split_{role}_read_original_profile", command,
                                    sudo=True, timeout=12, record_output=False)
        mtu_match = re.search(r"\bmtu\s+(\d+)\b", output)
        if not mtu_match:
            raise WorkflowError(f"could not read original ens37 MTU on {role}")
        original: dict[str, Any] = {"role": role, "host": host, "interface": "ens37",
                                    "mtu": int(mtu_match.group(1))}
        required_features = ("tcp-segmentation-offload", "generic-segmentation-offload") if role == "client" else ("generic-receive-offload",)
        for feature in required_features:
            match = re.search(r"^" + re.escape(feature) + r":\s+(on|off)(?:\s|$)", output, re.MULTILINE)
            if not match:
                raise WorkflowError(f"could not read original {feature} on {role}")
            original[feature] = match.group(1)
        return original

    def split_restore_command(self, profile: dict[str, Any]) -> str:
        cmd = ["set -eu", "ip link set dev ens37 mtu " + str(profile["mtu"])]
        for feature in ("tcp-segmentation-offload", "generic-segmentation-offload", "generic-receive-offload"):
            if feature in profile:
                short = {"tcp-segmentation-offload": "tso", "generic-segmentation-offload": "gso",
                         "generic-receive-offload": "gro"}[feature]
                cmd.append("ethtool -K ens37 " + short + " " + profile[feature])
        for feature, expected in profile.items():
            if feature in {"tcp-segmentation-offload", "generic-segmentation-offload", "generic-receive-offload"}:
                cmd.append("ethtool -k ens37 | grep -Eq '^" + feature + ": " + expected + "($|[[:space:]])'")
        cmd.append("ip -o link show dev ens37 | grep -Eq 'mtu " + str(profile["mtu"]) + "([[:space:]]|$)'")
        return "; ".join(cmd)

    def arm_split_restore_timer(self, profile: dict[str, Any]) -> None:
        role = profile["role"]
        unit = f"netpro-snmp-split-{role}-{self.run_id.lower()}"
        profile["timer_unit"] = unit
        preflight = (
            "set -eu; test \"$(systemctl show -p LoadState --value " + unit + ".timer)\" = not-found; "
            "test \"$(systemctl show -p LoadState --value " + unit + ".service)\" = not-found; "
            "test ! -e /run/systemd/transient/" + unit + ".timer; "
            "test ! -e /run/systemd/transient/" + unit + ".service"
        )
        self.command(profile["host"], f"split_{role}_restore_timer_preflight", preflight,
                     sudo=True, timeout=10)
        profile["restore_owned"] = True
        restore = self.split_restore_command(profile)
        arm = ("systemd-run --quiet --collect --unit=" + unit + " --on-active=90s /bin/sh -c " +
               shlex.quote(restore) + "; systemctl is-active --quiet " + unit + ".timer")
        self.command(profile["host"], f"split_{role}_arm_restore_timer", arm,
                     sudo=True, timeout=12)

    def configure_split_profile(self) -> None:
        gateway = self.snapshot_split_profile(GATEWAY_HOST, "gateway")
        client = self.snapshot_split_profile(CLIENT_HOST, "client")
        self.split_profile = {"gateway": gateway, "client": client}
        self.document["split_network_originals"] = {
            role: {key: value for key, value in profile.items() if key != "host"}
            for role, profile in self.split_profile.items()
        }
        self.save()
        # Arm both exact-name fallback restorers before changing either interface.
        self.arm_split_restore_timer(gateway)
        self.arm_split_restore_timer(client)
        self.command(GATEWAY_HOST, "split_gateway_disable_gro", (
            "set -eu; systemctl is-active --quiet " + gateway["timer_unit"] + ".timer; "
            "ethtool -K ens37 gro off; ethtool -k ens37 | grep -Eq '^generic-receive-offload: off($|[[:space:]])'"
        ), sudo=True, timeout=12)
        self.command(CLIENT_HOST, "split_client_set_mtu_and_disable_tso_gso", (
            "set -eu; systemctl is-active --quiet " + client["timer_unit"] + ".timer; "
            "ip link set dev ens37 mtu 128; ethtool -K ens37 tso off gso off; "
            "ip -o link show dev ens37 | grep -Eq 'mtu 128([[:space:]]|$)'; "
            "ethtool -k ens37 | grep -Eq '^tcp-segmentation-offload: off($|[[:space:]])'; "
            "ethtool -k ens37 | grep -Eq '^generic-segmentation-offload: off($|[[:space:]])'"
        ), sudo=True, timeout=12)
        self.event("split_network_profile_applied", client_mtu=128,
                   client_tso_gso="off", gateway_gro="off",
                   auto_restore_seconds=90)

    def restore_split_profile(self) -> None:
        for role in ("client", "gateway"):
            profile = self.split_profile.get(role)
            if not profile or not profile.get("restore_owned"):
                continue
            unit = profile["timer_unit"]
            restore = self.split_restore_command(profile)
            cancel = (
                "if test \"$(systemctl show -p LoadState --value " + unit + ".timer)\" != not-found; then systemctl stop " + unit + ".timer; fi; "
                "if test \"$(systemctl show -p LoadState --value " + unit + ".service)\" != not-found && systemctl is-active --quiet " + unit + ".service; then systemctl stop " + unit + ".service; fi"
            )
            self.command(profile["host"], f"split_{role}_restore_original_profile", restore + "; " + cancel,
                         sudo=True, timeout=15)
            profile["restore_owned"] = False
            self.event("split_original_profile_restored", role=role,
                       mtu=profile["mtu"],
                       offloads={key: value for key, value in profile.items()
                                 if key in {"tcp-segmentation-offload", "generic-segmentation-offload", "generic-receive-offload"}})

    def return_status(self) -> str:
        command = (
            "test \"$(sha256sum " + shlex.quote(RST_HELPER) +
            " | cut -d' ' -f1)\" = " + RST_HELPER_SHA256 +
            " && /bin/bash " + shlex.quote(RST_HELPER) + " status"
        )
        _, stdout, _ = self.command(GATEWAY_HOST, "dedicated_rst_return_status", command,
                                    sudo=True, timeout=12)
        return stdout

    def build_probe_command(self, mode: str, remote_capture: str) -> str:
        if mode not in {"deny", "allow", "deny_split"}:
            raise ValueError("invalid probe mode")
        expected = "deny" if mode == "deny_split" else mode
        remote_parent, _ = os.path.split(remote_capture)
        if remote_parent != "/home/netpro/incoming":
            raise ValueError("capture path escaped the incoming directory")
        expected_cond = (
            '[ "$curl_rc" -eq 0 ] && [ "$http_code" = 200 ]'
            if expected == "allow" else
            '([ "$curl_rc" -eq 35 ] || [ "$curl_rc" -eq 56 ]) && '
            '[ "$http_code" = 000 ] && awk -v t="$elapsed" "BEGIN {exit !(t+0 < 2.5)}"'
        )
        classification = "EXPECTED_ALLOW_200" if expected == "allow" else "EXPECTED_DENY_RST"
        return f"""set -u
test "$(hostname -s)" = netpro-test-client || exit 20
ip -4 -o addr show dev ens37 | grep -Fq '192.168.80.29/24' || exit 21
command -v tcpdump >/dev/null 2>&1 || exit 22
test ! -e {shlex.quote(remote_capture)} || exit 23
capdir=$(mktemp -d /tmp/netpro-active-snmp.XXXXXX) || exit 24
chmod 0700 "$capdir"
pcap="$capdir/client.pcap"
caplog="$capdir/tcpdump.log"
triallog="$capdir/trials.log"
umask 077
: >"$triallog"
timeout -s INT 50s tcpdump -U -Z root -ni ens37 -e -s0 -c 2500 -w "$pcap" 'tcp port 8443 and host 192.168.80.28' >/dev/null 2>"$caplog" &
cap_pid=$!
cleanup_cap() {{
  if [ -n "${{cap_pid:-}}" ]; then kill -INT "$cap_pid" 2>/dev/null || true; wait "$cap_pid" 2>/dev/null || true; fi
  rm -f -- "$pcap" "$caplog"
  rm -f -- "$triallog"
  for n in $(seq 1 20); do rm -f -- "$capdir/curl-$n.err"; done
  rmdir "$capdir" 2>/dev/null || true
}}
trap cleanup_cap EXIT HUP INT TERM
sleep 1
kill -0 "$cap_pid" 2>/dev/null || {{ printf 'capture_failed\\n'; exit 25; }}
start_epoch=$(date +%s)
ok=0
attempted=0
for n in $(seq 1 {TRIAL_COUNT}); do
  elapsed_total=$(( $(date +%s) - start_epoch ))
  if [ "$elapsed_total" -ge 40 ]; then printf 'class=TIME_BUDGET_EXHAUSTED expected={expected} attempted=%s/20 remaining_unattempted=%s\\n' "$attempted" "$((20-attempted))"; break; fi
  result=$(curl --interface 192.168.80.29 --noproxy '*' --silent --show-error --output /dev/null --connect-timeout 2 --max-time 3 --resolve netpro-tap.test:8443:192.168.80.28 --http1.1 --tlsv1.2 --tls-max 1.2 --insecure --header 'Connection: close' --write-out '%{{http_code}}|%{{time_total}}' https://netpro-tap.test:8443/ 2>"$capdir/curl-$n.err")
  curl_rc=$?
  attempted=$((attempted+1))
  http_code=${{result%%|*}}
  elapsed=${{result#*|}}
  trial_class=UNEXPECTED
  if {expected_cond}; then trial_class={classification}; ok=$((ok+1)); fi
  printf 'trial=%s class=%s curl_rc=%s http=%s elapsed=%s\\n' "$n" "$trial_class" "$curl_rc" "$http_code" "$elapsed" | tee -a "$triallog"
  if [ "$trial_class" = UNEXPECTED ]; then
    if [ "$curl_rc" -eq 28 ]; then detail=TIMEOUT_NOT_A_PASS; elif [ "$curl_rc" -eq 0 ]; then detail=HTTP_RESPONSE_NOT_EXPECTED; else detail=UNEXPECTED_TRANSPORT_RESULT; fi
    printf 'detail=%s\\n' "$detail" | tee -a "$triallog"
    break
  fi
done
sleep 1
kill -INT "$cap_pid" 2>/dev/null || true
cap_rc=0
wait "$cap_pid" || cap_rc=$?
cap_pid=
if [ ! -s "$pcap" ]; then printf 'capture_failed rc=%s\\n' "$cap_rc"; exit 26; fi
printf 'tcpdump_capture_stats_begin\\n'
cat "$caplog"
printf 'tcpdump_capture_stats_end\\n'
install -o netpro -g netpro -m 0644 "$pcap" {shlex.quote(remote_capture)} || exit 27
printf 'capture_remote=%s capture_sha256=' {shlex.quote(remote_capture)}
sha256sum {shlex.quote(remote_capture)}
printf 'trial_summary mode={expected} expected=%s/20 attempted=%s/20 unattempted=%s\\n' "$ok" "$attempted" "$((20-attempted))"
tcpdump -nn -e -S -r {shlex.quote(remote_capture)} 2>/dev/null | head -30
rst_to_client=$(tcpdump -nn -r {shlex.quote(remote_capture)} 'tcp[tcpflags] & tcp-rst != 0 and dst host 192.168.80.29' 2>/dev/null | wc -l | tr -d ' ')
printf 'client_directed_rst_packets=%s\n' "$rst_to_client"
if [ "{expected}" = deny ]; then [ "$rst_to_client" -ge {TRIAL_COUNT} ] || {{ printf 'capture_incomplete_rst_evidence\n'; exit 28; }}; else [ "$rst_to_client" -eq 0 ] || {{ printf 'unexpected_rst_in_allow_capture\n'; exit 29; }}; fi
printf 'trial_output_begin\\n'
cat "$triallog"
printf 'trial_output_end\\n'
rm -f -- "$pcap" "$caplog" "$triallog"
for n in $(seq 1 20); do rm -f -- "$capdir/curl-$n.err"; done
rmdir "$capdir"
trap - EXIT HUP INT TERM
[ "$ok" -eq {TRIAL_COUNT} ]"""

    def run_probe(self, mode: str) -> bool:
        remote_capture = f"/home/netpro/incoming/active-snmp-{mode}-{self.run_id}.pcap"
        self.capture_paths.append(remote_capture)
        command = self.build_probe_command(mode, remote_capture)
        status, stdout, stderr = self.command(
            CLIENT_HOST, f"tls_{mode}_probe", command, sudo=True, timeout=60,
            allow_failure=True,
        )
        match = re.search(r"capture_remote=(/home/netpro/incoming/[A-Za-z0-9._-]+)", stdout)
        if match:
            capture_path = match.group(1)
            if capture_path != remote_capture:
                raise WorkflowError("client reported an unexpected capture destination")
            local_path = self.evidence_dir / f"active-snmp-{mode}-{self.run_id}.pcap"
            self.download_capture(capture_path, local_path)
        self.document["outcomes"][mode] = {
            "exit_status": status,
            "stdout_tail": redact(stdout[-12000:]),
            "stderr": redact(stderr[-2000:]),
            "passed_all_20": status == 0,
        }
        if self.split_clienthello and 'local_path' in locals() and local_path.exists():
            split_result = validate_split_clienthello_pcap(local_path, TRIAL_COUNT)
            self.document["outcomes"][mode]["segmentation_validation"] = split_result
        self.save()
        if self.split_clienthello and not self.document["outcomes"][mode].get("segmentation_validation", {}).get("passed"):
            return False
        return status == 0

    def download_capture(self, remote_path: str, local_path: Path) -> None:
        expected_hash_status, expected_hash_output, _ = self.command(
            CLIENT_HOST, "capture_sha256", "sha256sum " + shlex.quote(remote_path),
            sudo=True, timeout=10,
        )
        if expected_hash_status != 0:
            raise WorkflowError("could not hash remote capture")
        expected_hash = expected_hash_output.split()[0]
        if not re.fullmatch(r"[a-fA-F0-9]{64}", expected_hash):
            raise WorkflowError("remote capture hash is malformed")
        if local_path.exists():
            raise WorkflowError("local capture destination already exists")
        digest = hashlib.sha256()
        size = 0
        sftp = self.clients[CLIENT_HOST].open_sftp()
        try:
            with sftp.open(remote_path, "rb") as source, local_path.open("xb") as destination:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    destination.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
        finally:
            sftp.close()
        local_hash = digest.hexdigest()
        self.document["captures"].append({
            "remote_path": remote_path,
            "local_path": str(local_path.resolve()),
            "bytes": size,
            "sha256": local_hash,
            "hash_matches": local_hash == expected_hash,
        })
        self.save()
        if local_hash != expected_hash:
            raise WorkflowError("downloaded capture SHA-256 differs from remote")
        self.command(CLIENT_HOST, "capture_remote_cleanup",
                     "rm -f -- " + shlex.quote(remote_path) + " && test ! -e " + shlex.quote(remote_path),
                     sudo=True, timeout=10)
        self.event("capture_hash_verified_and_remote_removed", remote_path=remote_path,
                   sha256=local_hash)

    def delete_policy_exactly(self) -> None:
        if not self.policy_id or self.policy_deleted:
            return
        existing_ids, rows = self.policy_api_ids()
        if self.policy_id in existing_ids:
            # Refuse if the exact row no longer has the content created by this run.
            matches = [r for r in rows if r.get("id") == self.policy_id]
            if (len(matches) != 1 or matches[0].get("name") != self.test_name or
                    matches[0].get("domain") != TEST_DOMAIN or matches[0].get("ip_add") != TEST_IP):
                raise WorkflowError("exact temporary policy changed; refusing delete")
            sqlite_exact = self.sqlite(
                "SELECT id, domain, ip_address FROM policies WHERE id = ?",
                (self.policy_id,))
            if len(sqlite_exact) > 1 or (sqlite_exact and
                    (sqlite_exact[0].get("id") != self.policy_id or
                     sqlite_exact[0].get("domain") != TEST_DOMAIN or
                     sqlite_exact[0].get("ip_address") != TEST_IP)):
                raise WorkflowError("SQLite has a conflicting temporary-policy row; refusing delete")
            response = self.api("DELETE", policy_id=self.policy_id)
            deleted = response.get("deletedBlockedList") if isinstance(response, dict) else None
            if not isinstance(deleted, dict) or safe_id(deleted.get("id")) != self.policy_id:
                raise WorkflowError("DELETE response did not confirm the exact temporary policy ID")
        self.wait_sqlite_row(self.policy_id, False)
        after_api, _ = self.policy_api_ids()
        if after_api != set(self.document["baseline_api_policy_ids"]):
            raise WorkflowError("Backend API policy IDs differ from the original baseline after delete")
        after_sqlite = {safe_policy_key(row.get("id")) for row in self.sqlite("SELECT id FROM policies ORDER BY id;")}
        if after_sqlite != set(self.document["baseline_sqlite_policy_ids"]):
            raise WorkflowError("Policy SQLite IDs differ from the original baseline after delete")
        self.policy_deleted = True
        self.event("temporary_policy_deleted_and_baseline_restored", policy_id=self.policy_id)

    def verify_return_path_absent(self) -> None:
        verify = ("set -eu; ip -o link show dev ens38; "
                  "! ip -o link show dev ens38 | grep -q PROMISC; "
                  "ip -o link show dev ens38 | grep -q 'state DOWN'; "
                  "! ip -o link show dev ens38 | grep -q '<[^>]*UP'; "
                  "! tc qdisc show dev ens38 | grep -q clsact; "
                  "! tc filter show dev ens38 ingress | grep -Eq 'handle (201|202|203)'")
        self.command(GATEWAY_HOST, "verify_rst_return_path_absent", verify, sudo=True, timeout=12)

    def cleanup_return_helper(self) -> None:
        if not self.rst_started:
            return
        status_cmd = "test \"$(sha256sum " + shlex.quote(RST_HELPER) + " | cut -d' ' -f1)\" = " + RST_HELPER_SHA256 + " && /bin/bash " + shlex.quote(RST_HELPER) + " status"
        status, stdout, stderr = self.command(GATEWAY_HOST, "rst_helper_status_for_cleanup", status_cmd,
                                             sudo=True, timeout=12, allow_failure=True)
        if status == 0 and "state=active" in stdout:
            stop_cmd = "test \"$(sha256sum " + shlex.quote(RST_HELPER) + " | cut -d' ' -f1)\" = " + RST_HELPER_SHA256 + " && /bin/bash " + shlex.quote(RST_HELPER) + " stop"
            self.command(GATEWAY_HOST, "rst_helper_exact_cleanup", stop_cmd, sudo=True, timeout=15)
            self.verify_return_path_absent()
        elif status == 0 and "state=absent" in stdout and "timer=inactive" in stdout:
            # The helper's own 60-second timer completed its scoped cleanup.
            self.verify_return_path_absent()
            self.event("rst_helper_auto_cleanup_verified")
        else:
            self.document["cleanup"].append({"step": "rst_helper", "status": "needs_review",
                                               "stdout": redact(stdout[-3000:]),
                                               "stderr": redact(stderr[-1000:])})
            self.save()
            raise WorkflowError("RST helper state could not be safely classified during cleanup")

    def cleanup_gateway_server(self) -> None:
        if not self.server_started:
            return
        command = (
            "set -eu; f=" + shlex.quote(GATEWAY_SERVER) + "; test \"$(sha256sum \"$f\" | cut -d' ' -f1)\" = " +
            GATEWAY_SERVER_SHA256 + "; exec /bin/bash \"$f\" stop"
        )
        self.command(GATEWAY_HOST, "gateway_server_exact_cleanup", command, sudo=True, timeout=15)
        self.server_started = False

    def cleanup(self) -> None:
        cleanup_errors: list[str] = []
        try:
            self.restore_split_profile()
        except Exception as exc:
            cleanup_errors.append(f"split profile restoration: {type(exc).__name__}")
        try:
            self.delete_policy_exactly()
        except Exception as exc:
            cleanup_errors.append(f"policy deletion/verification: {type(exc).__name__}")
        try:
            self.cleanup_return_helper()
        except Exception as exc:
            cleanup_errors.append(f"RST helper cleanup: {type(exc).__name__}")
        try:
            self.cleanup_gateway_server()
        except Exception as exc:
            cleanup_errors.append(f"Gateway listener cleanup: {type(exc).__name__}")
        # Preserve any remote capture not transferred and hash-verified.
        self.document["cleanup"].extend(
            {"time_utc": utc_now(), "status": "error", "step": message}
            for message in cleanup_errors
        )
        self.document["cleanup"].append({
            "time_utc": utc_now(),
            "status": "needs_review" if cleanup_errors else "completed_or_auto_verified",
        })
        for client in self.clients.values():
            client.close()
        self.save()

    def execute(self) -> int:
        final_status = 1
        try:
            self.connect_all()
            self.baseline()
            self.start_gateway_server()
            if self.split_clienthello:
                self.configure_split_profile()
            policy_id = self.create_policy()
            self.start_return_helper()
            deny_ok = self.run_probe("deny")
            self.document["outcomes"]["rst_filter_status_after_deny"] = redact(self.return_status())
            self.save()
            if not deny_ok:
                raise WorkflowError("deny probe did not achieve all 20 expected fast RST denials")
            self.delete_policy_exactly()
            self.document["outcomes"]["rst_filter_status_after_delete"] = redact(self.return_status())
            self.save()
            allow_ok = self.run_probe("allow")
            if not allow_ok:
                raise WorkflowError("allow-after-delete probe did not achieve all 20 HTTP 200 responses")
            self.event("active_baseline_workflow_passed", policy_id=policy_id)
            final_status = 0
        except Exception as exc:
            self.document["failure"] = {"time_utc": utc_now(), "type": type(exc).__name__,
                                         "message": redact(str(exc))[:1000]}
            self.save()
        finally:
            try:
                self.cleanup()
            except Exception as exc:
                self.document["cleanup"].append({"status": "error", "step": type(exc).__name__})
                final_status = 1
                self.save()
        if self.document.get("failure") or any(c.get("status") == "error" for c in self.document["cleanup"]):
            final_status = 1
        print(f"Evidence: {self.evidence_path}")
        return final_status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-active-test", action="store_true",
                        help="execute the staged, bounded policy/RST test; omitted means plan-only")
    parser.add_argument("--known-hosts", type=Path, default=Path.home() / ".ssh" / "known_hosts")
    parser.add_argument("--split-clienthello", action="store_true",
                        help="temporarily force TCP segmentation and verify both captures")
    parser.add_argument("--evidence-dir", type=Path,
                        default=Path(__file__).resolve().parent / "evidence")
    args = parser.parse_args()
    if not args.execute_active_test:
        print("Plan only. Review this file and the approved test plan; no SSH, API, or VM operation was attempted.")
        print(f"Targets: {POLICY_HOST}, {BACKEND_HOST}, {GATEWAY_HOST}, {CLIENT_HOST}")
        print(f"Evidence directory when explicitly run: {args.evidence_dir}")
        return 0
    password = getpass.getpass("Lab SSH/sudo password (kept in memory only): ")
    if not password:
        print("Empty password; refusing active workflow.")
        return 2
    workflow = ActiveBaseline(password, args.evidence_dir, args.known_hosts,
                              split_clienthello=args.split_clienthello)
    return workflow.execute()


if __name__ == "__main__":
    raise SystemExit(main())
