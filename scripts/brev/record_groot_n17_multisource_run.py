#!/usr/bin/env python3
"""Record immutable identities for the bounded multisource GR00T run."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any


SCHEDULED_STEPS = (250, 500, 750, 1000)
EXPERIMENT_NAME = "sim2claw-groot-n17-multisource-v2"
HISTORICAL_RANK12_PATH = Path(
    "configs/evaluations/pawn_rank12_bidirectional_v1.json"
)
CURRENT_RANK12_PATH = Path(
    "configs/evaluations/pawn_rank12_bidirectional_v2.json"
)
HISTORICAL_RANK12_SHA256 = (
    "f3dac8b86cd7b0252153d25c0d5c09204079003ac9780642992fd10bc08e0d43"
)
CURRENT_RANK12_SHA256 = (
    "8e5a351421dc222688e3ad0cfc7e0c14023352e3ee7132e02c26290d0a7f96f3"
)
CURRENT_RANK12_SOURCE_COMMIT = (
    "36f1ebc5f66e63317b1fba84ba9aaabf66a5ff2d"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def checkpoint_manifest(checkpoint: Path, step: int) -> dict[str, Any]:
    files: dict[str, str] = {}
    sizes: dict[str, int] = {}
    for path in sorted(
        candidate for candidate in checkpoint.rglob("*") if candidate.is_file()
    ):
        relative = path.relative_to(checkpoint).as_posix()
        files[relative] = sha256_file(path)
        sizes[relative] = path.stat().st_size
    required = {
        "config.json",
        "model.safetensors.index.json",
        "processor_config.json",
        "statistics.json",
        "trainer_state.json",
    }
    if not required.issubset(files):
        missing = sorted(required - set(files))
        raise ValueError(f"checkpoint-{step} is missing identity files: {missing}")
    model_shards = [
        name
        for name in files
        if name.startswith("model-") and name.endswith(".safetensors")
    ]
    if not model_shards:
        raise ValueError(f"checkpoint-{step} has no model shards")
    return {
        "schema_version": "sim2claw.groot_checkpoint_manifest.v1",
        "checkpoint_step": step,
        "checkpoint_path": str(checkpoint.resolve()),
        "files": files,
        "file_sizes_bytes": sizes,
        "file_count": len(files),
        "total_size_bytes": sum(sizes.values()),
    }


def rank12_contract_identities(code_root: Path) -> dict[str, Any]:
    """Keep the completed run's v1 identity historical beside current v2."""

    historical = code_root / HISTORICAL_RANK12_PATH
    current = code_root / CURRENT_RANK12_PATH
    historical_payload = json.loads(historical.read_text(encoding="utf-8"))
    historical_sha256 = sha256_file(historical)
    if (
        historical_payload.get("evaluation_set_id")
        != "pawn_rank12_bidirectional_v1"
    ):
        raise ValueError("historical rank-12 v1 identity changed")
    if historical_sha256 != HISTORICAL_RANK12_SHA256:
        raise ValueError("historical rank-12 v1 payload changed")
    current_identity: dict[str, Any] = {
        "path": CURRENT_RANK12_PATH.as_posix(),
        "expected_evaluation_set_id": "pawn_rank12_bidirectional_b_to_g_v2",
        "expected_scope": "brown_pawns_b_through_g_rank1_rank2_bidirectional",
        "sha256": CURRENT_RANK12_SHA256,
        "source_commit": CURRENT_RANK12_SOURCE_COMMIT,
        "role": "current_product_contract_not_used_by_completed_run",
        "available_in_code_root": current.is_file(),
        "payload_verified_in_code_root": False,
    }
    if current.is_file():
        current_payload = json.loads(current.read_text(encoding="utf-8"))
        if (
            current_payload.get("evaluation_set_id")
            != current_identity["expected_evaluation_set_id"]
        ):
            raise ValueError("current rank-12 v2 identity changed")
        if sha256_file(current) != CURRENT_RANK12_SHA256:
            raise ValueError("current rank-12 v2 payload changed")
        current_identity["payload_verified_in_code_root"] = True
    return {
        "historical_completed_run_contract": {
            "path": HISTORICAL_RANK12_PATH.as_posix(),
            "evaluation_set_id": historical_payload["evaluation_set_id"],
            "sha256": historical_sha256,
            "role": "historical_identity_used_by_completed_run",
        },
        "current_product_contract": current_identity,
        "completed_run_contract_was_not_rewritten": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--code-root", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--remote-loader-receipt", type=Path, required=True)
    parser.add_argument("--model-snapshot-receipt", type=Path, required=True)
    parser.add_argument("--superseded-root", type=Path, required=True)
    args = parser.parse_args()

    run_root = args.run_root.resolve()
    code_root = args.code_root.resolve()
    dataset = args.dataset.resolve()
    experiment = code_root / "configs/experiments/groot_n17_multisource_v2.json"
    evaluator = code_root / "configs/tasks/chess_pick_place_pawn_evaluator_v3.json"
    rank12_identities = rank12_contract_identities(code_root)
    training_root = run_root / "train" / EXPERIMENT_NAME
    if (run_root / "training.exit").read_text().strip() != "0":
        raise ValueError("training did not exit successfully")
    observed_steps = sorted(
        int(path.name.removeprefix("checkpoint-"))
        for path in training_root.glob("checkpoint-*")
        if path.is_dir()
    )
    if observed_steps != list(SCHEDULED_STEPS):
        raise ValueError(f"scheduled checkpoint set drifted: {observed_steps}")

    evidence_root = run_root / "evidence"
    checkpoint_root = evidence_root / "checkpoints"
    checkpoint_root.mkdir(parents=True, exist_ok=False)
    checkpoint_rows: list[dict[str, Any]] = []
    for step in SCHEDULED_STEPS:
        manifest = checkpoint_manifest(training_root / f"checkpoint-{step}", step)
        path = checkpoint_root / f"checkpoint-{step}-manifest.json"
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        checkpoint_rows.append(
            {
                "step": step,
                "manifest_path": str(path),
                "manifest_sha256": sha256_file(path),
                "file_count": manifest["file_count"],
                "total_size_bytes": manifest["total_size_bytes"],
            }
        )

    trainer_state = json.loads(
        (training_root / "checkpoint-1000/trainer_state.json").read_text()
    )
    if int(trainer_state.get("global_step", -1)) != 1000:
        raise ValueError("terminal checkpoint trainer state is not step 1000")
    training_log = (run_root / "training.log").read_text(errors="replace")
    runtime_rows = re.findall(r"\{'train_runtime': [^}]+\}", training_log)
    if len(runtime_rows) != 1:
        raise ValueError("training log does not contain one terminal runtime row")
    terminal_metrics = ast.literal_eval(runtime_rows[0])
    dataset_receipt = dataset / "dataset_receipt.json"
    superseded_files = {
        relative: sha256_file(args.superseded_root / relative)
        for relative in (
            "training.log",
            "training-launch-receipt.json",
            "training.exit",
        )
    }
    payload = {
        "schema_version": "sim2claw.groot_n17_multisource_run_receipt.v1",
        "experiment_sha256": sha256_file(experiment),
        "dataset_receipt_sha256": sha256_file(dataset_receipt),
        "dataset_payload_manifest_sha256": json.loads(dataset_receipt.read_text())[
            "payload_manifest_sha256"
        ],
        "remote_loader_receipt_sha256": sha256_file(args.remote_loader_receipt),
        "model_snapshot_receipt_sha256": sha256_file(args.model_snapshot_receipt),
        "evaluator_contract_sha256": sha256_file(evaluator),
        # Backward-compatible historical field: this completed run used v1.
        "sealed_rank12_evaluation_sha256": rank12_identities[
            "historical_completed_run_contract"
        ]["sha256"],
        "rank12_contract_identities": rank12_identities,
        "training_log_sha256": sha256_file(run_root / "training.log"),
        "training_launch_receipt_sha256": sha256_file(
            run_root / "training-launch-receipt.json"
        ),
        "training_exit_receipt_sha256": sha256_file(run_root / "training.exit"),
        "optimizer_steps": 1000,
        "training_runtime_seconds": float(terminal_metrics["train_runtime"]),
        "train_samples_per_second": float(
            terminal_metrics["train_samples_per_second"]
        ),
        "train_steps_per_second": float(terminal_metrics["train_steps_per_second"]),
        "train_loss": float(terminal_metrics["train_loss"]),
        "scheduled_checkpoints": checkpoint_rows,
        "fixed_primary_checkpoint": 1000,
        "superseded_pre_optimizer_failure": {
            "root": str(args.superseded_root.resolve()),
            "files": superseded_files,
            "optimizer_steps": 0,
            "checkpoint_created": False,
        },
        "held_out_rows_used": 0,
        "failed_action_rows_used": 0,
        "physical_training_rows": 0,
        "training_complete": True,
        "evaluation_complete": False,
        "training_cannot_promote": True,
        "physical_authority": False,
    }
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
    receipt_path = evidence_root / "run-receipt.json"
    receipt_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
