"""Prospective chessboard-surface plane admission for synchronized captures."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from .learning_factory_artifacts import sha256_file
from .paths import REPO_ROOT

CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/d405_chessboard_surface_plane_v1.json"
)
CONTRACT_SCHEMA = "sim2claw.d405_chessboard_surface_plane_contract.v1"


class D405ChessboardSurfacePlaneError(RuntimeError):
    """The chessboard-surface admission contract or observation is invalid."""


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != CONTRACT_SCHEMA:
        raise D405ChessboardSurfacePlaneError(
            "unexpected chessboard-surface plane contract"
        )
    if not value.get("authority") or any(value["authority"].values()):
        raise D405ChessboardSurfacePlaneError(
            "chessboard-surface plane authority widened"
        )
    required_positive = (
        "minimum_valid_depth_pixel_count",
        "minimum_absolute_plane_inlier_count",
        "minimum_accepted_frame_count",
    )
    if any(int(value.get(key, 0)) <= 0 for key in required_positive):
        raise D405ChessboardSurfacePlaneError(
            "chessboard-surface minimums must be preregistered and positive"
        )
    return value


def _pair_stable(
    first: dict[str, Any],
    second: dict[str, Any],
    contract: dict[str, Any],
) -> bool:
    first_plane, second_plane = first["plane"], second["plane"]
    first_normal = np.asarray(
        first_plane["normal_camera_unit"], dtype=np.float64
    )
    second_normal = np.asarray(
        second_plane["normal_camera_unit"], dtype=np.float64
    )
    angle = math.degrees(
        math.acos(float(np.clip(first_normal @ second_normal, -1.0, 1.0)))
    )
    offset_drift = abs(
        float(first_plane["plane_equation"]["offset_m"])
        - float(second_plane["plane_equation"]["offset_m"])
    )
    return (
        angle
        <= float(contract["maximum_cross_frame_normal_angle_degrees"])
        and offset_drift
        <= float(contract["maximum_cross_frame_plane_offset_drift_m"])
    )


def _stable_subset(
    candidates: list[dict[str, Any]], contract: dict[str, Any]
) -> list[int]:
    """Return a deterministic pairwise-stable greedy subset."""
    groups: list[list[int]] = []
    for seed in range(len(candidates)):
        group = [seed]
        for index in range(len(candidates)):
            if index != seed and all(
                _pair_stable(candidates[index], candidates[member], contract)
                for member in group
            ):
                group.append(index)
        groups.append(sorted(group))
    return min(groups, key=lambda group: (-len(group), group))


def _stability(planes: list[dict[str, Any]]) -> dict[str, float]:
    angles, offsets = [], []
    for first_index, first in enumerate(planes):
        for second in planes[first_index + 1 :]:
            first_normal = np.asarray(first["normal_camera_unit"])
            second_normal = np.asarray(second["normal_camera_unit"])
            angles.append(
                math.degrees(
                    math.acos(
                        float(
                            np.clip(first_normal @ second_normal, -1.0, 1.0)
                        )
                    )
                )
            )
            offsets.append(
                abs(
                    float(first["plane_equation"]["offset_m"])
                    - float(second["plane_equation"]["offset_m"])
                )
            )
    return {
        "maximum_pairwise_normal_angle_degrees": max(angles, default=0.0),
        "maximum_pairwise_plane_offset_drift_m": max(offsets, default=0.0),
    }


def admit_chessboard_surface_planes(
    observations: list[dict[str, Any]],
    *,
    contract_path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    """Filter transient frames and evaluate the frozen accepted-frame minimum."""
    contract = load_contract(contract_path)
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for source_index, observation in enumerate(copy.deepcopy(observations)):
        plane = observation.get("plane")
        if not isinstance(plane, dict):
            raise D405ChessboardSurfacePlaneError(
                f"observation {source_index} has no plane fit"
            )
        residuals = plane.get("residuals_m", {})
        distance = plane.get(
            "camera_optical_origin_perpendicular_distance_m"
        )
        failures = []
        checks = {
            "valid_depth_pixel_count": int(plane.get("valid_pixel_count", 0))
            >= int(contract["minimum_valid_depth_pixel_count"]),
            "absolute_plane_inlier_count": int(
                plane.get("plane_inlier_count", 0)
            )
            >= int(contract["minimum_absolute_plane_inlier_count"]),
            "plane_rms_residual": float(residuals.get("rms", math.inf))
            <= float(contract["maximum_plane_rms_residual_m"]),
            "plane_p95_residual": float(
                residuals.get("p95_absolute", math.inf)
            )
            <= float(contract["maximum_plane_p95_absolute_residual_m"]),
            "camera_origin_plane_distance": isinstance(
                distance, (float, int)
            )
            and float(contract["camera_origin_plane_distance_range_m"][0])
            <= float(distance)
            <= float(contract["camera_origin_plane_distance_range_m"][1]),
        }
        failures.extend(key for key, passed in checks.items() if not passed)
        observation["source_frame_index"] = source_index
        observation["individual_admission_checks"] = checks
        if failures:
            observation["rejection_reasons"] = failures
            rejected.append(observation)
        else:
            candidates.append(observation)

    stable_indexes = set(_stable_subset(candidates, contract)) if candidates else set()
    accepted = []
    for index, observation in enumerate(candidates):
        if index in stable_indexes:
            observation["admitted"] = True
            accepted.append(observation)
        else:
            observation["admitted"] = False
            observation["rejection_reasons"] = [
                "cross_frame_stability_outlier"
            ]
            rejected.append(observation)
    accepted.sort(key=lambda item: item["source_frame_index"])
    rejected.sort(key=lambda item: item["source_frame_index"])
    stability = _stability([item["plane"] for item in accepted])
    count_passed = len(accepted) >= int(
        contract["minimum_accepted_frame_count"]
    )
    return {
        "contract": {
            "path": str(contract_path.resolve()),
            "sha256": sha256_file(contract_path),
            "schema_version": contract["schema_version"],
        },
        "surface_semantics": contract["surface_semantics"],
        "input_frame_count": len(observations),
        "accepted_frame_count": len(accepted),
        "rejected_frame_count": len(rejected),
        "minimum_accepted_frame_count": int(
            contract["minimum_accepted_frame_count"]
        ),
        "accepted_observations": accepted,
        "rejected_observations": rejected,
        "cross_frame_stability": stability,
        "checks": {
            "minimum_accepted_frame_count": count_passed,
            "accepted_pairwise_normal_stability": stability[
                "maximum_pairwise_normal_angle_degrees"
            ]
            <= float(contract["maximum_cross_frame_normal_angle_degrees"]),
            "accepted_pairwise_offset_stability": stability[
                "maximum_pairwise_plane_offset_drift_m"
            ]
            <= float(contract["maximum_cross_frame_plane_offset_drift_m"]),
        },
        "passed": count_passed,
        "authority": contract["authority"],
    }
