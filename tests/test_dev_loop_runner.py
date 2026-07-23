from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sim2claw.dev_loop.lifecycle import cleanup_expired_process_lease
from sim2claw.dev_loop.runner import DevLoopRunnerError, run_test_with_receipt


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def test_runner_executes_then_reuses_only_the_exact_passing_identity(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "dev-loop@example.invalid")
    _git(tmp_path, "config", "user.name", "Dev Loop Test")
    subject = tmp_path / "subject.txt"
    subject.write_text("one\n", encoding="utf-8")
    _git(tmp_path, "add", "subject.txt")
    _git(tmp_path, "commit", "-m", "seed")
    marker = tmp_path / "execution-count.json"
    script = (
        "import json, pathlib; "
        f"p=pathlib.Path({str(marker)!r}); "
        "n=json.loads(p.read_text()) if p.exists() else 0; "
        "p.write_text(json.dumps(n+1)); "
        "print('1 passed')"
    )
    arguments = {
        "repo_root": tmp_path,
        "command": [sys.executable, "-c", script],
        "relevant_paths": ["subject.txt"],
        "receipt_root": Path("outputs/dev-loop/test-receipts"),
        "tier": "focused",
    }

    first = run_test_with_receipt(**arguments)
    lease_path = (
        tmp_path
        / "outputs/dev-loop/test-receipts"
        / first["identity_digest"]
        / "process-lease.json"
    )
    completed_lease = json.loads(lease_path.read_text(encoding="utf-8"))
    assert completed_lease["status"] == "completed"
    assert completed_lease["pid"] != os.getpid()
    assert completed_lease["process_cwd"] == str(tmp_path)
    second = run_test_with_receipt(**arguments)
    assert first["status"] == "executed"
    assert second["status"] == "reused"
    assert first["receipt_digest"] == second["receipt_digest"]
    assert json.loads(marker.read_text(encoding="utf-8")) == 1

    subject.write_text("two\n", encoding="utf-8")
    third = run_test_with_receipt(**arguments)
    assert third["status"] == "executed"
    assert third["identity_digest"] != first["identity_digest"]
    assert json.loads(marker.read_text(encoding="utf-8")) == 2


def test_runner_crash_leaves_the_actual_child_leased_and_blocks_duplicate(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "dev-loop@example.invalid")
    _git(tmp_path, "config", "user.name", "Dev Loop Test")
    subject = tmp_path / "subject.txt"
    subject.write_text("one\n", encoding="utf-8")
    _git(tmp_path, "add", "subject.txt")
    _git(tmp_path, "commit", "-m", "seed")
    marker = tmp_path / "child-started"
    command = [
        sys.executable,
        "-c",
        f"import pathlib,time; pathlib.Path({str(marker)!r}).write_text('yes'); time.sleep(30)",
    ]
    receipt_root = Path("outputs/dev-loop/crash-receipts")
    driver = (
        "from pathlib import Path; "
        "from sim2claw.dev_loop.runner import run_test_with_receipt; "
        "run_test_with_receipt("
        f"repo_root=Path({str(tmp_path)!r}), command={command!r}, "
        "relevant_paths=['subject.txt'], "
        f"receipt_root=Path({str(receipt_root)!r}), "
        "tier='crash-probe', wall_time_seconds=1)"
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", driver],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    lease_path: Path | None = None
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            leases = list((tmp_path / receipt_root).glob("*/process-lease.json"))
            if marker.is_file() and leases:
                lease_path = leases[0]
                break
            time.sleep(0.05)
        assert lease_path is not None
        active_lease = json.loads(lease_path.read_text(encoding="utf-8"))
        assert active_lease["status"] == "active"
        assert active_lease["pid"] != parent.pid

        parent.kill()
        parent.wait(timeout=5)
        with pytest.raises(DevLoopRunnerError, match="duplicate test launch"):
            run_test_with_receipt(
                repo_root=tmp_path,
                command=command,
                relevant_paths=["subject.txt"],
                receipt_root=receipt_root,
                tier="crash-probe",
                wall_time_seconds=1,
            )

        expires_at = datetime.fromisoformat(active_lease["expires_at"])
        delay = (expires_at - datetime.now(timezone.utc)).total_seconds()
        if delay > 0:
            time.sleep(delay + 0.1)
        closed = cleanup_expired_process_lease(active_lease, terminate=True)
        assert closed["status"] == "expired"
        assert closed["termination_requested"] is True
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)
