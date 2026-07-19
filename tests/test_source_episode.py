from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import mujoco
import numpy as np

from sim2claw.grasp import NECK_HEIGHT_M, _pinch_offset, _solve_reach
from sim2claw.scene import (
    CURRENT_TASK_PIECE_LAYOUT,
    TELEOP_PAWN_SOURCE_SQUARES,
    board_square_center,
    build_scene_spec,
    initialize_robot_poses,
)
from sim2claw.source_episode import (
    ACT_ADAPTER_SCHEMA,
    ADMISSION_SCHEMA,
    CURRENT_BOARD_POSE_ID,
    CURRENT_SCENE_ID,
    CONTRACT_PATH_V1,
    EPISODE_SCHEMA,
    GROOT_ADAPTER_SCHEMA,
    RECEIPT_SCHEMA,
    SAMPLE_SCHEMA,
    adapt_source_episode,
    admission_payload_sha256,
    load_source_contract,
    sha256_file,
    source_contract_sha256,
    tree_manifest,
    validate_source_contract,
)


def _sample(index: int) -> dict:
    timestamp = index / 20.0
    return {
        "schema_version": SAMPLE_SCHEMA,
        "episode_id": "episode-001",
        "sample_index": index,
        "timestamp_monotonic_seconds": timestamp,
        "language_instruction": "Pick up the tan pawn on c8 and place it upright on the empty square c6.",
        "rgb": {
            "top": {
                "available": True,
                "path": f"rgb/top/{index:06d}.png",
                "timestamp_monotonic_seconds": timestamp,
                "sha256": "top",
            },
            "wrist": {
                "available": True,
                "path": f"rgb/wrist/{index:06d}.png",
                "timestamp_monotonic_seconds": timestamp,
                "sha256": "wrist",
            },
        },
        "robot": {
            "joint_position_rad": [0.0] * 6,
            "joint_velocity_rad_s": [0.0] * 6,
            "end_effector_pose_world": [0.0, 0.0, 0.2, 1.0, 0.0, 0.0, 0.0],
            "gripper_joint_position_rad": 0.0,
        },
        "goal": {
            "selected_piece_pose_world": [0.0, 0.0, 0.1, 1.0, 0.0, 0.0, 0.0],
            "continuous_target_pose_world": [0.1, 0.1, 0.1, 1.0, 0.0, 0.0, 0.0],
        },
        "action": {
            "representation": "absolute_joint_position_target",
            "joint_target_rad": [index / 10.0] * 6,
            "owner": "geometric_expert",
            "assistance": 0,
            "intervention": int(index > 0),
        },
        "events": {"contacts": [], "simulator_events": []},
        "evaluator_privileged_state": {
            "inline": False,
            "path": "evaluator_privileged_state.jsonl",
            "row_index": index,
        },
    }


class CanonicalSourceEpisodeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name) / "episode"
        self.directory.mkdir()
        rows = [_sample(0), _sample(1), _sample(2)]
        for row in rows:
            for stream in ("top", "wrist"):
                frame_path = self.directory / row["rgb"][stream]["path"]
                frame_path.parent.mkdir(parents=True, exist_ok=True)
                frame_path.write_bytes(
                    f"fixture-{stream}-{row['sample_index']}".encode("utf-8")
                )
                row["rgb"][stream]["sha256"] = sha256_file(frame_path)
        samples_path = self.directory / "samples.jsonl"
        samples_path.write_text(
            "".join(
                json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                for row in rows
            ),
            encoding="utf-8",
        )
        privileged_path = self.directory / "evaluator_privileged_state.jsonl"
        privileged_path.write_text(
            "".join(
                json.dumps(
                    {
                        "episode_id": "episode-001",
                        "sample_index": index,
                        "policy_adapter_access": False,
                        "state": {"integration": [index]},
                    },
                    sort_keys=True,
                )
                + "\n"
                for index in range(3)
            ),
            encoding="utf-8",
        )
        initial_privileged_path = (
            self.directory / "initial_evaluator_privileged_state.json"
        )
        initial_privileged_path.write_text(
            json.dumps(
                {
                    "schema_version": "sim2claw.evaluator_initial_privileged_state.v1",
                    "episode_id": "episode-001",
                    "policy_adapter_access": False,
                    "state": {
                        "available": True,
                        "mj_state_spec": "mjSTATE_INTEGRATION",
                        "integration_state_float64": [0.0],
                    },
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        receipt = {
            "schema_version": RECEIPT_SCHEMA,
            "source_episode_schema": EPISODE_SCHEMA,
            "source_contract_sha256": source_contract_sha256(),
            "task_id": "chess_pick_place_source_episode_v2",
            "scene_id": CURRENT_SCENE_ID,
            "board_pose_id": CURRENT_BOARD_POSE_ID,
            "recording_id": "episode-001",
            "sample_count": 3,
            "samples_sha256": sha256_file(samples_path),
            "evaluator_privileged_state_path": privileged_path.name,
            "evaluator_privileged_state_sha256": sha256_file(privileged_path),
            "initial_evaluator_privileged_state_path": initial_privileged_path.name,
            "initial_evaluator_privileged_state_sha256": sha256_file(
                initial_privileged_path
            ),
            "rgb_streams": tree_manifest(self.directory / "rgb"),
        }
        self.receipt_path = self.directory / "recording_receipt.json"
        self.receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _verdict(self, **changes: object) -> dict:
        verdict = {
            "schema_version": ADMISSION_SCHEMA,
            "source_recording_id": "episode-001",
            "source_receipt_sha256": sha256_file(self.receipt_path),
            "source_samples_sha256": json.loads(
                self.receipt_path.read_text(encoding="utf-8")
            )["samples_sha256"],
            "scene_id": CURRENT_SCENE_ID,
            "board_pose_id": CURRENT_BOARD_POSE_ID,
            "held_out_membership": False,
            "strict_success": True,
            "exact_float32_sample_hold_replay_passed": True,
            "physics_steps_per_action": 10,
            "assistance_frames": 0,
            "admission_class": "ordinary_strict_success",
            "all_source_actions_admitted": True,
        }
        verdict.update(changes)
        verdict["canonical_payload_sha256"] = admission_payload_sha256(verdict)
        return verdict

    def test_contract_binds_current_100_mm_workcell_and_zero_heldout_rows(self) -> None:
        contract = load_source_contract()
        self.assertEqual(contract["scene"]["scene_id"], CURRENT_SCENE_ID)
        self.assertEqual(contract["scene"]["board_pose_id"], CURRENT_BOARD_POSE_ID)
        self.assertEqual(contract["scene"]["board_center_in_table_frame_xy_m"], [0.04, -0.065])
        self.assertEqual(contract["splits"]["held_out_training_rows"], 0)

        changed = json.loads(json.dumps(contract))
        changed["scene"]["board_center_in_table_frame_xy_m"] = [0.04, -0.165]
        with self.assertRaisesRegex(ValueError, "wrong board center"):
            validate_source_contract(changed)

        historical = load_source_contract(CONTRACT_PATH_V1)
        self.assertEqual(
            historical["scene"]["board_pose_id"],
            "board_robotward_72mm_20260718_v2",
        )

    def test_source_and_destination_cells_are_inside_left_arm_ik_envelope(self) -> None:
        contract = load_source_contract()
        model = build_scene_spec(piece_layout=CURRENT_TASK_PIECE_LAYOUT).compile()
        data = mujoco.MjData(model)
        initialize_robot_poses(model, data)
        mujoco.mj_forward(model, data)
        pinch = _pinch_offset(model, data, "left")
        pawn_height = float(
            data.xpos[
                mujoco.mj_name2id(
                    model, mujoco.mjtObj.mjOBJ_BODY, "tan_pawn_c8"
                )
            ][2]
        )

        for piece_id in contract["scene"]["source_piece_ids"]:
            body_id = mujoco.mj_name2id(
                model, mujoco.mjtObj.mjOBJ_BODY, piece_id
            )
            target = np.asarray(data.xpos[body_id], dtype=np.float64).copy()
            target[2] += NECK_HEIGHT_M["pawn"]
            _, residual = _solve_reach(model, data, "left", target, pinch)
            self.assertLessEqual(residual, 0.003, piece_id)

        for square in contract["scene"]["destination_squares"]:
            target = np.asarray(board_square_center(square), dtype=np.float64)
            target[2] = pawn_height + NECK_HEIGHT_M["pawn"]
            _, residual = _solve_reach(model, data, "left", target, pinch)
            self.assertLessEqual(residual, 0.003, square)

        for square in TELEOP_PAWN_SOURCE_SQUARES:
            body_id = mujoco.mj_name2id(
                model, mujoco.mjtObj.mjOBJ_BODY, f"brown_pawn_{square}"
            )
            target = np.asarray(data.xpos[body_id], dtype=np.float64).copy()
            target[2] += NECK_HEIGHT_M["pawn"]
            _, residual = _solve_reach(model, data, "left", target, pinch)
            self.assertGreater(residual, 0.003, square)

        for square in ("f4", "g4", "h4"):
            target = np.asarray(board_square_center(square), dtype=np.float64)
            target[2] = pawn_height + NECK_HEIGHT_M["pawn"]
            _, residual = _solve_reach(model, data, "left", target, pinch)
            self.assertGreater(residual, 0.003, square)

    def test_strict_success_adapts_to_act_and_groot_without_privileged_state(self) -> None:
        verdict = self._verdict()
        act_rows = adapt_source_episode(
            self.directory, adapter="act", admission_verdict=verdict
        )
        groot_rows = adapt_source_episode(
            self.directory, adapter="groot", admission_verdict=verdict
        )
        self.assertEqual(len(act_rows), 3)
        self.assertEqual(len(groot_rows), 3)
        self.assertEqual(act_rows[0]["schema_version"], ACT_ADAPTER_SCHEMA)
        self.assertEqual(groot_rows[0]["schema_version"], GROOT_ADAPTER_SCHEMA)
        self.assertNotIn("evaluator_privileged_state", json.dumps(act_rows))
        self.assertNotIn("evaluator_privileged_state", json.dumps(groot_rows))
        self.assertIn("top_rgb_path", groot_rows[0]["observation"])
        self.assertNotIn("top_rgb_path", act_rows[0]["observation"])

    def test_failure_and_assistance_contribute_zero_adapter_rows(self) -> None:
        for verdict, message in (
            (self._verdict(strict_success=False), "strict evaluator successes"),
            (self._verdict(assistance_frames=1), "Assisted|assisted"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    adapt_source_episode(
                        self.directory,
                        adapter="groot",
                        admission_verdict=verdict,
                    )

    def test_corrective_suffix_excludes_failed_prefix(self) -> None:
        verdict = self._verdict(
            admission_class="corrective_suffix",
            all_source_actions_admitted=False,
            corrective_suffix={
                "start_sample_index": 1,
                "end_sample_index_exclusive": 3,
                "exact_pre_failure_integration_state_matched": True,
                "failed_prefix_excluded_from_imitation_rows": True,
                "independent_full_episode_replay_passed": True,
                "corrective_actions_owned_by_declared_expert_or_teleoperator": True,
            },
        )
        rows = adapt_source_episode(
            self.directory, adapter="act", admission_verdict=verdict
        )
        self.assertEqual([row["lineage"]["source_sample_index"] for row in rows], [1, 2])


if __name__ == "__main__":
    unittest.main()
