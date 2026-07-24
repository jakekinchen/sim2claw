from __future__ import annotations

import hashlib
import json
from pathlib import Path

import mujoco
import numpy as np

import sim2claw.hil_simulator_comparison as comparison
from sim2claw.hil_identifiability import action_tensor_sha256
from sim2claw.hil_simulator_comparison import (
    _evaluate,
    _load_source,
    load_hil_simulator_contract,
)
from sim2claw.joint_limit_comparison import _apply_calibrated_ranges, _model_binding
from sim2claw.scene import CURRENT_TASK_PIECE_LAYOUT, ROBOT_JOINTS, build_scene_spec


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "hil_shoulder_range_external_validation_v1.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_contract_freezes_two_replays_and_shoulder_only_scope() -> None:
    contract = load_hil_simulator_contract(CONTRACT)
    assert contract["budget"]["simulator_replays"] == 2
    assert contract["simulator"]["variants"][1]["mutated_joints"] == [
        "shoulder_lift"
    ]
    assert all(value is False for value in contract["authority"].values())


def test_shoulder_only_range_mutation_leaves_other_ranges_byte_identical() -> None:
    model = build_scene_spec(piece_layout=CURRENT_TASK_PIECE_LAYOUT).compile()
    actuator_ids, joint_ids, _ = _model_binding(model)
    before_joint = model.jnt_range[joint_ids].copy()
    before_ctrl = model.actuator_ctrlrange[actuator_ids].copy()
    ranges = {
        joint: [-120.0 - index, 120.0 + index]
        for index, joint in enumerate(ROBOT_JOINTS[:-1])
    }
    _apply_calibrated_ranges(
        model,
        actuator_ids,
        joint_ids,
        ranges,
        mutated_joints=("shoulder_lift",),
    )
    target = list(ROBOT_JOINTS).index("shoulder_lift")
    for index in range(len(ROBOT_JOINTS)):
        if index == target:
            assert not np.array_equal(model.jnt_range[joint_ids[index]], before_joint[index])
            assert not np.array_equal(
                model.actuator_ctrlrange[actuator_ids[index]], before_ctrl[index]
            )
        else:
            assert np.array_equal(
                model.jnt_range[joint_ids[index]], before_joint[index]
            )
            assert np.array_equal(
                model.actuator_ctrlrange[actuator_ids[index]], before_ctrl[index]
            )


def test_source_loader_rejects_action_substitution(tmp_path: Path, monkeypatch) -> None:
    packet = tmp_path / "runs" / "packet"
    source = packet / "source"
    replay = packet / "replay"
    source.mkdir(parents=True)
    replay.mkdir()
    actions = np.ascontiguousarray(
        [
            [0.0, -100.0, 90.0, 0.0, 0.0, 2.0],
            [0.0, -99.0, 90.0, 0.0, 0.0, 2.0],
        ],
        dtype="<f8",
    )
    np.save(source / "actions.npy", actions, allow_pickle=False)
    (packet / "raw_receipt.json").write_text("{}", encoding="utf-8")
    (packet / "evaluation.json").write_text(
        json.dumps(
            {"verdict": "admit_unloaded_joint_measurement", "admitted": True}
        ),
        encoding="utf-8",
    )
    rows = [
        {
            "replay_phase": "source_trace",
            "requested_source_command_degrees": action.tolist(),
            "follower_actual_position_degrees": action.tolist(),
            "source_elapsed_seconds": 0.05 * index,
        }
        for index, action in enumerate(actions)
    ]
    samples = replay / "samples.jsonl"
    samples.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    contract = {
        "source": {
            "packet_directory": "runs/packet",
            "raw_receipt_sha256": _sha(packet / "raw_receipt.json"),
            "evaluation_sha256": _sha(packet / "evaluation.json"),
            "evaluation_verdict": "admit_unloaded_joint_measurement",
            "action_tensor_path": "source/actions.npy",
            "action_tensor_file_sha256": _sha(source / "actions.npy"),
            "action_tensor_sha256": action_tensor_sha256(actions),
            "action_shape": [2, 6],
            "replay_samples_path": "replay/samples.jsonl",
            "replay_samples_sha256": _sha(samples),
        }
    }
    monkeypatch.setattr(comparison, "REPO_ROOT", tmp_path)
    loaded, actual, timestamps = _load_source(contract)
    assert np.array_equal(loaded, actions)
    assert np.array_equal(actual, actions)
    assert timestamps.tolist() == [0.0, 0.05]
    rows[1]["requested_source_command_degrees"][1] += 1.0
    samples.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    contract["source"]["replay_samples_sha256"] = _sha(samples)
    try:
        _load_source(contract)
    except Exception as error:
        assert "requested action bytes changed" in str(error)
    else:
        raise AssertionError("action substitution was not rejected")


def test_independent_evaluator_requires_target_gain_and_nonregression() -> None:
    contract = load_hil_simulator_contract(CONTRACT)

    def result(body: list[float], gripper: float, digest: str) -> dict:
        return {
            "input_action_sha256": digest,
            "input_action_shape": [201, 6],
            "input_action_dtype": "float64",
            "metrics": {
                "body_joint_rmse_degrees": body,
                "gripper_rmse_actuator_rad": gripper,
            },
        }

    baseline = result([1.0, 10.0, 1.0, 1.0, 1.0], 0.1, "a" * 64)
    candidate = result([1.0, 8.0, 1.0, 1.0, 1.0], 0.1, "a" * 64)
    accepted = _evaluate(baseline, candidate, contract)
    assert accepted["diagnostic_gain"] is True
    assert accepted["simulator_parameter_promoted"] is False
    regressed = result([1.5, 8.0, 1.0, 1.0, 1.0], 0.1, "a" * 64)
    rejected = _evaluate(baseline, regressed, contract)
    assert rejected["diagnostic_gain"] is False
    assert rejected["non_target_regression_gate_passed"] is False
