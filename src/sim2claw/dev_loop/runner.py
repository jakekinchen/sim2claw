"""Exact-identity test execution with durable receipts and process leases."""

from __future__ import annotations

import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

from ..learning_factory_artifacts import atomic_write_json, sha256_file
from .lifecycle import (
    DevLoopLifecycleError,
    build_process_lease,
    build_task_contract,
    build_test_identity,
    build_test_receipt,
    complete_process_lease,
    is_test_receipt_reusable,
    mark_missing_process_orphaned,
    verify_process_lease,
)


RUN_SCHEMA = "sim2claw.dev_loop_test_run.v1"
_COUNT_PATTERN = re.compile(
    r"(?P<count>\d+)\s+(?P<label>passed|failed|errors?|skipped|xfailed|xpassed)\b"
)


class DevLoopRunnerError(RuntimeError):
    """A leased test run could not start, finish, or reuse exact evidence."""


def _load_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DevLoopRunnerError(f"cannot read test-run artifact {path}: {error}") from error
    if not isinstance(value, dict):
        raise DevLoopRunnerError(f"test-run artifact is not an object: {path}")
    return value


def _counts(log_text: str) -> dict[str, int]:
    counts = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
    }
    for match in _COUNT_PATTERN.finditer(log_text):
        label = match.group("label")
        if label == "error":
            label = "errors"
        counts[label] = max(counts[label], int(match.group("count")))
    return counts


def _relative_to_repo(repo_root: Path, path: Path, *, label: str) -> str:
    root = repo_root.resolve()
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise DevLoopRunnerError(f"{label} escapes repository")
    return resolved.relative_to(root).as_posix()


def run_test_with_receipt(
    *,
    repo_root: Path,
    command: Sequence[str],
    relevant_paths: Sequence[Path | str],
    receipt_root: Path,
    tier: str,
    wall_time_seconds: int = 3600,
) -> dict[str, Any]:
    """Execute once per exact identity, or reuse a matching passing receipt."""

    root = repo_root.resolve()
    if not command or not tier.strip() or wall_time_seconds < 1:
        raise DevLoopRunnerError("test run requires command, tier, and a positive wall time")
    output_root = receipt_root if receipt_root.is_absolute() else root / receipt_root
    output_root = output_root.resolve()
    relative_output = _relative_to_repo(root, output_root, label="receipt root")
    output_root.mkdir(parents=True, exist_ok=True)
    lock_path = output_root / ".runner.lock"

    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        identity = build_test_identity(
            repo_root=root,
            command=command,
            relevant_paths=relevant_paths,
        )
        identity_root = output_root / str(identity["identity_digest"])
        identity_root.mkdir(parents=True, exist_ok=True)
        receipt_path = identity_root / "test-receipt.json"
        log_path = identity_root / "test.log"
        existing = _load_object(receipt_path)
        if (
            existing is not None
            and log_path.is_file()
            and existing.get("log_sha256") == sha256_file(log_path)
            and is_test_receipt_reusable(existing, identity)
        ):
            return {
                "schema_version": RUN_SCHEMA,
                "status": "reused",
                "identity_digest": identity["identity_digest"],
                "receipt_path": str(receipt_path),
                "receipt_digest": existing["receipt_digest"],
                "exit_code": 0,
                "counts": existing["counts"],
            }

        lease_path = identity_root / "process-lease.json"
        prior_lease = _load_object(lease_path)
        if prior_lease is not None:
            verified = verify_process_lease(prior_lease)
            if verified["status"] == "active":
                try:
                    orphaned = mark_missing_process_orphaned(verified)
                except DevLoopLifecycleError as error:
                    raise DevLoopRunnerError(
                        "refusing duplicate test launch while the exact leased process is active"
                    ) from error
                atomic_write_json(identity_root / "orphaned-process-lease.json", orphaned)

        task = build_task_contract(
            task_id=f"test-{identity['identity_digest']}",
            role="executor",
            repo_root=root,
            branch=str(identity["branch"]),
            base_commit=str(identity["commit"]),
            allowed_paths=[*relevant_paths, relative_output],
            allowed_operations=["read", "test", "write_receipts"],
            proof_target=f"exact-identity {tier} test evidence",
            wall_time_seconds=wall_time_seconds,
        )
        started = time.monotonic()
        read_fd, write_fd = os.pipe()
        child: subprocess.Popen[str] | None = None
        lease: dict[str, Any] | None = None
        try:
            with log_path.open("w", encoding="utf-8") as log_file:
                child = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "sim2claw.dev_loop.worker",
                        "--gate-fd",
                        str(read_fd),
                        "--gate-timeout-seconds",
                        "30",
                        "--",
                        *[str(value) for value in command],
                    ],
                    cwd=root,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                    pass_fds=(read_fd,),
                    start_new_session=True,
                )
                os.close(read_fd)
                read_fd = -1
                lease = build_process_lease(
                    lease_id=f"test-{identity['identity_digest']}",
                    task_contract=task,
                    pid=child.pid,
                    expected_command_substring=str(command[0]),
                    expires_at=datetime.now(timezone.utc)
                    + timedelta(seconds=wall_time_seconds),
                )
                atomic_write_json(lease_path, lease)
                os.write(write_fd, b"1")
                os.close(write_fd)
                write_fd = -1
                try:
                    exit_code = int(child.wait(timeout=wall_time_seconds))
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait(timeout=5)
                    exit_code = 124
                    log_file.write(f"\nTIMEOUT after {wall_time_seconds} seconds\n")
        except BaseException:
            if child is not None and child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                child.wait(timeout=5)
            raise
        finally:
            if read_fd >= 0:
                os.close(read_fd)
            if write_fd >= 0:
                os.close(write_fd)
        if lease is None:
            raise DevLoopRunnerError("test child lease was not created")
        duration = time.monotonic() - started
        closed_lease = complete_process_lease(lease, exit_code=exit_code)
        atomic_write_json(lease_path, closed_lease)
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        receipt = build_test_receipt(
            identity=identity,
            tier=tier,
            exit_code=exit_code,
            duration_seconds=duration,
            counts=_counts(log_text),
            log_sha256=sha256_file(log_path),
        )
        atomic_write_json(receipt_path, receipt)
        return {
            "schema_version": RUN_SCHEMA,
            "status": "executed",
            "identity_digest": identity["identity_digest"],
            "receipt_path": str(receipt_path),
            "receipt_digest": receipt["receipt_digest"],
            "exit_code": exit_code,
            "counts": receipt["counts"],
        }


__all__ = ["DevLoopRunnerError", "RUN_SCHEMA", "run_test_with_receipt"]
