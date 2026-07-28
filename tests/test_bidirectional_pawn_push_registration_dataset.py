import hashlib
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "bidirectional_pawn_push_registration_dataset_v1.json"
)


def test_registration_dataset_split_is_frozen_and_hash_bound() -> None:
    payload = json.loads(MANIFEST.read_bytes())
    assert (
        payload["schema_version"]
        == "sim2claw.bidirectional_pawn_push_registration_dataset.v1"
    )
    assert payload["authority"] == {
        "physical_motion": False,
        "training": False,
        "promotion": False,
    }
    rules = payload["split_rules"]
    assert rules["held_out_content_inspected_during_q01"] is False
    assert rules["held_out_open_count_allowed_after_candidate_freeze"] == 1
    assert rules["maximum_fit_residual_mm"] == 25.0
    assert rules["maximum_held_out_residual_mm"] == 25.0

    inputs = payload["inputs"]
    assert len(inputs) == len({entry["id"] for entry in inputs})
    assert {entry["split"] for entry in inputs} == {"fit", "held_out"}
    assert sum(entry["split"] == "held_out" for entry in inputs) >= 4

    for entry in inputs:
        path = REPO_ROOT / entry["path"]
        assert path.is_file(), entry["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]


def test_q02_candidate_family_is_bounded_before_heldout_open() -> None:
    payload = json.loads(MANIFEST.read_bytes())
    family = payload["candidate_family_constraints_for_q02"]
    assert family["categorical_family"] == "eight square-board D4 orientations"
    assert family["continuous_parameters"] == [
        "board_center_x_m",
        "board_center_y_m",
        "board_yaw_degrees",
    ]
    assert family["board_center_delta_bound_m"] == 0.08
    assert family["board_yaw_delta_bound_degrees"] == 15.0
    assert family["action_mutation_allowed"] is False
