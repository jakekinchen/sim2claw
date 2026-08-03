from __future__ import annotations

import numpy as np

from sim2claw.observable_registration_post_final_independent_left_right_robot_base_se2_diagnostic import (
    _independently_registered_trace,
    load_post_final_independent_left_right_robot_base_se2_diagnostic_contract,
)


def test_or94_contract_freezes_independent_exact_mesh_search() -> None:
    contract = load_post_final_independent_left_right_robot_base_se2_diagnostic_contract()

    assert len(contract["robot_registration_family"]["parameter_names"]) == 6
    assert contract["search"]["renderer"].startswith("exact_source_meshes")
    assert contract["resource_boundary"]["analytic_or_bounds_proxy_renders_allowed"] == 0
    assert contract["resource_boundary"]["new_physical_video_decodes_allowed"] == 0
    assert contract["claim_limits"]["same_video_semantic_match"] is False


def test_independent_registration_keeps_groups_separate() -> None:
    trace = {
        "body_names": ["world", "board", "left", "right", "static"],
        "frames": [{
            "p": [0.0, 0.0, 0.0, 1.0, 2.0, 0.0, 2.0, 2.0, 0.5, 0.0, 2.0, 0.5, -1.0, 0.0, 0.0],
            "q": [1.0, 0.0, 0.0, 0.0] * 5,
        }],
    }
    transformed = _independently_registered_trace(
        trace,
        anchor_body_id=1,
        left_body_ids=[2],
        right_body_ids=[3],
        vector=np.asarray([90.0, 0.25, -0.5, -90.0, -0.25, 0.5]),
    )
    before = np.asarray(trace["frames"][0]["p"]).reshape((-1, 3))
    after = np.asarray(transformed["frames"][0]["p"]).reshape((-1, 3))

    assert np.array_equal(after[[0, 1, 4]], before[[0, 1, 4]])
    assert np.allclose(after[2], [1.25, 2.5, 0.5])
    assert np.allclose(after[3], [0.75, 3.5, 0.5])
