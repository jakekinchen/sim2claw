from __future__ import annotations

from copy import deepcopy

from sim2claw.d405_chessboard_surface_plane import (
    admit_chessboard_surface_planes,
    load_contract,
)


def _observation(
    index: int,
    *,
    normal: list[float] = [0.0, 0.0, 1.0],
    offset_m: float = -0.12,
    inliers: int = 18000,
    rms: float = 0.0002,
) -> dict:
    return {
        "bag_timestamp_ns": index * 1_000_000,
        "plane": {
            "valid_pixel_count": 100000,
            "plane_inlier_count": inliers,
            "normal_camera_unit": normal,
            "plane_equation": {"offset_m": offset_m},
            "camera_optical_origin_perpendicular_distance_m": abs(offset_m),
            "residuals_m": {"rms": rms, "p95_absolute": rms * 1.5},
        },
    }


def test_contract_uses_absolute_support_and_keeps_authority_false() -> None:
    contract = load_contract()

    assert contract["minimum_absolute_plane_inlier_count"] == 12000
    assert "minimum_plane_inlier_fraction_of_valid" not in contract
    assert contract["minimum_accepted_frame_count"] == 3
    assert all(value is False for value in contract["authority"].values())


def test_transient_frames_are_recorded_and_filtered() -> None:
    frames = [_observation(index) for index in range(4)]
    frames.append(
        _observation(4, normal=[0.1, 0.0, 0.994987437], offset_m=-0.14)
    )
    result = admit_chessboard_surface_planes(frames)

    assert result["passed"] is True
    assert result["accepted_frame_count"] == 4
    assert [item["source_frame_index"] for item in result["rejected_observations"]] == [
        4
    ]
    assert result["rejected_observations"][0]["rejection_reasons"] == [
        "cross_frame_stability_outlier"
    ]


def test_below_preregistered_accepted_count_returns_rejected_result() -> None:
    frames = [_observation(index) for index in range(3)]
    frames[1]["plane"]["plane_inlier_count"] = 2000
    frames[2]["plane"]["residuals_m"]["rms"] = 0.01
    original = deepcopy(frames)

    result = admit_chessboard_surface_planes(frames)

    assert result["passed"] is False
    assert result["accepted_frame_count"] == 1
    assert result["checks"]["minimum_accepted_frame_count"] is False
    assert result["rejected_frame_count"] == 2
    assert frames == original
