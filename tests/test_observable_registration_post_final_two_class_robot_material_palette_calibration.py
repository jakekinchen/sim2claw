from __future__ import annotations

from sim2claw.observable_registration_post_final_two_class_robot_material_palette_calibration import (
    _material_scene,
    load_post_final_two_class_robot_material_palette_calibration_contract,
)


def test_or106_contract_freezes_two_class_shared_palette_and_split() -> None:
    contract = load_post_final_two_class_robot_material_palette_calibration_contract()

    assert contract["split"]["development_positions"] == list(range(1, 8))
    assert contract["split"]["validation_positions"] == list(range(8, 12))
    assert contract["split"]["validation_render_requires_development_gate"] is True
    assert contract["candidate_family"]["structural_grayscale_albedo_candidates"] == [0.5, 0.7, 0.85, 1.0]
    assert contract["candidate_family"]["servo_grayscale_albedo_candidates"] == [0.05, 0.15, 0.3, 0.5]
    assert contract["candidate_family"]["identity_pair"] == [0.5, 0.5]
    assert contract["candidate_family"]["one_shared_pair_for_both_robots_all_frames_and_episodes"] is True
    assert contract["candidate_family"]["per_frame_side_episode_or_mesh_values"] is False
    assert contract["resource_boundary"]["exact_full_mesh_development_candidate_renders_allowed"] == 336
    assert contract["resource_boundary"]["simulator_replays_allowed"] == 0
    assert contract["resource_boundary"]["paid_compute_allowed"] is False
    assert not any(contract["authority"].values())


def test_or106_material_scene_preserves_identity_and_splits_classes() -> None:
    scene = {
        "meshes": [{"id": 1, "name": "left_structure"}, {"id": 2, "name": "right_servo"}],
        "geoms": [
            {"id": 1, "body_id": 29, "type": "mesh", "mesh_id": 1, "rgba": [0.5, 0.5, 0.5, 1.0]},
            {"id": 2, "body_id": 37, "type": "mesh", "mesh_id": 2, "rgba": [0.5, 0.5, 0.5, 1.0]},
            {"id": 3, "body_id": 5, "type": "box", "mesh_id": None, "rgba": [0.2, 0.3, 0.4, 1.0]},
        ],
    }
    classes = {"structural": {"structure"}, "servo": {"servo"}}

    assert _material_scene(scene, classes, 0.5, 0.5) == scene
    candidate = _material_scene(scene, classes, 0.9, 0.1)
    assert candidate["geoms"][0]["rgba"] == [0.9, 0.9, 0.9, 1.0]
    assert candidate["geoms"][1]["rgba"] == [0.1, 0.1, 0.1, 1.0]
    assert candidate["geoms"][2] == scene["geoms"][2]
