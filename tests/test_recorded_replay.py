from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from sim2claw.recorded_replay import (
    EPISODE_SCHEMA,
    REPLAY_RECEIPT_SCHEMA,
    ReplayContractError,
    calculate_metrics,
    load_recorded_episode,
    load_sysid_config,
    replay_recorded_episode,
    simulate_and_align,
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
        with self.assertRaisesRegex(ReplayContractError, "pawn_body binding"):
            simulate_and_align(
                self.episode,
                self.config,
                parameter_values={"pawn_mass_scale": 1.1},
                model_base_directory=FIXTURE_ROOT,
            )


if __name__ == "__main__":
    unittest.main()
