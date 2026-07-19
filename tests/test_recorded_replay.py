from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import mujoco

from sim2claw.recorded_replay import (
    EPISODE_SCHEMA,
    REPLAY_RECEIPT_SCHEMA,
    ReplayContractError,
    ReplayRangeError,
    _align_continuous,
    _apply_parameters,
    _compile_model,
    calculate_metrics,
    load_recorded_episode,
    load_sysid_config,
    replay_recorded_episode,
    simulate_and_align,
    nominal_parameter_values,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "sysid"
CONFIG_PATH = FIXTURE_ROOT / "smooth_slider_sysid_v1.json"
EPISODE_PATH = FIXTURE_ROOT / "recorded_slider_episode_v1.json"


class RecordedReplayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_sysid_config(CONFIG_PATH)
        self.episode = load_recorded_episode(EPISODE_PATH, self.config)

    def test_deterministic_replay_aligns_to_exact_measured_timestamps(self) -> None:
        first = simulate_and_align(
            self.episode,
            self.config,
            model_base_directory=FIXTURE_ROOT,
        )
        second = simulate_and_align(
            self.episode,
            self.config,
            model_base_directory=FIXTURE_ROOT,
        )
        self.assertEqual(first["synchronized_rows"], second["synchronized_rows"])
        self.assertEqual(first["timing"], second["timing"])
        self.assertEqual(first["timing"]["command_interpolation"], "zero_order_hold")
        self.assertEqual(first["timing"]["model_timestep_seconds"], 0.01)
        self.assertTrue(first["control_diagnostics"]["exact_command_replay"])
        self.assertFalse(first["control_diagnostics"]["clipping_performed"])
        self.assertEqual(
            first["synchronized_rows"][1]["requested_control_joint_position"],
            first["synchronized_rows"][1]["applied_control_joint_position"],
        )
        self.assertEqual(len(first["synchronized_rows"]), 5)
        np.testing.assert_allclose(
            [row["timestamp_seconds"] for row in first["synchronized_rows"]],
            [0.0, 0.03, 0.07, 0.11, 0.16],
            atol=1e-12,
        )

    def test_timestamp_mismatch_is_rejected_without_repair(self) -> None:
        payload = json.loads(EPISODE_PATH.read_text(encoding="utf-8"))
        payload["samples"][2]["timestamp_seconds"] = payload["samples"][1][
            "timestamp_seconds"
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad-time.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ReplayContractError, "strictly increasing"):
                load_recorded_episode(path, self.config)

    def test_missing_observables_are_explicit_in_rows_metrics_and_receipt(self) -> None:
        replay = simulate_and_align(
            self.episode,
            self.config,
            model_base_directory=FIXTURE_ROOT,
        )
        metrics = calculate_metrics(replay, self.config)
        self.assertTrue(metrics["joint_position"]["available"])
        self.assertTrue(metrics["end_effector_position"]["available"])
        self.assertFalse(metrics["pawn_position"]["available"])
        self.assertIn("fixture has no pawn", metrics["pawn_position"]["reason"])
        row = replay["synchronized_rows"][0]
        self.assertIsNone(row["measured"].get("pawn_position_m"))
        self.assertIsNone(row["sim_minus_measured"]["pawn_position"])
        self.assertFalse(
            row["observable_availability"]["pawn_position"]["available"]
        )
        with tempfile.TemporaryDirectory() as temporary:
            receipt = replay_recorded_episode(
                EPISODE_PATH,
                config_path=CONFIG_PATH,
                output_directory=Path(temporary),
            )
            self.assertEqual(receipt["schema_version"], REPLAY_RECEIPT_SCHEMA)
            self.assertEqual(
                receipt["source"]["schema_version"], EPISODE_SCHEMA
            )
            self.assertFalse(
                receipt["observable_availability"]["pawn_position"]["available"]
            )
            self.assertEqual(receipt["proof"]["proof_class"], "replay")
            self.assertFalse(receipt["proof"]["physical_task_verified"])
            self.assertFalse(receipt["proof"]["gateway_or_motion_authority"])
            self.assertTrue((Path(temporary) / "synchronized.jsonl").is_file())
            self.assertTrue((Path(temporary) / "replay_receipt.json").is_file())

    def test_parameter_bounds_fail_closed(self) -> None:
        with self.assertRaisesRegex(ReplayContractError, "outside its bounds"):
            simulate_and_align(
                self.episode,
                self.config,
                parameter_values={"actuator_gain_scale": 1.5001},
                model_base_directory=FIXTURE_ROOT,
            )
        with self.assertRaisesRegex(ReplayContractError, "object-body binding"):
            simulate_and_align(
                self.episode,
                self.config,
                parameter_values={"pawn_mass_scale": 1.1},
                model_base_directory=FIXTURE_ROOT,
            )

    def test_four_joint_vector_alignment_is_not_quaternion_normalized(self) -> None:
        aligned = _align_continuous(
            np.asarray([0.0, 1.0]),
            [[1.0, 2.0, 3.0, 4.0], [2.0, 4.0, 6.0, 8.0]],
            np.asarray([0.5]),
            semantic="vector",
        )
        np.testing.assert_allclose(aligned, [[1.5, 3.0, 4.5, 6.0]])
        self.assertNotAlmostEqual(float(np.linalg.norm(aligned[0])), 1.0)

    def test_quaternion_alignment_uses_explicit_semantics_and_unit_normalizes(self) -> None:
        aligned = _align_continuous(
            np.asarray([0.0, 1.0]),
            [[1.0, 0.0, 0.0, 0.0], [-0.707106781, 0.0, 0.0, -0.707106781]],
            np.asarray([0.5]),
            semantic="quaternion_wxyz",
        )
        self.assertAlmostEqual(float(np.linalg.norm(aligned[0])), 1.0, places=12)
        self.assertGreater(aligned[0, 0], 0.0)
        self.assertGreater(aligned[0, 3], 0.0)

    def test_object_observables_require_measured_body_pose_binding(self) -> None:
        payload = json.loads(EPISODE_PATH.read_text(encoding="utf-8"))
        payload["unavailable_observables"].pop("pawn_position")
        for sample in payload["samples"]:
            sample["measured"]["pawn_position_m"] = [0.2, 0.0, 0.2]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "missing-object-binding.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                ReplayContractError, "pawn/contact observables require"
            ):
                load_recorded_episode(path, self.config)

    def test_named_free_object_is_initialized_to_exact_measured_pose(self) -> None:
        payload = json.loads(EPISODE_PATH.read_text(encoding="utf-8"))
        position = [0.31, -0.12, 0.27]
        quaternion = [0.9238795325, 0.0, 0.0, 0.3826834324]
        payload["initial_object_state"] = {
            "status": "available",
            "body_name": "fixture_object",
            "free_joint_name": "fixture_object_free",
            "frame": "world",
            "position_unit": "m",
            "orientation_convention": "wxyz_unit_quaternion",
            "linear_velocity_unit": "m/s",
            "angular_velocity_unit": "rad/s",
            "position": position,
            "quaternion_wxyz": quaternion,
            "linear_velocity": [0.0, 0.0, 0.0],
            "angular_velocity": [0.0, 0.0, 0.0],
            "measurement_provenance": {
                "source_id": "fixture-object-pose",
                "measurement_method": "synthetic_exact_state",
                "sha256": "a" * 64,
            },
        }
        payload["unavailable_observables"].pop("pawn_position")
        payload["unavailable_observables"].pop("pawn_orientation")
        for sample in payload["samples"]:
            sample["measured"]["pawn_position_m"] = position
            sample["measured"]["pawn_quaternion_wxyz"] = quaternion
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bound-object.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            episode = load_recorded_episode(path, self.config)
            replay = simulate_and_align(
                episode,
                self.config,
                model_base_directory=FIXTURE_ROOT,
            )
        np.testing.assert_allclose(replay["simulated"]["pawn_position"][0], position)
        np.testing.assert_allclose(
            replay["simulated"]["pawn_orientation"][0], quaternion, atol=1e-9
        )

    def test_object_pose_shape_unit_frame_and_hash_provenance_fail_closed(self) -> None:
        base = json.loads(EPISODE_PATH.read_text(encoding="utf-8"))
        available = {
            "status": "available",
            "body_name": "fixture_object",
            "free_joint_name": "fixture_object_free",
            "frame": "world",
            "position_unit": "m",
            "orientation_convention": "wxyz_unit_quaternion",
            "linear_velocity_unit": "m/s",
            "angular_velocity_unit": "rad/s",
            "position": [0.2, 0.0, 0.2],
            "quaternion_wxyz": [1.0, 0.0, 0.0, 0.0],
            "linear_velocity": [0.0, 0.0, 0.0],
            "angular_velocity": [0.0, 0.0, 0.0],
            "measurement_provenance": {
                "source_id": "fixture",
                "measurement_method": "synthetic_exact_state",
                "sha256": "a" * 64,
            },
        }
        mutations = [
            ("3 finite values", lambda value: value.update(position=[0.2, 0.0])),
            ("position_unit", lambda value: value.update(position_unit="cm")),
            ("pose frame", lambda value: value.update(frame="camera")),
            (
                "hash-bound measurement provenance",
                lambda value: value["measurement_provenance"].update(sha256="bad"),
            ),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, (message, mutate) in enumerate(mutations):
                payload = copy.deepcopy(base)
                value = copy.deepcopy(available)
                mutate(value)
                payload["initial_object_state"] = value
                path = root / f"bad-object-{index}.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.subTest(message=message), self.assertRaisesRegex(
                    ReplayContractError, message
                ):
                    load_recorded_episode(path, self.config)
            wrong_model_units = copy.deepcopy(base)
            wrong_model_units["initial_state"]["joint_position_units"] = [
                "radian"
            ]
            wrong_model_units["initial_state"]["joint_velocity_units"] = [
                "radian_per_second"
            ]
            wrong_model_path = root / "wrong-model-units.json"
            wrong_model_path.write_text(
                json.dumps(wrong_model_units), encoding="utf-8"
            )
            episode = load_recorded_episode(wrong_model_path, self.config)
            with self.assertRaisesRegex(
                ReplayContractError, "must match its MuJoCo joint type"
            ):
                simulate_and_align(
                    episode,
                    self.config,
                    model_base_directory=FIXTURE_ROOT,
                )

    def test_out_of_range_state_or_command_never_silently_clips(self) -> None:
        payload = json.loads(EPISODE_PATH.read_text(encoding="utf-8"))
        payload["initial_state"]["joint_position"] = [1.1]
        payload["samples"][0]["measured"]["joint_position"] = [1.1]
        payload["samples"][0]["command_joint_position"] = [1.2]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "out-of-range.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            episode = load_recorded_episode(path, self.config)
            with self.assertRaisesRegex(ReplayRangeError, "clipping"):
                simulate_and_align(
                    episode,
                    self.config,
                    model_base_directory=FIXTURE_ROOT,
                )

    def test_canonical_initial_joint_velocity_and_units_are_required(self) -> None:
        base = json.loads(EPISODE_PATH.read_text(encoding="utf-8"))
        cases = []
        missing = copy.deepcopy(base)
        missing["initial_state"].pop("joint_velocity")
        cases.append(("joint_velocity", missing))
        nonfinite = copy.deepcopy(base)
        nonfinite["initial_state"]["joint_velocity"] = [float("nan")]
        cases.append(("finite values", nonfinite))
        wrong_shape = copy.deepcopy(base)
        wrong_shape["initial_state"]["joint_velocity"] = [0.0, 0.0]
        cases.append(("contain 1 finite values", wrong_shape))
        missing_units = copy.deepcopy(base)
        missing_units["initial_state"].pop("joint_velocity_units")
        cases.append(("units must match", missing_units))
        wrong_unit_shape = copy.deepcopy(base)
        wrong_unit_shape["initial_state"]["joint_velocity_units"] = [
            "meter_per_second",
            "meter_per_second",
        ]
        cases.append(("units must match", wrong_unit_shape))
        semantic_mismatch = copy.deepcopy(base)
        semantic_mismatch["initial_state"]["joint_velocity_units"] = [
            "radian_per_second"
        ]
        cases.append(("unsupported semantics", semantic_mismatch))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, (message, payload) in enumerate(cases):
                path = root / f"bad-initial-velocity-{index}.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.subTest(message=message), self.assertRaisesRegex(
                    ReplayContractError, message
                ):
                    load_recorded_episode(path, self.config)

    def test_mass_scaling_preserves_mass_inertia_ratio(self) -> None:
        model, _ = _compile_model(self.config, base_directory=FIXTURE_ROOT)
        body_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_BODY, "fixture_object"
        )
        original_mass = float(model.body_mass[body_id])
        original_inertia = model.body_inertia[body_id].copy()
        original_subtree_mass = float(model.body_subtreemass[body_id])
        values = nominal_parameter_values(self.config)
        values["pawn_mass_scale"] = 1.5
        _apply_parameters(
            model,
            self.config,
            values,
            object_body_name="fixture_object",
        )
        self.assertAlmostEqual(float(model.body_mass[body_id]), original_mass * 1.5)
        np.testing.assert_allclose(model.body_inertia[body_id], original_inertia * 1.5)
        self.assertAlmostEqual(
            float(model.body_subtreemass[body_id]), original_subtree_mass * 1.5
        )

    def test_replay_receipt_source_identity_is_relocation_invariant(self) -> None:
        payload = EPISODE_PATH.read_text(encoding="utf-8")
        sources = []
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            for root_text in (first, second):
                root = Path(root_text)
                episode_path = root / "episode.json"
                episode_path.write_text(payload, encoding="utf-8")
                receipt = replay_recorded_episode(
                    episode_path,
                    config_path=CONFIG_PATH,
                    output_directory=root / "output",
                )
                sources.append(receipt["source"])
                self.assertNotIn(root_text, json.dumps(receipt["source"]))
                self.assertEqual(
                    receipt["initial_joint_state"]["joint_velocity"], [0.0]
                )
                self.assertEqual(
                    receipt["initial_joint_state"]["joint_velocity_units"],
                    ["meter_per_second"],
                )
        self.assertEqual(sources[0], sources[1])


if __name__ == "__main__":
    unittest.main()
