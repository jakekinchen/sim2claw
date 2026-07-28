from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from tools.build_current_pi_tag3_hand_eye_base_anchor import (
    HandEyeAnchorError,
    apply_single_axis_gauge,
    select_diverse_grid_seeds,
    validate_spec,
)
from tools.evaluate_current_pi_cad_keyed_joint_mapping import canonical_sha256
from tools.fit_pi_dual_link_tag_bundle import transform


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = (
    ROOT
    / "configs/evaluations/current_pi_tag3_hand_eye_base_anchor_v1.json"
)


def _spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def test_spec_freezes_tag3_single_axis_fit_and_denies_hardware() -> None:
    spec = _spec()
    validate_spec(spec)
    algorithm = spec["hand_eye_algorithm"]
    assert canonical_sha256(algorithm) == spec[
        "hand_eye_algorithm_sha256"
    ]
    assert spec["fit_poses"] == ["J", "S", "K", "L"]
    assert algorithm["tag_fit"]["expected_identifiable_rank"] == 10
    assert algorithm["tag_fit"]["expected_gauge_nullity"] == 2
    assert spec["authority"]["hardware_motion"] is False


def test_spec_rejects_algorithm_tamper_and_heldout_reference() -> None:
    tampered = copy.deepcopy(_spec())
    tampered["hand_eye_algorithm"]["tag_id"] = 2
    with pytest.raises(HandEyeAnchorError, match="hash changed"):
        validate_spec(tampered)

    heldout = copy.deepcopy(_spec())
    heldout["extra"] = "runs/camera/pose-m-fresh/image.jpg"
    with pytest.raises(HandEyeAnchorError, match="held-out"):
        validate_spec(heldout)


def test_exact_single_axis_gauge_preserves_hand_eye_products() -> None:
    camera = transform(
        np.asarray([0.2, -0.3, 0.1]),
        np.asarray([0.4, 0.7, 0.9]),
    )
    mount = transform(
        np.asarray([-0.1, 0.4, 0.2]),
        np.asarray([0.03, -0.02, 0.05]),
    )
    world_axis = np.eye(4)
    world_axis[:3, 3] = [0.1, 0.8, 0.6]
    axis_body = transform(
        np.asarray([0.1, 0.2, -0.1]),
        np.asarray([0.02, 0.03, 0.04]),
    )
    for gauge in (
        np.asarray([0.8, 0.1]),
        np.asarray([-0.7, -0.2]),
    ):
        changed_camera, changed_mount = apply_single_axis_gauge(
            camera, mount, world_axis, axis_body, gauge
        )
        for angle in (-0.4, 0.0, 0.6):
            revolution = np.eye(4)
            revolution[:3, :3] = Rotation.from_rotvec(
                [0.0, 0.0, angle]
            ).as_matrix()
            body = world_axis @ revolution @ axis_body
            assert np.allclose(
                changed_camera @ body @ changed_mount,
                camera @ body @ mount,
                atol=1e-12,
            )


def test_grid_seed_selection_is_cost_ordered_and_cyclically_diverse() -> None:
    rows = [
        (1.0, -math.pi, -0.3),
        (1.1, math.pi, -0.3),
        (1.2, -2.0, -0.3),
        (1.3, -2.0, -0.1),
        (1.4, 0.0, 0.0),
    ]
    selected = select_diverse_grid_seeds(
        rows,
        count=3,
        minimum_rotation_separation=0.45,
        minimum_translation_separation=0.08,
    )
    assert selected == [
        [-math.pi, -0.3],
        [-2.0, -0.3],
        [-2.0, -0.1],
    ]
