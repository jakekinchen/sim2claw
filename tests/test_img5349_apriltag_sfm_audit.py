from __future__ import annotations

import numpy as np
import pytest

from tools.audit_img5349_apriltag_sfm import (
    Camera,
    RegisteredImage,
    project,
    quaternion_to_rotation,
    triangulate_tag,
)


def _image(name: str, center: tuple[float, float, float]) -> RegisteredImage:
    camera_center = np.asarray(center, dtype=np.float64)
    return RegisteredImage(
        image_id=int(name.removeprefix("frame-").removesuffix(".jpg")),
        camera_id=1,
        name=name,
        rotation_world_to_camera=np.eye(3),
        translation_world_to_camera=-camera_center,
    )


def test_quaternion_and_multiview_tag_triangulation() -> None:
    assert quaternion_to_rotation((1.0, 0.0, 0.0, 0.0)) == pytest.approx(
        np.eye(3)
    )
    camera = Camera(
        camera_id=1,
        model_id=4,
        width=1600,
        height=1200,
        parameters=np.asarray(
            (1000.0, 1000.0, 800.0, 600.0, 0.0, 0.0, 0.0, 0.0)
        ),
    )
    corners = np.asarray(
        (
            (-0.1, 0.1, 3.0),
            (0.1, 0.1, 3.0),
            (0.1, -0.1, 3.0),
            (-0.1, -0.1, 3.0),
        )
    )
    images = [
        _image("frame-000001.jpg", (-0.5, 0.0, 0.0)),
        _image("frame-000002.jpg", (0.5, 0.0, 0.0)),
        _image("frame-000003.jpg", (0.0, -0.5, 0.0)),
    ]
    observations = []
    for image in images:
        pixels = np.stack([project(corner, image, camera)[0] for corner in corners])
        observations.append((image, pixels))

    result = triangulate_tag(observations, camera)

    assert result["accepted"] is True
    assert result["corners_sfm"] == pytest.approx(corners)
    assert result["metrics"]["corner_reprojection_rms_px"] < 1e-10
    assert result["metrics"]["minimum_depth_sfm"] == pytest.approx(3.0)
    assert result["metrics"]["maximum_pair_parallax_deg"] > 10.0


def test_two_views_do_not_pass_strict_tag_gate() -> None:
    camera = Camera(
        camera_id=1,
        model_id=4,
        width=1600,
        height=1200,
        parameters=np.asarray(
            (1000.0, 1000.0, 800.0, 600.0, 0.0, 0.0, 0.0, 0.0)
        ),
    )
    corners = np.asarray(
        (
            (-0.1, 0.1, 3.0),
            (0.1, 0.1, 3.0),
            (0.1, -0.1, 3.0),
            (-0.1, -0.1, 3.0),
        )
    )
    images = [
        _image("frame-000001.jpg", (-0.5, 0.0, 0.0)),
        _image("frame-000002.jpg", (0.5, 0.0, 0.0)),
    ]
    observations = [
        (
            image,
            np.stack([project(corner, image, camera)[0] for corner in corners]),
        )
        for image in images
    ]

    result = triangulate_tag(observations, camera)

    assert result["accepted"] is False
    assert result["gates"]["at_least_three_views"] is False
