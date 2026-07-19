#!/usr/bin/env python3
"""Record exact completion evidence and checkpoint manifests for pawn GR00T."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def checkpoint_manifest(path: Path) -> dict[str, Any]:
    if not path.is_dir():
        raise SystemExit(f"checkpoint is missing: {path}")
    rows = []
    for entry in sorted(
        (entry for entry in path.rglob("*") if entry.is_file()),
        key=lambda item: item.relative_to(path).as_posix(),
    ):
        rows.append(
            {
                "path": entry.relative_to(path).as_posix(),
                "size_bytes": entry.stat().st_size,
                "sha256": sha256_file(entry),
            }
        )
    return {
        "path": str(path),
        "file_count": len(rows),
        "manifest": rows,
        "manifest_sha256": canonical_sha256(rows),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--training-root", type=Path, required=True)
    parser.add_argument("--launch-receipt", type=Path, required=True)
    parser.add_argument("--runtime-receipt", type=Path, required=True)
    parser.add_argument("--training-log", type=Path, required=True)
    parser.add_argument("--training-exit", type=Path, required=True)
    parser.add_argument("--supervisor-pid", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    experiment_sha256 = sha256_file(args.experiment)
    experiment = json.loads(args.experiment.read_text())
    if experiment_sha256 != "ea6184ba10bd7803ac8e839ae3aebc4de079621afe03f43b6505a61e86622507":
        raise SystemExit("completed run belongs to another experiment")
    if args.training_exit.read_text().strip() != "0":
        raise SystemExit("training did not exit successfully")
    log = args.training_log.read_bytes()
    if b"1000/1000" not in log or b"'train_runtime':" not in log:
        raise SystemExit("training log does not prove 1,000-step completion")
    if b"Traceback (most recent call last)" in log:
        raise SystemExit("training log contains a traceback")

    runtime = json.loads(args.runtime_receipt.read_text())
    child_pid = int(runtime["pid"])
    supervisor_pid = int(args.supervisor_pid.read_text().strip())
    if Path("/proc", str(child_pid)).exists() or Path("/proc", str(supervisor_pid)).exists():
        raise SystemExit("training process is still live")
    if runtime["experiment_sha256"] != experiment_sha256:
        raise SystemExit("runtime receipt belongs to another experiment")

    launch = json.loads(args.launch_receipt.read_text())
    if launch["experiment_sha256"] != experiment_sha256:
        raise SystemExit("launch receipt belongs to another experiment")
    if launch["held_out_rows_used"] != 0 or runtime["held_out_rows_used"] != 0:
        raise SystemExit("training evidence consumed held-out rows")

    checkpoint_parent = args.training_root / "sim2claw-groot-n17-pawn-100mm-v1"
    actual_steps = sorted(
        int(path.name.removeprefix("checkpoint-"))
        for path in checkpoint_parent.glob("checkpoint-*")
        if path.is_dir() and path.name.removeprefix("checkpoint-").isdigit()
    )
    expected_steps = experiment["training"]["checkpoint_steps"]
    if actual_steps != expected_steps:
        raise SystemExit(f"checkpoint inventory drifted: {actual_steps}")
    checkpoints = {}
    for step in expected_steps:
        path = checkpoint_parent / f"checkpoint-{step}"
        state = json.loads((path / "trainer_state.json").read_text())
        if int(state["global_step"]) != step or int(state["max_steps"]) != 1000:
            raise SystemExit(f"checkpoint-{step} trainer state drifted")
        checkpoints[str(step)] = {
            **checkpoint_manifest(path),
            "global_step": int(state["global_step"]),
            "maximum_steps": int(state["max_steps"]),
        }

    gpu_processes = subprocess.run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if gpu_processes:
        raise SystemExit(f"GPU compute process remains after training: {gpu_processes}")

    payload = {
        "schema_version": "sim2claw.groot_n17_pawn_training_completion.v1",
        "experiment_sha256": experiment_sha256,
        "training_root": str(args.training_root),
        "checkpoint_parent": str(checkpoint_parent),
        "checkpoints": checkpoints,
        "launch_receipt_sha256": sha256_file(args.launch_receipt),
        "runtime_receipt_sha256": sha256_file(args.runtime_receipt),
        "training_log_sha256": hashlib.sha256(log).hexdigest(),
        "training_exit_sha256": sha256_file(args.training_exit),
        "training_exit_code": 0,
        "training_child_pid": child_pid,
        "training_supervisor_pid": supervisor_pid,
        "training_processes_stopped": True,
        "gpu_compute_processes_after_training": 0,
        "optimizer_steps": 1000,
        "held_out_rows_used": 0,
        "model_queries": 0,
        "task_success_authority": False,
        "physical_authority": False,
        "completion_recorder_sha256": sha256_file(Path(__file__).resolve()),
    }
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
