from __future__ import annotations

import numpy as np

from sim2claw.observable_registration_post_final_shared_robot_base_se2_diagnostic import (
    _robot_registered_trace,
    load_post_final_shared_robot_base_se2_diagnostic_contract,
)


def test_or93_contract_freezes_smallest_post_final_factorization() -> None:
    contract = load_post_final_shared_robot_base_se2_diagnostic_contract()

    assert len(contract["samples"]) == 6
    assert len(contract["robot_registration_family"]["parameter_names"]) == 3
    assert contract["resource_boundary"]["new_physical_video_decodes_allowed"] == 0
    assert contract["resource_boundary"]["analytic_search_candidate_evaluations_allowed"] == 195
    assert contract["claim_limits"]["same_video_semantic_match"] is False
    assert contract["claim_limits"]["untouched_cohort_remaining"] is False


def test_robot_registration_changes_only_declared_robot_bodies() -> None:
    trace = {
        "body_names": ["world", "board", "robot", "static"],
        "frames": [{
            "p": [0.0, 0.0, 0.0, 1.0, 2.0, 0.0, 2.0, 2.0, 0.5, -1.0, 0.0, 0.0],
            "q": [1.0, 0.0, 0.0, 0.0] * 4,
        }],
    }
    transformed = _robot_registered_trace(
        trace,
        anchor_body_id=1,
        robot_body_ids=[2],
        vector=np.asarray([90.0, 0.25, -0.5], dtype=np.float64),
    )
    before = np.asarray(trace["frames"][0]["p"]).reshape((-1, 3))
    after = np.asarray(transformed["frames"][0]["p"]).reshape((-1, 3))

    assert np.array_equal(after[[0, 1, 3]], before[[0, 1, 3]])
    assert np.allclose(after[2], [1.25, 2.5, 0.5])
