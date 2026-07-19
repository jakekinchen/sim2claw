#!/usr/bin/env python3
"""Record and validate the live bounded pawn GR00T training process."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any


EXPERIMENT_SHA256 = "ea6184ba10bd7803ac8e839ae3aebc4de079621afe03f43b6505a61e86622507"
DATASET_PATH = "/home/shadeform/chess_pick_place_pawn_groot_v1"
OUTPUT_PATH = "/home/shadeform/runs/groot-n17-pawn-100mm-v1/train"
BASE_PATH = "/home/shadeform/.cache/huggingface/hub/models--nvidia--GR00T-N1.7-3B/snapshots/2fc962b973bccdd5d8ce4f67cc63b264d6886495"
PROCESSOR_PATH = "/home/shadeform/.cache/huggingface/hub/models--nvidia--Cosmos-Reason2-2B/snapshots/9ce19a195e423419c349abfc86fd07178b230561"


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


def flag_values(command: list[str]) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for index, token in enumerate(command):
        if token.startswith("--") and index + 1 < len(command):
            values.setdefault(token, []).append(command[index + 1])
    return values


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--launch-receipt", type=Path, required=True)
    parser.add_argument("--training-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    proc = Path("/proc") / str(args.pid)
    if not proc.is_dir():
        raise SystemExit(f"training PID is not live: {args.pid}")
    command = [
        value.decode()
        for value in (proc / "cmdline").read_bytes().split(b"\0")
        if value
    ]
    if len(command) < 2 or command[1] != "gr00t/experiment/launch_finetune.py":
        raise SystemExit(f"unexpected training child command: {command}")
    flags = flag_values(command)
    exact_last_flags = {
        "--base_model_path": BASE_PATH,
        "--dataset_path": DATASET_PATH,
        "--output_dir": OUTPUT_PATH,
        "--embodiment_tag": "NEW_EMBODIMENT",
        "--num_gpus": "1",
        "--save_steps": "250",
        "--max_steps": "1000",
        "--global_batch_size": "16",
        "--shard_size": "64",
        "--num_shards_per_epoch": "9",
        "--episode_sampling_rate": "0.1",
        "--state_dropout_prob": "0.0",
        "--learning_rate": "5e-05",
    }
    for flag, expected in exact_last_flags.items():
        if not flags.get(flag) or flags[flag][-1] != expected:
            raise SystemExit(f"training flag drifted: {flag} -> {flags.get(flag)}")

    environment = {}
    for row in (proc / "environ").read_bytes().split(b"\0"):
        if not row or b"=" not in row:
            continue
        key, value = row.split(b"=", 1)
        environment[key.decode()] = value.decode(errors="replace")
    expected_environment = {
        "CUDA_VISIBLE_DEVICES": "0",
        "NUM_GPUS": "1",
        "MAX_STEPS": "1000",
        "SAVE_STEPS": "250",
        "GLOBAL_BATCH_SIZE": "16",
        "SHARD_SIZE": "64",
        "NUM_SHARDS_PER_EPOCH": "9",
        "EPISODE_SAMPLING_RATE": "0.1",
        "GROOT_PROCESSOR_MODEL_PATH": PROCESSOR_PATH,
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "EXPECTED_EXPERIMENT_SHA256": EXPERIMENT_SHA256,
    }
    for key, expected in expected_environment.items():
        if environment.get(key) != expected:
            raise SystemExit(f"training environment drifted: {key}")

    if sha256_file(args.experiment) != EXPERIMENT_SHA256:
        raise SystemExit("runtime experiment hash drifted")
    launch = json.loads(args.launch_receipt.read_text())
    if launch.get("experiment_sha256") != EXPERIMENT_SHA256:
        raise SystemExit("launch receipt experiment identity drifted")
    if launch.get("held_out_rows_used") != 0 or launch.get("model_queries") != 0:
        raise SystemExit("launch receipt authority boundary drifted")

    gpu = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,uuid,memory.used",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    log_bytes = args.training_log.read_bytes()
    payload = {
        "schema_version": "sim2claw.groot_n17_pawn_training_runtime.v1",
        "pid": args.pid,
        "command": command,
        "validated_last_flag_values": exact_last_flags,
        "validated_environment": expected_environment,
        "experiment_sha256": EXPERIMENT_SHA256,
        "launch_receipt_sha256": sha256_file(args.launch_receipt),
        "training_log_prefix_size_bytes": len(log_bytes),
        "training_log_prefix_sha256": hashlib.sha256(log_bytes).hexdigest(),
        "gpu": gpu,
        "output_path": OUTPUT_PATH,
        "held_out_rows_used": 0,
        "physical_authority": False,
        "runtime_recorder_sha256": sha256_file(Path(__file__).resolve()),
    }
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
