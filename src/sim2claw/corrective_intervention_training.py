"""Suffix-only correction mixtures and non-behavioral checkpoint smoke proof."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch

from .act_model import load_act_checkpoint_snapshot, read_act_checkpoint_snapshot
from .goal_act_training import (
    TRAINING_RECEIPT_SCHEMA,
    load_goal_act_dataset,
)
from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .learning_factory_goal_data import (
    DATASET_SCHEMA,
    ROW_SCHEMA,
    encode_goal_act_rows,
)
from .source_episode import adapt_source_episode, load_source_episode


CHECKPOINT_SMOKE_SCHEMA = "sim2claw.corrective_checkpoint_runtime_smoke.v1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(dict(row), sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )
    return {"path": path.name, "sha256": sha256_file(path), "row_count": len(rows)}


def build_goal_act_correction_mixture(
    *,
    base_dataset_receipt_path: Path,
    corrections: Sequence[Mapping[str, Any]],
    output_directory: Path,
    object_dimensions_m: Sequence[float],
    gripper_aperture_mapping: Mapping[str, Any],
) -> dict[str, Any]:
    """Append independently admitted corrective suffixes to one LF-09 dataset."""

    base_receipt, base_rows = load_goal_act_dataset(base_dataset_receipt_path)
    _require(bool(corrections), "correction mixture requires at least one admitted suffix")
    dimensions = [float(value) for value in object_dimensions_m]
    _require(len(dimensions) == 3 and all(math.isfinite(value) and value > 0 for value in dimensions), "correction mixture object dimensions are invalid")
    mapping = dict(gripper_aperture_mapping)
    _require(mapping.get("mapping_id") == "so101_parallel_jaw_affine_v1", "correction mixture requires the reviewed gripper mapping")
    output_directory = output_directory.resolve()
    _require(not output_directory.exists(), "correction mixture output already exists")
    output_directory.mkdir(parents=True)

    rows = [dict(row) for row in base_rows]
    training_episode_ids = list(base_receipt["training_episode_ids"])
    correction_receipts: list[dict[str, Any]] = []
    for declaration in corrections:
        admitted = declaration.get("admitted_correction")
        _require(isinstance(admitted, Mapping), "correction declaration lacks admitted evidence")
        admitted = dict(admitted)
        unsigned_admitted = {
            key: value for key, value in admitted.items() if key != "artifact_sha256"
        }
        _require(
            admitted.get("schema_version") == "sim2claw.factory_admitted_correction.v1"
            and admitted.get("artifact_sha256") == canonical_digest(unsigned_admitted),
            "correction admission artifact is invalid",
        )
        _require(admitted.get("independent_evaluator_admitted") is True, "correction was not independently admitted")
        _require(admitted.get("failed_prefix_training_rows") == 0, "correction contains failed-prefix rows")
        _require(admitted.get("route_target") == "LF-09", "correction does not route to LF-09")
        episode = Path(str(admitted["corrective_episode_directory"])).resolve()
        verdict_path = Path(str(admitted["admission_verdict_path"])).resolve()
        _require(
            verdict_path.is_file()
            and sha256_file(verdict_path) == admitted["admission_verdict_sha256"],
            "correction verdict is missing or changed",
        )
        verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
        receipt, source_rows = load_source_episode(episode)
        adapted = adapt_source_episode(
            episode,
            adapter="act",
            admission_verdict=verdict,
        )
        suffix = verdict["corrective_suffix"]
        start = int(suffix["start_sample_index"])
        end = int(suffix["end_sample_index_exclusive"])
        selected_rows = source_rows[start:end]
        _require(
            len(selected_rows)
            == len(adapted)
            == int(admitted["admitted_suffix_row_count"]),
            "correction suffix row count changed",
        )
        _require(receipt["recording_id"] not in training_episode_ids, "correction episode duplicates a base episode")
        observations = encode_goal_act_rows(
            selected_rows,
            piece_id=str(receipt["piece_id"]),
            object_dimensions_m=dimensions,
            gripper_aperture_mapping=mapping,
        )
        row_start = len(rows)
        for source_row, adapted_row, observation in zip(
            selected_rows,
            adapted,
            observations,
            strict=True,
        ):
            rows.append(
                {
                    "schema_version": ROW_SCHEMA,
                    "candidate_id": admitted["correction_candidate_id"],
                    "source_sample_index": int(source_row["sample_index"]),
                    "observation": observation.astype(float).tolist(),
                    "action_joint_target_rad": [
                        float(value)
                        for value in adapted_row["action_joint_target_rad"]
                    ],
                    "lineage": {
                        **adapted_row["lineage"],
                        "correction_candidate_id": admitted[
                            "correction_candidate_id"
                        ],
                        "parent_counterexample_id": admitted[
                            "parent_counterexample_id"
                        ],
                        "admitted_correction_sha256": admitted[
                            "artifact_sha256"
                        ],
                        "failed_prefix_training_rows": 0,
                    },
                }
            )
        training_episode_ids.append(receipt["recording_id"])
        correction_receipts.append(
            {
                "correction_candidate_id": admitted["correction_candidate_id"],
                "parent_counterexample_id": admitted["parent_counterexample_id"],
                "admitted_correction_sha256": admitted["artifact_sha256"],
                "source_recording_id": receipt["recording_id"],
                "source_receipt_sha256": sha256_file(
                    episode / "recording_receipt.json"
                ),
                "admission_verdict_sha256": admitted[
                    "admission_verdict_sha256"
                ],
                "training_row_start": row_start,
                "training_row_end_exclusive": len(rows),
                "training_row_count": len(rows) - row_start,
                "failed_prefix_training_rows": 0,
            }
        )

    payload = _write_jsonl(output_directory / "act_train.jsonl", rows)
    correction_count = sum(row["training_row_count"] for row in correction_receipts)
    unsigned = {
        "schema_version": DATASET_SCHEMA,
        "task_id": base_receipt["task_id"],
        "task_contract_sha256": base_receipt["task_contract_sha256"],
        "base_dataset_sha256": base_receipt["dataset_sha256"],
        "base_dataset_receipt_sha256": sha256_file(base_dataset_receipt_path),
        "mixture_proof_class": "simulation_correction_training_fixture",
        "accepted_count": int(base_receipt.get("accepted_count", 0))
        + len(correction_receipts),
        "rejected_count": int(base_receipt.get("rejected_count", 0)),
        "training_episode_ids": training_episode_ids,
        "base_training_row_count": len(base_rows),
        "correction_training_row_count": correction_count,
        "training_row_count": len(rows),
        "correction_fraction": correction_count / len(rows),
        "held_out_training_rows": 0,
        "rejected_training_rows": 0,
        "act_payload": payload,
        "corrections": correction_receipts,
        "preflight": {
            "observation_dimension": 61,
            "action_dimension": 6,
            "all_rows_have_lineage": all(bool(row["lineage"]) for row in rows),
            "failed_prefix_training_rows": 0,
            "privileged_state_in_policy_payload": False,
        },
        "admission_owner": "separate_cpu_fp32_consequence_evaluator",
        "training_can_promote": False,
    }
    receipt = {**unsigned, "dataset_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_directory / "dataset_receipt.json", receipt)
    return receipt


def evaluate_correction_checkpoint_runtime(
    *,
    checkpoint_path: Path,
    training_receipt_path: Path,
    dataset_receipt_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Independently prove checkpoint lineage and finite CPU inference only."""

    training = json.loads(training_receipt_path.read_text(encoding="utf-8"))
    unsigned_training = {
        key: value for key, value in training.items() if key != "artifact_sha256"
    }
    _require(
        training.get("schema_version") == TRAINING_RECEIPT_SCHEMA
        and training.get("artifact_sha256") == canonical_digest(unsigned_training),
        "training receipt is invalid",
    )
    dataset, rows = load_goal_act_dataset(dataset_receipt_path)
    _require(training["dataset_sha256"] == dataset["dataset_sha256"], "training dataset identity mismatch")
    _require(training["checkpoint_sha256"] == sha256_file(checkpoint_path), "checkpoint bytes changed")
    snapshot = read_act_checkpoint_snapshot(
        checkpoint_path,
        expected_sha256=training["checkpoint_sha256"],
    )
    model, statistics, checkpoint = load_act_checkpoint_snapshot(
        snapshot,
        device=torch.device("cpu"),
    )
    _require(
        checkpoint.get("training", {}).get("dataset_sha256")
        == dataset["dataset_sha256"],
        "checkpoint embeds another dataset identity",
    )
    observation = torch.as_tensor(
        rows[0]["observation"],
        dtype=torch.float32,
    ).unsqueeze(0)
    normalized = (
        observation - statistics["observation_mean"]
    ) / statistics["observation_std"]
    with torch.inference_mode():
        prediction = model.predict_action_chunk(normalized).squeeze(0)
    decoded = (
        prediction * statistics["action_std"] + statistics["action_mean"]
    ).cpu().numpy()
    _require(
        decoded.ndim == 2
        and decoded.shape[1] == 6
        and np.isfinite(decoded).all(),
        "checkpoint runtime emitted invalid actions",
    )
    unsigned = {
        "schema_version": CHECKPOINT_SMOKE_SCHEMA,
        "proof_class": "checkpoint_lineage_and_finite_cpu_runtime_only",
        "dataset_sha256": dataset["dataset_sha256"],
        "dataset_receipt_sha256": sha256_file(dataset_receipt_path),
        "training_receipt_sha256": sha256_file(training_receipt_path),
        "checkpoint_sha256": snapshot.sha256,
        "device": "cpu",
        "dtype": "float32",
        "predicted_chunk_shape": list(decoded.shape),
        "finite_actions": True,
        "behavioral_evaluation": False,
        "held_out_policy_success": None,
        "training_can_promote": False,
        "physical_transfer_proof": False,
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_path, receipt)
    return receipt
