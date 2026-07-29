from __future__ import annotations

import json
from pathlib import Path

from sim2claw.parking_target_certificate import _materialize_angle_contract


ROOT = Path(__file__).resolve().parents[1]


def test_parking_target_contract_is_prospective_and_motion_free() -> None:
    contract = json.loads(
        (
            ROOT
            / "configs/evaluations/parking_target_certificate_v1.json"
        ).read_text(encoding="utf-8")
    )
    assert contract["lock_angle_grid_degrees"] == [
        97.0,
        95.0,
        93.0,
        91.0,
        90.0,
        88.0,
    ]
    assert contract["selection"] == {
        "minimum_distinct_families_per_direction": 1,
        "maximum_viable_lock_angle_is_threshold": True,
        "recommended_target_requires_at_least_2deg_lower_passing_angle": True,
        "dynamic_outcome_used": False,
        "physical_outcome_used": False,
        "grid_expansion_after_run": False,
    }
    assert contract["authority"]["static_simulation"] is True
    assert contract["authority"]["physical_motion"] is False
    assert contract["authority"]["physical_task_attempt"] is False
    assert contract["authority"]["transfer_claim"] is False


def test_materialized_angle_changes_only_elbow_seed_and_identity() -> None:
    template = json.loads(
        (
            ROOT
            / "configs/evaluations/directional_displacement_static_v1.json"
        ).read_text(encoding="utf-8")
    )
    output = (
        ROOT
        / "runs/bidirectional-pawn-push-v2/test-parking/elbow_93p0_degrees"
    )
    materialized = _materialize_angle_contract(
        template,
        angle_degrees=93.0,
        output_directory=output,
    )
    original_seed = template["live_seed"]["follower_position_degrees"]
    derived_seed = materialized["live_seed"]["follower_position_degrees"]
    assert derived_seed[:2] == original_seed[:2]
    assert derived_seed[2] == 93.0
    assert derived_seed[3:] == original_seed[3:]
    assert materialized["live_seed"]["locked_value_degrees"] == 93.0
    assert materialized["unchanged_from_base"] == template[
        "unchanged_from_base"
    ]
    assert materialized["authority"] == template["authority"]
    assert materialized["output_directory"].endswith(
        "test-parking/elbow_93p0_degrees"
    )
