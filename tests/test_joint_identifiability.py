from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from sim2claw import joint_identifiability
from sim2claw.joint_identifiability import (
    JointIdentifiabilityError,
    derive_joint_identifiability_report,
)
from sim2claw.learning_factory_artifacts import sha256_file


JOINTS = [
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
]


def _fixture(root: Path) -> tuple[Path, np.ndarray]:
    recording_id = "fixture-identifiability"
    samples_path = root / "recording/samples.jsonl"
    samples_path.parent.mkdir(parents=True, exist_ok=True)
    # Pan, roll, and gripper are bidirectional; shoulder lift is constant;
    # elbow has insufficient span; wrist flex is one-way only.
    command = np.asarray(
        [
            [-10, -100, 90, -20, -100, 0],
            [0, -100, 92, -10, -90, 50],
            [10, -100, 94, 0, -80, 100],
            [0, -100, 96, 10, -90, 50],
            [-10, -100, 98, 20, -100, 0],
        ],
        dtype="<f8",
    )
    actual = command * np.asarray([0.98, 1, 0.9, 1.01, 1, 0.99]) + np.asarray(
        [0.2, 0.5, 9, -0.2, 0.3, 0.5]
    )
    velocity = np.vstack([np.zeros(6), np.diff(actual, axis=0) / 0.05])
    rows = []
    for index in range(len(command)):
        rows.append(
            {
                "recording_id": recording_id,
                "timestamp_monotonic_seconds": index * 0.05,
                "follower_command_degrees": command[index].tolist(),
                "follower_actual_position_degrees": actual[index].tolist(),
                "follower_actual_velocity_degrees_s": velocity[index].tolist(),
            }
        )
    samples_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    action_sha256 = hashlib.sha256(command.tobytes(order="C")).hexdigest()
    authority = {
        "physical_motion": False,
        "physical_capture": False,
        "simulator_execution": False,
        "simulator_parameter_promotion": False,
        "policy_promotion": False,
        "training": False,
        "task_score_change": False,
        "provider_advice_is_evaluator_evidence": False,
    }
    contract = {
        "schema_version": "sim2claw.overnight_joint_identifiability_contract.v1",
        "analysis_id": "fixture-identifiability-v1",
        "status": "frozen_before_derived_materialization",
        "source": {
            "recording_directory": "recording",
            "recording_id": recording_id,
            "samples_path": "samples.jsonl",
            "samples_sha256": sha256_file(samples_path),
            "command_field": "follower_command_degrees",
            "actual_position_field": "follower_actual_position_degrees",
            "actual_velocity_field": "follower_actual_velocity_degrees_s",
            "timestamp_field": "timestamp_monotonic_seconds",
            "action_shape": [5, 6],
            "action_dtype": "float64",
            "action_sha256": action_sha256,
            "joint_order": JOINTS,
        },
        "estimator": {
            "lag_candidates_samples": [0, 1],
            "minimum_command_span_degrees": 15,
            "minimum_positive_command_changes": 1,
            "minimum_negative_command_changes": 1,
            "command_change_epsilon_degrees": 1e-9,
            "minimum_velocity_for_direction_degrees_s": 2,
            "no_lag_interpolation": True,
            "no_action_mutation": True,
        },
        "claim_gates": {
            "simulator_parameter_promotion_allowed": False,
            "task_score_change_allowed": False,
        },
        "authority": authority,
    }
    contract_path = root / "contract.json"
    contract_path.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return contract_path, command


def test_report_separates_excitation_from_affine_fit(tmp_path: Path) -> None:
    contract_path, command = _fixture(tmp_path)
    output = tmp_path / "output"
    with patch.object(joint_identifiability, "REPO_ROOT", tmp_path):
        receipt = derive_joint_identifiability_report(
            output, contract_path=contract_path
        )
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    rows = {row["joint"]: row for row in report["joints"]}
    assert report["exact_action_sha256"] == hashlib.sha256(
        command.tobytes(order="C")
    ).hexdigest()
    assert (
        rows["shoulder_lift"]["identifiability_verdict"]
        == "not_identifiable_insufficient_command_span"
    )
    assert rows["shoulder_lift"]["command_span_degrees"] == 0
    assert (
        rows["elbow_flex"]["identifiability_verdict"]
        == "not_identifiable_insufficient_command_span"
    )
    assert (
        rows["wrist_flex"]["identifiability_verdict"]
        == "not_identifiable_insufficient_bidirectional_excitation"
    )
    assert (
        rows["shoulder_pan"]["identifiability_verdict"]
        == "diagnostic_identifiable_for_unloaded_tracking_only"
    )
    assert report["shoulder_lift_hypothesis"][
        "joint_specific_range_scale_identified"
    ] is False
    assert report["simulator_replays_used"] == 0
    assert report["physical_trials_used"] == 0
    assert receipt["simulator_parameter_promoted"] is False
    assert receipt["task_score_changed"] is False


def test_repeated_materialization_is_byte_identical(tmp_path: Path) -> None:
    contract_path, _ = _fixture(tmp_path)
    with patch.object(joint_identifiability, "REPO_ROOT", tmp_path):
        derive_joint_identifiability_report(
            tmp_path / "first", contract_path=contract_path
        )
        derive_joint_identifiability_report(
            tmp_path / "second", contract_path=contract_path
        )
    assert (tmp_path / "first/report.json").read_bytes() == (
        tmp_path / "second/report.json"
    ).read_bytes()
    assert (tmp_path / "first/receipt.json").read_bytes() == (
        tmp_path / "second/receipt.json"
    ).read_bytes()


def test_source_tamper_and_output_replay_fail_closed(tmp_path: Path) -> None:
    contract_path, _ = _fixture(tmp_path)
    samples_path = tmp_path / "recording/samples.jsonl"
    samples_path.write_text(
        samples_path.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )
    with (
        patch.object(joint_identifiability, "REPO_ROOT", tmp_path),
        pytest.raises(JointIdentifiabilityError, match="Source sample bytes changed"),
    ):
        derive_joint_identifiability_report(
            tmp_path / "tampered", contract_path=contract_path
        )

    contract_path, _ = _fixture(tmp_path)
    output = tmp_path / "existing"
    output.mkdir()
    (output / "keep.txt").write_text("do not overwrite", encoding="utf-8")
    with (
        patch.object(joint_identifiability, "REPO_ROOT", tmp_path),
        pytest.raises(JointIdentifiabilityError, match="overwrite is refused"),
    ):
        derive_joint_identifiability_report(output, contract_path=contract_path)
