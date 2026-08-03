from __future__ import annotations

import numpy as np

from sim2claw.observable_registration_post_final_shared_shoulder_lift_articulation_calibration import (
    _articulated_trace,
    load_post_final_shared_shoulder_lift_articulation_calibration_contract,
)


def test_or104_contract_freezes_shared_family_split_and_resources() -> None:
    contract = load_post_final_shared_shoulder_lift_articulation_calibration_contract()

    assert contract["split"]["development_positions"] == list(range(1, 8))
    assert contract["split"]["validation_positions"] == list(range(8, 12))
    assert contract["split"]["validation_render_requires_development_gate"] is True
    assert contract["joint_family"]["name"] == "shoulder_lift"
    assert contract["joint_family"]["one_shared_pair_for_both_robots"] is True
    assert contract["joint_family"]["per_episode_or_side_parameters"] is False
    assert contract["candidate_family"]["excursion_gain_candidates"] == [0.8, 0.9, 1.0, 1.1, 1.2]
    assert contract["candidate_family"]["offset_degree_candidates"] == [-10.0, -5.0, 0.0, 5.0, 10.0]
    assert contract["resource_boundary"]["exact_full_mesh_development_candidate_renders_allowed"] == 525
    assert contract["resource_boundary"]["simulator_replays_allowed"] == 0
    assert contract["resource_boundary"]["paid_compute_allowed"] is False
    assert not any(contract["authority"].values())


def test_or104_identity_articulation_is_byte_exact() -> None:
    frame = {
        "p": np.asarray([[0.0, 0.0, 0.0], [0.2, 0.1, 0.3], [0.4, -0.2, 0.5]], dtype=np.float64).reshape(-1).tolist(),
        "q": np.asarray([[1.0, 0.0, 0.0, 0.0]] * 3, dtype=np.float64).reshape(-1).tolist(),
        "t": 0.0,
    }
    trace = {"body_names": ["parent", "joint", "child"], "frames": [frame]}
    result = _articulated_trace(
        trace,
        initial_frame=frame,
        axes={"left": np.asarray([0.0, 1.0, 0.0])},
        sides={"left": {"parent_body_id": 0, "joint_body_id": 1, "subtree_body_ids": [1, 2]}},
        gain=1.0,
        offset_degrees=0.0,
    )

    assert result == trace
