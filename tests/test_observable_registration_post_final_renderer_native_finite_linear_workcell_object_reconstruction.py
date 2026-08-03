import numpy as np

from sim2claw.observable_registration_post_final_renderer_native_finite_linear_workcell_object_reconstruction import (
    _ray_plane_point,
    load_post_final_renderer_native_finite_linear_workcell_object_reconstruction_contract,
)


def test_contract_freezes_real_two_primitive_no_refit_reconstruction() -> None:
    contract = load_post_final_renderer_native_finite_linear_workcell_object_reconstruction_contract()
    assert contract["geometry"]["total_triangle_count"] == 348
    assert contract["geometry"]["shared_scene_zbuffer"] is True
    assert contract["split"]["validation_render_requires_development_gate"] is True
    assert contract["resource_boundary"]["candidate_searches_allowed"] == 0


def test_center_pixel_intersects_frontoparallel_plane() -> None:
    camera = {"position": [0.0, 0.0, 0.0], "target": [0.0, 0.0, 1.0], "fov_degrees": 60.0, "roll_degrees": 0.0}
    point = _ray_plane_point(np.asarray([160.0, 120.0]), camera, 320, 240, np.asarray([0.0, 0.0, 2.0]), np.asarray([0.0, 0.0, 1.0]))
    assert np.allclose(point, [0.0, 0.0, 2.0])
