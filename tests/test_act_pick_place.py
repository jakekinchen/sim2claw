from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

import numpy as np

from sim2claw.act_pick_place import (
    REQUIRED_LINEAGE_FIELDS,
    encode_observation,
    load_act_pick_place_task_contract,
    resolve_structured_goal,
    task_contract_sha256,
    validate_candidate_lineage,
    validate_candidate_outcome,
    validate_task_contract,
)
from sim2claw.paths import REPO_ROOT


FROZEN_PREDECESSOR_HASHES = {
    "chess_rook_lift_v1.json": "cbd590e144b5b2a7d3c2a520ed76334bc0696b6e25003290e90a7064aca21587",
    "chess_pick_place_groot_v1.json": "988a5a93d26358770c2dc3731602ba1dc11f723974758659d4cb05392f63ef58",
}


def _feature_values(contract: dict[str, object]) -> dict[str, list[float]]:
    values: dict[str, list[float]] = {}
    for feature in contract["observation"]["features"]:  # type: ignore[index]
        dimension = int(feature["dimension"])
        values[str(feature["name"])] = [0.0] * dimension
    for name in (
        "end_effector_pose",
        "selected_piece_pose",
        "continuous_target_pose",
        "end_effector_in_piece_frame",
        "piece_in_target_frame",
    ):
        values[name][3] = 1.0
    values["object_descriptor"][0] = 1.0
    values["object_descriptor"][4:] = [0.02, 0.02, 0.05]
    values["observable_skill_id"][0] = 1.0
    return values


class GoalConditionedActContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = load_act_pick_place_task_contract()

    def test_contract_round_trip_and_frozen_dimensions(self) -> None:
        encoded = json.dumps(self.contract, sort_keys=True, separators=(",", ":"))
        decoded = json.loads(encoded)
        self.assertEqual(validate_task_contract(decoded), self.contract)
        self.assertEqual(self.contract["observation"]["dimension"], 61)
        self.assertEqual(self.contract["action"]["dimension"], 6)
        self.assertEqual(len(task_contract_sha256()), 64)

    def test_frozen_predecessor_contracts_are_byte_identical(self) -> None:
        task_root = REPO_ROOT / "configs" / "tasks"
        for name, expected in FROZEN_PREDECESSOR_HASHES.items():
            actual = hashlib.sha256((task_root / name).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, name)

    def test_same_schema_encodes_two_continuous_destinations(self) -> None:
        first = resolve_structured_goal("brown_pawn_a2", "c3")
        second = resolve_structured_goal("brown_pawn_a2", "d4")
        self.assertNotEqual(first["target_pose"][:3], second["target_pose"][:3])
        self.assertEqual(first["target_pose_frame"], "world")
        values = _feature_values(self.contract)
        values["continuous_target_pose"] = first["target_pose"]
        first_vector = encode_observation(self.contract, values)
        values["continuous_target_pose"] = second["target_pose"]
        second_vector = encode_observation(self.contract, values)
        self.assertEqual(first_vector.shape, (61,))
        self.assertEqual(second_vector.shape, (61,))
        self.assertFalse(np.array_equal(first_vector, second_vector))

    def test_timing_and_square_class_leakage_is_rejected(self) -> None:
        for forbidden in ("episode_progress", "timed_phase_progress", "destination_square_one_hot"):
            values = _feature_values(self.contract)
            values[forbidden] = [0.5]
            with self.assertRaisesRegex(ValueError, "prohibited leakage"):
                encode_observation(self.contract, values)

    def test_missing_observable_and_invalid_frame_are_rejected(self) -> None:
        values = _feature_values(self.contract)
        del values["selected_piece_pose"]
        with self.assertRaisesRegex(ValueError, "missing observable"):
            encode_observation(self.contract, values)
        changed = copy.deepcopy(self.contract)
        changed["observation"]["features"][0]["frame"] = "future_world"
        with self.assertRaisesRegex(ValueError, "undeclared coordinate frame"):
            validate_task_contract(changed)

    def test_split_leakage_is_rejected(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["splits"]["held_out_seeds"][0] = changed["splits"]["training_seeds"][0]
        with self.assertRaisesRegex(ValueError, "seeds overlap"):
            validate_task_contract(changed)
        changed = copy.deepcopy(self.contract)
        changed["splits"]["held_out_training_rows"] = 1
        with self.assertRaisesRegex(ValueError, "zero training rows"):
            validate_task_contract(changed)

    def test_lineage_is_complete_before_candidate_admission(self) -> None:
        lineage = {field: None for field in REQUIRED_LINEAGE_FIELDS}
        lineage["source_episode_id"] = "source-001"
        validate_candidate_lineage(self.contract, lineage)
        del lineage["ik_solver_id"]
        with self.assertRaisesRegex(ValueError, "ik_solver_id"):
            validate_candidate_lineage(self.contract, lineage)

    def test_each_frozen_negative_fixture_fails_closed(self) -> None:
        for rejection in self.contract["negative_fixture_rejections"]:
            with self.subTest(rejection=rejection):
                with self.assertRaisesRegex(ValueError, rejection):
                    validate_candidate_outcome(
                        self.contract,
                        {
                            "strict_success": False,
                            "rejection_reason": rejection,
                            "assistance": rejection == "assistance",
                            "action_owner": "model_or_declared_source_expert",
                        },
                    )

    def test_strict_success_requires_declared_owner_and_no_assistance(self) -> None:
        validate_candidate_outcome(
            self.contract,
            {
                "strict_success": True,
                "rejection_reason": None,
                "assistance": False,
                "action_owner": "model_or_declared_source_expert",
            },
        )
        for mutation, message in (
            ({"assistance": True}, "assisted"),
            ({"action_owner": "unknown"}, "ownership"),
            ({"strict_success": False}, "did not pass"),
        ):
            outcome = {
                "strict_success": True,
                "rejection_reason": None,
                "assistance": False,
                "action_owner": "model_or_declared_source_expert",
            }
            outcome.update(mutation)
            with self.assertRaisesRegex(ValueError, message):
                validate_candidate_outcome(self.contract, outcome)


if __name__ == "__main__":
    unittest.main()
