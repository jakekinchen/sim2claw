from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import mujoco
import numpy as np

from sim2claw.pawn_source_evaluator import (
    evaluate_source_episode,
    load_pawn_evaluator_contract,
    score_pawn_consequences,
)
from sim2claw.scene import (
    CURRENT_TASK_LAYOUT_ID,
    CURRENT_TASK_PIECE_LAYOUT,
    ROBOT_JOINTS,
    board_square_center,
    build_scene_spec,
    initialize_robot_poses,
    registered_board_center,
)
from sim2claw.source_episode import (
    CURRENT_BOARD_POSE_ID,
    CURRENT_SCENE_ID,
    EPISODE_SCHEMA,
    RECEIPT_SCHEMA,
    SAMPLE_SCHEMA,
    sha256_file,
    source_contract_sha256,
    tree_manifest,
)


def _state(model: mujoco.MjModel, data: mujoco.MjData) -> list[float]:
    size = mujoco.mj_stateSize(model, mujoco.mjtState.mjSTATE_INTEGRATION)
    value = np.empty(size, dtype=np.float64)
    mujoco.mj_getState(model, data, value, mujoco.mjtState.mjSTATE_INTEGRATION)
    return value.astype(float).tolist()


class PawnSourceEvaluatorTest(unittest.TestCase):
    def test_contract_protects_all_pawns_and_binds_exact_executor(self) -> None:
        contract = load_pawn_evaluator_contract()
        self.assertEqual(len(contract["scene"]["protected_piece_ids"]), 16)
        self.assertEqual(contract["scene"]["scene_id"], CURRENT_SCENE_ID)
        self.assertEqual(contract["scene"]["board_pose_id"], CURRENT_BOARD_POSE_ID)
        self.assertEqual(contract["execution"]["physics_steps_per_action"], 10)
        self.assertEqual(contract["execution"]["action_dtype"], "float32")

    def test_each_consequence_class_can_fail_closed(self) -> None:
        baseline = {
            "selected_piece_identity": True,
            "maximum_piece_rise_m": 0.05,
            "final_xy_error_m": 0.01,
            "final_height_error_m": 0.001,
            "final_upright_cosine": 0.99,
            "final_linear_speed_m_s": 0.01,
            "gripper_clearance_m": 0.05,
            "maximum_other_piece_displacement_m": 0.001,
            "target_displacement_m": 0.10,
            "wrong_piece_contact": False,
            "final_jaw_piece_contact": False,
            "assistance_frames": 0,
            "declared_action_owner": True,
            "executed_action_count": 10,
            "recorded_action_count": 10,
            "exact_sample_hold_state_replay": True,
        }
        self.assertTrue(score_pawn_consequences(baseline)["success"])
        failures = {
            "selected_piece_identity": False,
            "maximum_piece_rise_m": 0.0,
            "final_xy_error_m": 0.02,
            "final_height_error_m": 0.01,
            "final_upright_cosine": 0.0,
            "final_linear_speed_m_s": 0.1,
            "gripper_clearance_m": 0.0,
            "maximum_other_piece_displacement_m": 0.02,
            "target_displacement_m": 0.6,
            "wrong_piece_contact": True,
            "final_jaw_piece_contact": True,
            "assistance_frames": 1,
            "declared_action_owner": False,
            "executed_action_count": 9,
            "exact_sample_hold_state_replay": False,
        }
        for field, bad_value in failures.items():
            with self.subTest(field=field):
                measurements = dict(baseline)
                measurements[field] = bad_value
                self.assertFalse(score_pawn_consequences(measurements)["success"])

    def test_exact_sample_hold_replay_passes_but_failed_task_exports_zero_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "episode"
            directory.mkdir()
            model = build_scene_spec(piece_layout=CURRENT_TASK_PIECE_LAYOUT).compile()
            data = mujoco.MjData(model)
            initialize_robot_poses(model, data)
            mujoco.mj_forward(model, data)
            actuator_ids = np.asarray(
                [
                    mujoco.mj_name2id(
                        model,
                        mujoco.mjtObj.mjOBJ_ACTUATOR,
                        f"left_{joint}",
                    )
                    for joint in ROBOT_JOINTS
                ],
                dtype=np.int32,
            )
            qpos_addresses = np.asarray(
                [
                    model.jnt_qposadr[
                        mujoco.mj_name2id(
                            model,
                            mujoco.mjtObj.mjOBJ_JOINT,
                            f"left_{joint}",
                        )
                    ]
                    for joint in ROBOT_JOINTS
                ],
                dtype=np.int32,
            )
            dof_addresses = np.asarray(
                [
                    model.jnt_dofadr[
                        mujoco.mj_name2id(
                            model,
                            mujoco.mjtObj.mjOBJ_JOINT,
                            f"left_{joint}",
                        )
                    ]
                    for joint in ROBOT_JOINTS
                ],
                dtype=np.int32,
            )
            target_body = mujoco.mj_name2id(
                model, mujoco.mjtObj.mjOBJ_BODY, "tan_pawn_c8"
            )
            gripper_body = mujoco.mj_name2id(
                model, mujoco.mjtObj.mjOBJ_BODY, "left_gripper"
            )
            initial_state = _state(model, data)
            target_position = board_square_center(
                "c6",
                board_center_in_table_frame_xy_m=registered_board_center(
                    CURRENT_SCENE_ID
                ),
            )
            continuous_target_pose = [
                *target_position,
                1.0,
                0.0,
                0.0,
                0.0,
            ]
            initial_path = directory / "initial_evaluator_privileged_state.json"
            initial_path.write_text(
                json.dumps(
                    {
                        "episode_id": "fixture-episode",
                        "policy_adapter_access": False,
                        "state": {
                            "available": True,
                            "mj_state_spec": "mjSTATE_INTEGRATION",
                            "integration_state_float64": initial_state,
                        },
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            rows = []
            privileged = []
            command = np.asarray(data.ctrl[actuator_ids], dtype=np.float32)
            for index in range(2):
                data.ctrl[actuator_ids] = command.astype(np.float64)
                mujoco.mj_step(model, data, nstep=10)
                piece_pose = [
                    *data.xpos[target_body].astype(float).tolist(),
                    *data.xquat[target_body].astype(float).tolist(),
                ]
                end_effector_pose = [
                    *data.xpos[gripper_body].astype(float).tolist(),
                    *data.xquat[gripper_body].astype(float).tolist(),
                ]
                timestamp = index / 20.0
                row = {
                    "schema_version": SAMPLE_SCHEMA,
                    "episode_id": "fixture-episode",
                    "sample_index": index,
                    "timestamp_monotonic_seconds": timestamp,
                    "language_instruction": "Pick up the tan pawn on c8 and place it upright on the empty square c6.",
                    "rgb": {},
                    "robot": {
                        "joint_position_rad": data.qpos[qpos_addresses].astype(float).tolist(),
                        "joint_velocity_rad_s": data.qvel[dof_addresses].astype(float).tolist(),
                        "end_effector_pose_world": end_effector_pose,
                        "gripper_joint_position_rad": float(data.qpos[qpos_addresses[-1]]),
                    },
                    "goal": {
                        "selected_piece_pose_world": piece_pose,
                        "continuous_target_pose_world": continuous_target_pose,
                    },
                    "action": {
                        "representation": "absolute_joint_position_target",
                        "joint_target_rad": command.astype(float).tolist(),
                        "owner": "geometric_expert",
                        "assistance": 0,
                        "intervention": 0,
                    },
                    "events": {"contacts": [], "simulator_events": []},
                    "evaluator_privileged_state": {
                        "inline": False,
                        "path": "evaluator_privileged_state.jsonl",
                        "row_index": index,
                    },
                }
                for stream in ("top", "wrist"):
                    frame_path = directory / "rgb" / stream / f"{index:06d}.png"
                    frame_path.parent.mkdir(parents=True, exist_ok=True)
                    frame_path.write_bytes(f"{stream}-{index}".encode("utf-8"))
                    row["rgb"][stream] = {
                        "available": True,
                        "path": frame_path.relative_to(directory).as_posix(),
                        "timestamp_monotonic_seconds": timestamp,
                        "sha256": sha256_file(frame_path),
                    }
                rows.append(row)
                privileged.append(
                    {
                        "episode_id": "fixture-episode",
                        "sample_index": index,
                        "policy_adapter_access": False,
                        "state": {
                            "available": True,
                            "mj_state_spec": "mjSTATE_INTEGRATION",
                            "integration_state_float64": _state(model, data),
                        },
                    }
                )
            samples_path = directory / "samples.jsonl"
            samples_path.write_text(
                "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
                encoding="utf-8",
            )
            privileged_path = directory / "evaluator_privileged_state.jsonl"
            privileged_path.write_text(
                "".join(
                    json.dumps(row, sort_keys=True) + "\n" for row in privileged
                ),
                encoding="utf-8",
            )
            receipt = {
                "schema_version": RECEIPT_SCHEMA,
                "source_episode_schema": EPISODE_SCHEMA,
                "source_contract_sha256": source_contract_sha256(),
                "task_id": "chess_pick_place_source_episode_v2",
                "recording_id": "fixture-episode",
                "sample_count": len(rows),
                "sample_hz": 20,
                "piece_id": "tan_pawn_c8",
                "destination_square": "c6",
                "scene_id": CURRENT_SCENE_ID,
                "board_pose_id": CURRENT_BOARD_POSE_ID,
                "piece_layout": CURRENT_TASK_PIECE_LAYOUT,
                "initial_layout_id": CURRENT_TASK_LAYOUT_ID,
                "samples_sha256": sha256_file(samples_path),
                "evaluator_privileged_state_path": privileged_path.name,
                "evaluator_privileged_state_sha256": sha256_file(privileged_path),
                "initial_evaluator_privileged_state_path": initial_path.name,
                "initial_evaluator_privileged_state_sha256": sha256_file(initial_path),
                "rgb_streams": tree_manifest(directory / "rgb"),
            }
            (directory / "recording_receipt.json").write_text(
                json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8"
            )

            verdict = evaluate_source_episode(directory)
            self.assertTrue(verdict["exact_float32_sample_hold_replay_passed"])
            self.assertFalse(verdict["strict_success"])
            self.assertEqual(verdict["training_rows_authorized"], 0)
            self.assertEqual(verdict["admission_class"], "counterexample_only")
            self.assertFalse(verdict["gates"]["minimum_piece_rise"]["passed"])


if __name__ == "__main__":
    unittest.main()
