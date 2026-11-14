#!/usr/bin/env python3
"""Read-only SSH inventory helper for the SNMP/QUIC lab preflight.

No connections are made unless this script is run. Existing host keys are
required; unknown keys are rejected. Passwords are prompted or read from
NETPRO_LAB_PASSWORD and are never written to evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import getpass
import json
import os
import posixpath
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    import paramiko
except ImportError as exc:
    raise SystemExit("Missing dependency: install paramiko in the active Python environment.") from exc


HOSTS = {
    "192.168.31.31": "policy-server-vm",
    "192.168.31.32": "kafka-broker-vm",
    "192.168.31.33": "npb-vm",
    "192.168.31.34": "packet-generator-vm",
    "192.168.31.35": "backend-vm",
    "192.168.31.36": "frontend-vm",
    "192.168.31.37": "netpro-test-gateway",
    "192.168.31.38": "netpro-virtual-tap",
    "192.168.31.39": "netpro-test-client",
}
TRUSTED_HOST_ALIASES = {
    "192.168.31.34": "192.168.31.134",
    "192.168.31.36": "192.168.31.136",
}

# Inventory only: shell strings are fixed here and cannot be supplied by stdin.
INVENTORY_COMMANDS = {
    "hostname": "hostnamectl --static 2>/dev/null || hostname",
    "os": "cat /etc/os-release 2>/dev/null",
    "uptime": "uptime",
    "interfaces": "ip -brief address",
    "routes": "ip route show",
    "services": "systemctl --no-pager --type=service --state=running",
    "disk": "df -h",
}
COMMAND_TIMEOUT = 12
CONNECT_TIMEOUT = 8


def run_inventory(client: paramiko.SSHClient, sudo: bool, password: str | None, timeout: int) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, command in INVENTORY_COMMANDS.items():
        actual = command
        if sudo:
            # The inventory commands are read-only. Sudo receives its password
            # over the process channel, never as part of the command string.
            actual = "sudo -S -p '' -- sh -c " + quote(command)
        stdin, stdout, stderr = client.exec_command(actual, timeout=timeout)
        if sudo:
            stdin.write((password or "") + "\n")
            stdin.flush()
        stdin.close()
        try:
            out = stdout.read().decode("utf-8", "replace")
            err = stderr.read().decode("utf-8", "replace")
            status = stdout.channel.recv_exit_status()
        except Exception:
            out, err, status = "", "command read failed", 255
        # Avoid returning terminal escape sequences or credential-like text.
        result[name] = {"exit_status": status, "stdout": out[:24000], "stderr": redact(err[:4000])}
    return result


def quote(value: str) -> str:
    """POSIX single-quote a fixed inventory command."""
    return "'" + value.replace("'", "'\"'\"'") + "'"


def redact(value: str) -> str:
    value = re.sub(r"(?i)(password|passwd|community|token|secret)(\s*[=:]\s*)\S+", r"\1\2[REDACTED]", value)
    return value


def connect_verified(ip: str, user: str, password: str, known_hosts: Path,
                     trusted_host_alias: str | None = None,
                     timeout: int = COMMAND_TIMEOUT) -> tuple[paramiko.SSHClient, str]:
    """Open a password-only SSH connection with strict known-host and hostname checks.

    This is shared by the inventory CLI and explicitly authorized lab workflows.
    It never accepts unknown host keys, probes local keys/agents, or changes
    known_hosts. A remapped host alias is accepted only from the fixed map above
    and its exact already-trusted key is copied in memory for this connection.
    """
    expected = HOSTS.get(ip)
    if expected is None:
        raise ValueError("host is not in the fixed lab map")
    client = paramiko.SSHClient()
    client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    if trusted_host_alias is not None:
        if TRUSTED_HOST_ALIASES.get(ip) != trusted_host_alias:
            raise ValueError("trusted host alias does not match the fixed host map")
        trusted_keys = client.get_host_keys().lookup(trusted_host_alias)
        if not trusted_keys:
            raise ValueError("specified known_hosts alias has no trusted keys")
        host_keys = client.get_host_keys()
        host_keys.pop(ip, None)
        for key_type, key in trusted_keys.items():
            host_keys.add(ip, key_type, key)
    try:
        client.connect(
            ip,
            username=user,
            password=password,
            timeout=CONNECT_TIMEOUT,
            banner_timeout=CONNECT_TIMEOUT,
            auth_timeout=CONNECT_TIMEOUT,
            look_for_keys=False,
            allow_agent=False,
        )
        _, stdout, _ = client.exec_command(
            "hostnamectl --static 2>/dev/null || hostname", timeout=timeout
        )
        lines = stdout.read().decode("utf-8", "replace").strip().splitlines()
        actual = lines[0].strip() if lines else ""
        if actual != expected:
            raise ValueError(f"remote hostname mismatch for {ip}")
        return client, actual
    except Exception:
        client.close()
        raise


def run_remote_command(client: paramiko.SSHClient, command: str,
                       sudo_password: str | None = None,
                       timeout: int = COMMAND_TIMEOUT) -> tuple[int, str, str]:
    """Run an explicit command and return status/redacted stdout/stderr."""
    actual = command
    if sudo_password is not None:
        actual = "sudo -S -p '' -- sh -c " + quote(command)
    stdin, stdout, stderr = client.exec_command(actual, timeout=timeout)
    if sudo_password is not None:
        stdin.write(sudo_password + "\n")
        stdin.flush()
    stdin.close()
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    status = stdout.channel.recv_exit_status()
    return status, out[:24000], redact(err[:4000])


def upload_file(sftp: Any, local_path: Path, remote_path: str,
                allowed_parent: str = "/home/netpro/incoming") -> dict[str, Any]:
    """Upload a bounded non-secret-looking file without replacing a remote file."""
    if not local_path.is_file():
        raise FileNotFoundError("upload source is not a regular file")
    if local_path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError("upload source exceeds the 128 MiB limit")
    lowered_name = local_path.name.lower()
    secret_names = (".env", "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa", "credential", "password", "passwd", "secret")
    if (lowered_name.startswith(".env") or lowered_name.endswith(".env") or
        any(token in lowered_name for token in secret_names[1:]) or lowered_name.endswith(
        (".pem", ".key", ".p12", ".pfx")
    )):
        raise ValueError("upload source filename is credential-like")
    credential_line = re.compile(
        rb"(?im)^\s*(?:password|passwd|community|api[_-]?key|token|secret)\s*[:=]\s*['\"]?[^\s'\"]{6,}"
    )
    tail = b""
    with local_path.open("rb") as source:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            window = tail + chunk
            if b"-----BEGIN " in window and b" PRIVATE KEY-----" in window:
                raise ValueError("upload source appears to contain a private key")
            if credential_line.search(window):
                raise ValueError("upload source appears to contain a plaintext credential")
            tail = window[-256:]

    parent, basename = posixpath.split(remote_path)
    parent = parent or "/"
    if posixpath.normpath(parent) != posixpath.normpath(allowed_parent) or basename in ("", ".", ".."):
        raise ValueError("remote destination must be a new direct child of the user's incoming directory")
    parent_attrs = sftp.stat(parent)
    if not stat.S_ISDIR(parent_attrs.st_mode):
        raise NotADirectoryError("remote upload parent is not a directory")
    if sftp.normalize(parent) != posixpath.normpath(parent):
        raise ValueError("remote upload parent resolves through a symlink")
    if basename in sftp.listdir(parent):
        raise FileExistsError("remote destination already exists")
    temporary_path = posixpath.join(parent, f".{basename}.codex-upload-{uuid4().hex}.tmp")
    digest = hashlib.sha256()
    sent = 0
    try:
        with local_path.open("rb") as source, sftp.open(temporary_path, "wx") as destination:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                destination.write(chunk)
                digest.update(chunk)
                sent += len(chunk)
                if sent > 128 * 1024 * 1024:
                    raise ValueError("upload source grew beyond the 128 MiB limit")
        if basename in sftp.listdir(parent):
            raise FileExistsError("remote destination appeared during upload")
        # Standard SFTP rename fails if the destination already exists.
        sftp.rename(temporary_path, remote_path)
    except Exception:
        try:
            sftp.remove(temporary_path)
        except Exception:
            pass
        raise
    return {"local_path": str(local_path.resolve()), "remote_path": remote_path,
            "bytes": sent, "sha256": digest.hexdigest()}


def upload_directory(sftp: Any, local_root: Path, remote_root: str,
                     allowed_parent: str = "/home/netpro/incoming") -> dict[str, Any]:
    """Upload a directory tree into a new remote directory, excluding bytecode."""
    if local_root.is_symlink() or not local_root.is_dir():
        raise ValueError("upload directory must be a real local directory, not a symlink")
    parent, basename = posixpath.split(remote_root)
    parent = parent or "/"
    if posixpath.normpath(parent) != posixpath.normpath(allowed_parent) or basename in ("", ".", ".."):
        raise ValueError("remote bundle must be a new direct child of the user's incoming directory")
    parent_attrs = sftp.stat(parent)
    if not stat.S_ISDIR(parent_attrs.st_mode) or sftp.normalize(parent) != posixpath.normpath(parent):
        raise ValueError("remote incoming directory is missing or resolves through a symlink")
    if basename in sftp.listdir(parent):
        raise FileExistsError("remote bundle destination already exists")

    sftp.mkdir(remote_root, 0o700)
    created_directories = [remote_root]
    uploaded_files: list[str] = []
    file_records: list[dict[str, Any]] = []
    try:
        for current, dirnames, filenames in os.walk(local_root, topdown=True, followlinks=False):
            current_path = Path(current)
            kept_dirs: list[str] = []
            for dirname in dirnames:
                local_child = current_path / dirname
                if local_child.is_symlink():
                    raise ValueError("symbolic links are not allowed in upload bundles")
                if dirname == "__pycache__":
                    continue
                kept_dirs.append(dirname)
            dirnames[:] = kept_dirs
            relative = current_path.relative_to(local_root)
            remote_current = remote_root if str(relative) == "." else posixpath.join(remote_root, *relative.parts)
            for dirname in dirnames:
                remote_child = posixpath.join(remote_current, dirname)
                sftp.mkdir(remote_child, 0o700)
                created_directories.append(remote_child)
            for filename in filenames:
                local_file = current_path / filename
                if local_file.is_symlink():
                    raise ValueError("symbolic links are not allowed in upload bundles")
                if local_file.suffix.lower() == ".pyc":
                    continue
                remote_file = posixpath.join(remote_current, filename)
                record = upload_file(sftp, local_file, remote_file, allowed_parent=remote_current)
                uploaded_files.append(remote_file)
                file_records.append(record)
    except Exception:
        for remote_file in reversed(uploaded_files):
            try:
                sftp.remove(remote_file)
            except Exception:
                pass
        for remote_dir in reversed(created_directories):
            try:
                sftp.rmdir(remote_dir)
            except Exception:
                pass
        raise
    return {"local_path": str(local_root.resolve()), "remote_path": remote_root,
            "file_count": len(file_records), "files": file_records}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", default=os.environ.get("NETPRO_LAB_USER", "netpro"))
    parser.add_argument("--known-hosts", type=Path, default=Path.home() / ".ssh" / "known_hosts")
    parser.add_argument("--evidence-dir", type=Path, default=Path(__file__).resolve().parent / "evidence")
    parser.add_argument("--timeout", type=int, default=COMMAND_TIMEOUT, help="per-command timeout in seconds (1-60)")
    parser.add_argument("--sudo", action="store_true", help="run inventory or an explicit command via sudo -S")
    parser.add_argument("--host", choices=HOSTS, action="append", help="select a mapped host; repeatable for inventory")
    parser.add_argument("--trusted-host-alias", choices=tuple(TRUSTED_HOST_ALIASES.values()),
                        help="trust this exact existing known_hosts key for the matching remapped VM")
    parser.add_argument("--command", help="run one explicit command on the single --host selected")
    file_group = parser.add_mutually_exclusive_group()
    file_group.add_argument("--download", nargs=2, metavar=("REMOTE_PATH", "LOCAL_PATH"),
                        help="download one remote file over SFTP to a new local file; never overwrites")
    file_group.add_argument("--upload", nargs=2, metavar=("LOCAL_PATH", "REMOTE_PATH"),
                            help="upload one bounded non-secret file by SFTP to a new remote file; never overwrites")
    file_group.add_argument("--upload-dir", nargs=2, metavar=("LOCAL_DIR", "REMOTE_DIR"),
                            help="upload a directory bundle into a new remote directory; excludes .pyc and rejects symlinks")
    ops_group = parser.add_mutually_exclusive_group()
    ops_group.add_argument("--execute-operations", action="store_true",
                           help="read a JSON array of {host, command} objects from stdin and execute those commands")
    ops_group.add_argument("--operations-file", type=Path,
                           help="read a JSON array of {host, command} objects from a file")
    args = parser.parse_args()
    if not 1 <= args.timeout <= 60:
        parser.error("--timeout must be between 1 and 60 seconds")
    if args.command is not None and (args.execute_operations or args.operations_file or args.download or args.upload or args.upload_dir or len(args.host or []) != 1):
        parser.error("--command requires exactly one --host and cannot be combined with other action modes")
    if (args.download or args.upload or args.upload_dir) and (args.execute_operations or args.operations_file or args.command or len(args.host or []) != 1 or args.sudo):
        parser.error("--download/--upload requires exactly one --host; it cannot be combined with commands, operations, or --sudo")
    if args.download and (not args.download[0].startswith("/") or "\x00" in args.download[0]):
        parser.error("--download REMOTE_PATH must be an absolute POSIX path")
    if args.download and not Path(args.download[1]).parent.is_dir():
        parser.error("--download LOCAL_PATH parent directory must already exist")
    if args.upload and not args.upload[1].startswith("/"):
        parser.error("--upload REMOTE_PATH must be an absolute POSIX path")
    if args.upload and (not Path(args.upload[0]).is_file() or Path(args.upload[0]).stat().st_size > 128 * 1024 * 1024):
        parser.error("--upload LOCAL_PATH must be a regular file no larger than 128 MiB")
    if args.upload_dir and (not Path(args.upload_dir[0]).is_dir() or Path(args.upload_dir[0]).is_symlink()):
        parser.error("--upload-dir LOCAL_DIR must be a real local directory, not a symlink")
    if args.upload_dir and not args.upload_dir[1].startswith("/"):
        parser.error("--upload-dir REMOTE_DIR must be an absolute POSIX path")
    if (args.execute_operations or args.operations_file) and args.host:
        parser.error("operations modes take hosts from JSON; do not also pass --host")
    if args.trusted_host_alias and (len(args.host or []) != 1 or
                                    TRUSTED_HOST_ALIASES.get(args.host[0]) != args.trusted_host_alias):
        parser.error("--trusted-host-alias is valid only with its corresponding single mapped --host")
    if not args.known_hosts.is_file():
        parser.error(f"known_hosts file does not exist: {args.known_hosts}")

    password = os.environ.get("NETPRO_LAB_PASSWORD")
    if password is None:
        password = getpass.getpass("Lab SSH password (not saved): ")
    operations: list[dict[str, str]] | None = None
    if args.execute_operations or args.operations_file:
        try:
            if args.operations_file:
                loaded = json.loads(args.operations_file.read_text(encoding="utf-8"))
            else:
                loaded = json.load(sys.stdin)
        except (json.JSONDecodeError, OSError, UnicodeError) as exc:
            parser.error(f"could not read operations JSON ({type(exc).__name__})")
        if not isinstance(loaded, list) or not loaded:
            parser.error("operations stdin must be a non-empty JSON array")
        operations = []
        for index, op in enumerate(loaded):
            if not isinstance(op, dict) or set(op) != {"host", "command"}:
                parser.error(f"operation {index} must contain exactly host and command")
            if op["host"] not in HOSTS or not isinstance(op["command"], str) or not op["command"].strip():
                parser.error(f"operation {index} has an unknown host or empty command")
            if len(op["command"]) > 4000 or "\x00" in op["command"]:
                parser.error(f"operation {index} command is too long or contains a NUL")
            operations.append({"host": op["host"], "command": op["command"]})
    jobs: list[tuple[str, str | None, tuple[str, str] | None, tuple[str, str] | None, tuple[str, str] | None]] = (
        [(args.host[0], args.command, None, None, None)] if args.command is not None else
        [(args.host[0], None, tuple(args.download), None, None)] if args.download else
        [(args.host[0], None, None, tuple(args.upload), None)] if args.upload else
        [(args.host[0], None, None, None, tuple(args.upload_dir))] if args.upload_dir else
        [(op["host"], op["command"], None, None, None) for op in operations]
        if operations is not None else [(ip, None, None, None, None) for ip in (args.host or list(HOSTS))]
    )
    results: list[dict[str, Any]] = []
    for ip, requested_command, requested_download, requested_upload, requested_upload_dir in jobs:
        expected_name = HOSTS[ip]
        item: dict[str, Any] = {"host": ip, "expected_hostname": expected_name}
        client: paramiko.SSHClient | None = None
        try:
            if args.trusted_host_alias:
                item["trusted_host_alias"] = args.trusted_host_alias
            client, actual_hostname = connect_verified(
                ip, args.user, password, args.known_hosts,
                args.trusted_host_alias, args.timeout,
            )
            item["connected"] = True
            item["actual_hostname"] = actual_hostname
            item["hostname_matches"] = True
            if requested_download is not None:
                remote_path, local_path = requested_download
                sftp = client.open_sftp()
                try:
                    attrs = sftp.stat(remote_path)
                    if attrs.st_size > 128 * 1024 * 1024:
                        raise ValueError("remote file exceeds the 128 MiB download limit")
                    digest = hashlib.sha256()
                    transferred = 0
                    # Exclusive creation prevents silently replacing a local file.
                    local_file = Path(local_path)
                    created_local = False
                    try:
                        with local_file.open("xb") as destination:
                            created_local = True
                            with sftp.open(remote_path, "rb") as source:
                                while True:
                                    chunk = source.read(1024 * 1024)
                                    if not chunk:
                                        break
                                    destination.write(chunk)
                                    digest.update(chunk)
                                    transferred += len(chunk)
                    except Exception:
                        if created_local:
                            local_file.unlink(missing_ok=True)
                        raise
                    item["download"] = {"remote_path": remote_path, "local_path": str(Path(local_path).resolve()),
                                         "bytes": transferred, "sha256": digest.hexdigest()}
                finally:
                    sftp.close()
            elif requested_upload is not None:
                local_path, remote_path = requested_upload
                sftp = client.open_sftp()
                try:
                    item["upload"] = upload_file(
                        sftp, Path(local_path), remote_path,
                        posixpath.join("/home", args.user, "incoming"),
                    )
                finally:
                    sftp.close()
            elif requested_upload_dir is not None:
                local_root, remote_root = requested_upload_dir
                sftp = client.open_sftp()
                try:
                    item["upload_dir"] = upload_directory(
                        sftp, Path(local_root), remote_root,
                        posixpath.join("/home", args.user, "incoming"),
                    )
                finally:
                    sftp.close()
            elif requested_command is None:
                item["inventory"] = run_inventory(client, args.sudo, password, args.timeout)
            else:
                command = requested_command
                if args.sudo:
                    command = "sudo -S -p '' -- sh -c " + quote(command)
                stdin, stdout, stderr = client.exec_command(command, timeout=args.timeout)
                if args.sudo:
                    stdin.write(password + "\n")
                    stdin.flush()
                stdin.close()
                output = stdout.read().decode("utf-8", "replace")[:24000]
                error = stderr.read().decode("utf-8", "replace")[:4000]
                item["operation"] = {"command": requested_command, "exit_status": stdout.channel.recv_exit_status(),
                                     "stdout": redact(output), "stderr": redact(error)}
            if requested_command is None:
                if requested_download is None and requested_upload is None and requested_upload_dir is None:
                    reported = item.get("inventory", {}).get("hostname", {}).get("stdout", "").strip().splitlines()
                    if reported:
                        item["actual_hostname"] = reported[0].strip()
                        item["hostname_matches"] = item["actual_hostname"] == expected_name
            elif "operation" in item and item["operation"]["exit_status"] != 0:
                item["error"] = "remote command returned a non-zero exit status"
        except TimeoutError:
            item.update(error="remote operation timed out")
        except paramiko.BadHostKeyException:
            item.update(connected=False, error="host key mismatch; verify out of band")
        except paramiko.SSHException as exc:
            item.update(connected=False, error=f"SSH rejected or unavailable ({type(exc).__name__})")
        except OSError as exc:
            if item.get("connected"):
                item.update(error=f"local or remote operation failed ({type(exc).__name__})")
            else:
                item.update(connected=False, error=f"connection failed ({type(exc).__name__})")
        except ValueError as exc:
            item.update(error=f"operation rejected ({type(exc).__name__})")
        finally:
            if client is not None:
                client.close()
        results.append(item)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = args.evidence_dir / f"evidence-{timestamp}.json"
    document = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "download" if args.download else "upload-bundle" if args.upload_dir else "upload" if args.upload else "explicit-commands" if operations is not None or args.command is not None else "read-only-inventory",
        "user": args.user,
        "known_hosts": str(args.known_hosts),
        "hosts": results,
    }
    evidence_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    summary = [
        {"host": row["host"], "expected": row["expected_hostname"],
         "trusted_host_alias": row.get("trusted_host_alias"),
         "actual": row.get("actual_hostname"), "connected": row.get("connected", False),
         "hostname_matches": row.get("hostname_matches", False),
         "operation_exit_status": row.get("operation", {}).get("exit_status"),
         "sha256": row.get("download", row.get("upload", {})).get("sha256"),
         "upload_file_count": row.get("upload_dir", {}).get("file_count"), "error": row.get("error")}
        for row in results
    ]
    print(json.dumps({"evidence": str(evidence_path), "summary": summary}, indent=2))
    return 0 if all(row.get("connected") and row.get("hostname_matches")
                    and row.get("operation", {}).get("exit_status", 0) == 0
                    and "error" not in row for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
