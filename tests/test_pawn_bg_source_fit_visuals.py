from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sim2claw.pawn_bg_demo_sim import BASELINE_JOINT_ADAPTER, JointAdapter
from sim2claw.pawn_bg_source_fit import EXPECTED_CONTRACT_SHA256, SourceFitError
from sim2claw.pawn_bg_source_fit_visuals import (
    EXPECTED_C922_ANGLE_CONTRACT_SHA256,
    _c922_angle_camera,
    _load_c922_angle_contract,
    _load_receipt,
    render_score_history,
)


def _aggregate(reward: float, clipped: int) -> dict[str, object]:
    return {
        "episode_count": 11,
        "finite_episode_count": 11,
        "maximum_piece_rise_m": 0.0,
        "mean_diagnostic_reward": reward,
        "mean_final_center_distance_m": 0.04445,
        "piece_lift_episode_count": 0,
        "recordings_with_actual_rows_outside_limits": clipped,
        "recordings_with_clipped_commands": clipped,
        "release_episode_count": 11,
        "selected_piece_contact_episode_count": 0,
        "task_consequence_success_count": 0,
    }


def _receipt() -> dict[str, object]:
    candidate = JointAdapter(
        adapter_id="candidate",
        body_joint_signs=(-1, 1, 1, 1, -1),
        body_joint_zero_offsets_rad=(0.1, 0.2, 0.3, 0.4, 0.5),
        evidence_class="test_only_not_calibrated",
    )
    return {
        "schema_version": "sim2claw.pawn_bg_source_fit_receipt.v1",
        "source_fit_contract_sha256": EXPECTED_CONTRACT_SHA256,
        "reward_contract_sha256": "a" * 64,
        "contact_prior_sha256": "b" * 64,
        "baseline": {
            "adapter": BASELINE_JOINT_ADAPTER.receipt(),
            "kinematic": {"event_rms_distance_m": 0.3},
            "nominal_physics": {"aggregate": _aggregate(0.1, 11)},
        },
        "best_candidate_adapter": candidate.receipt(),
        "best_candidate_kinematic": {"event_rms_distance_m": 0.12},
        "candidate_accepted": False,
        "optimization_status": "terminal_negative_no_source_fit_adapter_accepted",
        "final_contact_variants": {
            variant_id: {"aggregate": _aggregate(-0.5, 0)}
            for variant_id in (
                "nominal_uncalibrated",
                "rubber_tip_low",
                "rubber_tip_nominal_prior",
                "rubber_tip_high",
            )
        },
    }


class PawnBGSourceFitVisualTests(unittest.TestCase):
    def test_c922_angle_transfer_is_hash_pinned_and_visual_only(self) -> None:
        contract = _load_c922_angle_contract()
        self.assertEqual(
            EXPECTED_C922_ANGLE_CONTRACT_SHA256,
            "4179694f20bc1e5aa6270bb20f0b2a616d99845d15cdb00773bac9f1aec24f71",
        )
        self.assertTrue(contract["authority"]["visual_comparison_only"])
        self.assertFalse(
            contract["authority"]["physical_camera_calibration_claimed"]
        )
        self.assertFalse(contract["authority"]["metric_pose_authority"])
        self.assertEqual(
            contract["render_contract"][
                "physical_board_axes_to_simulation_yaw_degrees"
            ],
            180.0,
        )

    def test_c922_angle_transfer_reprojects_current_board_angle(self) -> None:
        contract = _load_c922_angle_contract()
        camera = _c922_angle_camera(contract, (0.04, -0.065))
        self.assertLess(camera["board_corner_reprojection_rms_px"], 2.0)
        self.assertLess(camera["board_corner_reprojection_max_px"], 3.1)
        self.assertAlmostEqual(camera["vertical_fov_degrees"], 41.3892809568)
        self.assertEqual(camera["camera_position_world"].shape, (3,))
        self.assertEqual(camera["camera_cv_to_world"].shape, (3, 3))

    def test_score_history_binds_comparable_rows_and_writes_chart(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt_path = root / "receipt.json"
            receipt_path.write_text(json.dumps(_receipt()), encoding="utf-8")
            history = render_score_history(
                source_fit_receipt_path=receipt_path,
                output_directory=root / "visuals",
            )
            self.assertEqual(len(history["rows"]), 5)
            self.assertEqual(history["rows"][0]["recordings_with_clipped_commands"], 11)
            self.assertEqual(history["rows"][1]["recordings_with_clipped_commands"], 0)
            self.assertFalse(history["rows"][1]["accepted"])
            self.assertEqual(
                [row["contact_variant_id"] for row in history["rows"]],
                [
                    "nominal_uncalibrated",
                    "nominal_uncalibrated",
                    "rubber_tip_low",
                    "rubber_tip_nominal_prior",
                    "rubber_tip_high",
                ],
            )
            self.assertTrue((root / "visuals/source_fit_score_history.json").is_file())
            self.assertTrue((root / "visuals/source_fit_score_history.png").is_file())

    def test_visual_receipt_rejects_another_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "receipt.json"
            payload = _receipt()
            payload["source_fit_contract_sha256"] = "0" * 64
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(SourceFitError, "another contract"):
                _load_receipt(path)

    def test_score_history_rejects_missing_contact_variant(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "receipt.json"
            payload = _receipt()
            del payload["final_contact_variants"]["rubber_tip_high"]
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(SourceFitError, "variants drifted"):
                render_score_history(
                    source_fit_receipt_path=path,
                    output_directory=root / "visuals",
                )


if __name__ == "__main__":
    unittest.main()
