import json

import numpy as np

from sim2claw.observable_registration_board_grid_camera_sensor_roll_successor import _project_triangles_roll
from sim2claw.observable_registration_post_final_renderer_native_single_capsule_operator_reconstruction import (
    DEFAULT_CONTRACT,
    _actor_triangle_stream,
    load_post_final_renderer_native_single_capsule_operator_reconstruction_contract,
)


def test_contract_preserves_renderer_native_and_claim_boundaries() -> None:
    contract = load_post_final_renderer_native_single_capsule_operator_reconstruction_contract()
    assert contract["actor_geometry"]["shared_scene_zbuffer"] is True
    assert contract["actor_geometry"]["camera_facing_billboard_or_2d_overlay"] is False
    assert contract["resource_boundary"]["physical_pixel_copy_warp_blend_composite_or_texture_projection_allowed"] == 0
    assert contract["claim_limits"]["predictive_simulation"] is False
    assert contract["claim_limits"]["physics_fidelity"] is False


def test_actor_is_real_248_triangle_geometry_with_exact_pose_reprojection() -> None:
    contract = json.loads(DEFAULT_CONTRACT.read_text())
    camera = json.loads((DEFAULT_CONTRACT.parents[2] / contract["sources"]["or95_contract"]["path"]).read_text())["frozen_candidate"]["camera"]
    body_count = 45
    positions = np.zeros((body_count, 3), dtype=np.float64)
    position, right, up, forward = __import__(
        "sim2claw.observable_registration_board_grid_camera_sensor_roll_successor",
        fromlist=["_rolled_basis"],
    )._rolled_basis(camera)
    positions[34] = position + forward * 1.0 + right * 0.15
    positions[42] = position + forward * 1.0 - right * 0.15
    trace = {"body_names": [str(index) for index in range(body_count)], "frames": [{"p": positions.reshape(-1).tolist()}]}
    shape = {"endpoint0_px": [180.0, 100.0], "endpoint1_px": [230.0, 115.0], "radius_px": 12}
    pixels, depths, colors, metadata = _actor_triangle_stream(
        shape,
        trace,
        camera,
        contract["renderer"],
        np.asarray([80, 110, 160], dtype=np.uint8),
        contract["backprojection"],
    )
    assert pixels.shape == (248, 3, 2)
    assert depths.shape == (248, 3)
    assert colors.shape == (248, 3)
    assert np.all(depths > 0.0)
    assert metadata["triangle_count"] == 248
    assert metadata["endpoint_reprojection_error_px"] < 1e-9
    assert metadata["radius_reprojection_error_px"] < 1e-9
