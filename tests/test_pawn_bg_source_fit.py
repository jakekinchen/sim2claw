from __future__ import annotations

import copy
import json
import unittest

import numpy as np

from sim2claw.pawn_bg_source_fit import (
    CONTRACT_PATH,
    SourceFitError,
    _adapter_limit_report,
    _candidate_beats_baseline,
    _offset_bounds,
    extract_phase_indices,
    load_source_fit_contract,
    validate_source_fit_contract,
)
from sim2claw.pawn_bg_demo_sim import JointAdapter


def _sample(gripper: float, body: list[float] | None = None) -> dict[str, object]:
    joints = [0.0, 0.0, 0.0, 0.0, 0.0] if body is None else body
    return {
        "follower_actual_position_degrees": [*joints, gripper],
        "follower_command_degrees": [*joints, gripper],
    }


class PawnBGSourceFitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_frozen_contract_loads_and_is_hash_pinned(self) -> None:
        loaded = load_source_fit_contract()
        self.assertEqual(loaded["evidence_policy"]["expected_episode_count"], 11)
        self.assertFalse(loaded["evidence_policy"]["held_out_episode_assets_may_be_read"])
        self.assertEqual(
            loaded["bindings"]["wrist_cross_view"]["quantitative_object_or_endpoint_weight"],
            0.0,
        )

    def test_contract_extra_key_and_boolean_type_tamper_fail_closed(self) -> None:
        tampered = copy.deepcopy(self.contract)
        tampered["unexpected"] = True
        with self.assertRaisesRegex(SourceFitError, "keys drifted"):
            validate_source_fit_contract(tampered)

        tampered = copy.deepcopy(self.contract)
        tampered["evidence_policy"]["held_out_episode_assets_may_be_read"] = 0
        with self.assertRaisesRegex(SourceFitError, "drifted"):
            validate_source_fit_contract(tampered)

    def test_contract_wrist_and_variant_tamper_fail_closed(self) -> None:
        tampered = copy.deepcopy(self.contract)
        tampered["bindings"]["wrist_cross_view"]["held_out_membership"] = True
        with self.assertRaisesRegex(SourceFitError, "wrist held-out"):
            validate_source_fit_contract(tampered)

        tampered = copy.deepcopy(self.contract)
        tampered["bindings"]["wrist_cross_view"]["quantitative_object_or_endpoint_weight"] = 0
        with self.assertRaisesRegex(SourceFitError, "quantitative weight"):
            validate_source_fit_contract(tampered)

        tampered = copy.deepcopy(self.contract)
        variants = tampered["selection"]["selected_adapter_final_contact_variants"]
        variants[1], variants[2] = variants[2], variants[1]
        with self.assertRaisesRegex(SourceFitError, "final contact variants"):
            validate_source_fit_contract(tampered)

    def test_phase_extraction_uses_first_post_open_close_and_later_reopen(self) -> None:
        gripper = [1, 3, 8, 20, 30, 26, 16, 8, 4, 3, 4, 5, 10, 22, 28, 25, 10]
        samples = [_sample(value) for value in gripper]
        open_index, source_index, destination_index = extract_phase_indices(
            samples, self.contract
        )
        self.assertEqual(open_index, 4)
        self.assertEqual(source_index, 8)
        self.assertEqual(destination_index, 14)

    def test_phase_extraction_rejects_flat_or_incomplete_gripper_signal(self) -> None:
        with self.assertRaisesRegex(SourceFitError, "no usable open-close"):
            extract_phase_indices([_sample(5.0) for _ in range(12)], self.contract)
        with self.assertRaisesRegex(SourceFitError, "open-close amplitude"):
            extract_phase_indices(
                [_sample(value) for value in [1, 1, 1, 1, 1, 1, 1, 1, 1, 1]],
                self.contract,
            )

    def test_offset_bounds_keep_all_values_inside_unchanged_limits(self) -> None:
        values = np.asarray([
            [-50.0, -100.0, 30.0, -100.0, -160.0],
            [35.0, -15.0, 100.0, -10.0, -55.0],
        ])
        bounds = np.asarray([
            [-1.92, 1.92], [-1.75, 1.75], [-1.69, 1.69],
            [-1.66, 1.66], [-2.74, 2.84], [-0.17, 1.75],
        ])
        signs = (-1, -1, -1, -1, -1)
        lower, upper = _offset_bounds(values, signs, bounds)
        offsets = (lower + upper) / 2.0
        adapter = JointAdapter(
            adapter_id="bounded",
            body_joint_signs=signs,
            body_joint_zero_offsets_rad=tuple(float(value) for value in offsets),
            evidence_class="test_only",
        )
        report = _adapter_limit_report(adapter, values, bounds)
        self.assertTrue(report["all_allowed_training_body_values_within_unchanged_limits"])
        self.assertEqual(report["violating_joint_value_count"], 0)

    def test_no_clipping_candidate_still_requires_frozen_metric_improvement(self) -> None:
        adapter = JointAdapter(
            adapter_id="candidate",
            body_joint_signs=(1, 1, 1, 1, 1),
            body_joint_zero_offsets_rad=(0.0, 0.0, 0.0, 0.0, 0.0),
            evidence_class="test_only",
        )

        def row(reward: float) -> dict[str, object]:
            return {
                "adapter": adapter,
                "kinematic": {"event_rms_distance_m": 0.1},
                "nominal_physics": {"aggregate": {
                    "task_consequence_success_count": 0,
                    "selected_piece_contact_episode_count": 0,
                    "mean_diagnostic_reward": reward,
                    "mean_final_center_distance_m": 0.04445,
                }},
            }

        no_clipping = {
            "all_allowed_training_body_values_within_unchanged_limits": True
        }
        self.assertFalse(_candidate_beats_baseline(row(-0.5), row(0.1), no_clipping))
        self.assertTrue(_candidate_beats_baseline(row(0.2), row(0.1), no_clipping))
        self.assertFalse(_candidate_beats_baseline(
            row(0.2),
            row(0.1),
            {"all_allowed_training_body_values_within_unchanged_limits": False},
        ))


if __name__ == "__main__":
    unittest.main()
