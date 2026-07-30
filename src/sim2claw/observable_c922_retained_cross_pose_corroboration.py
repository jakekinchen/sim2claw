"""Final zero-new-data C922 focal-family corroboration across workspaces."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .observable_c922_pixel_lattice_refinement import (
    fit_camera_family,
)
from .paths import REPO_ROOT


SCHEMA = (
    "sim2claw.observable_c922_retained_cross_pose_corroboration_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_c922_retained_cross_pose_corroboration_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_c922_retained_cross_pose_corroboration_v1.json"
)
OUTPUT_PATH = (
    REPO_ROOT
    / "outputs"
    / "observable_c922_retained_cross_pose_corroboration_v1"
    / "receipt.json"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _bound_path(
    binding: dict[str, Any], *, root: Path, label: str
) -> Path:
    path = root / str(binding.get("path", ""))
    expected = str(binding.get("sha256", ""))
    _require(path.is_file(), f"{label} source is missing")
    _require(
        len(expected) == 64 and sha256_file(path) == expected,
        f"{label} hash drifted",
    )
    return path


def _bound_json(
    binding: dict[str, Any], *, root: Path, label: str
) -> dict[str, Any]:
    return load_json_object(
        _bound_path(binding, root=root, label=label),
        label=label,
    )


def _episode_map(split: dict[str, Any]) -> dict[str, dict[str, Any]]:
    episodes = split.get("episodes")
    _require(isinstance(episodes, list) and episodes, "historical split is empty")
    result: dict[str, dict[str, Any]] = {}
    for episode in episodes:
        _require(isinstance(episode, dict), "historical split row is invalid")
        episode_id = str(episode.get("episode_id", ""))
        _require(episode_id and episode_id not in result, "episode IDs changed")
        result[episode_id] = episode
    return result


def load_cross_pose_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="C922 cross-pose contract")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    _require(contract.get("card_id") == "OR10B", "card identity changed")
    _require(contract.get("one_run_only") is True, "one-run gate changed")
    _require(
        contract.get("evidence_role")
        == "retrospective_retained_cross_pose_intrinsics_corroboration_diagnostic",
        "evidence role changed",
    )
    sources = contract.get("sources")
    _require(isinstance(sources, dict) and sources, "sources are missing")
    for source_id, binding in sources.items():
        _require(isinstance(binding, dict), f"invalid source: {source_id}")
        _bound_path(binding, root=root, label=source_id)

    split = _bound_json(
        sources["historical_sysid_split"],
        root=root,
        label="historical sysid split",
    )
    _require(split.get("frozen") is True, "historical split is not frozen")
    episodes = _episode_map(split)
    selection = contract.get("historical_episode_selection")
    _require(isinstance(selection, dict), "episode selection is missing")
    included = [str(item) for item in selection.get("included_episode_ids", [])]
    _require(len(included) == 14 and len(set(included)) == 14, "input set changed")
    quarantine = str(
        selection.get("quarantined_advisory_inspection", {}).get(
            "episode_id", ""
        )
    )
    train_ids = {
        episode_id
        for episode_id, episode in episodes.items()
        if episode.get("split") == "train"
    }
    _require(
        set(included) == train_ids - {quarantine},
        "included inputs no longer equal train minus quarantine",
    )
    _require(quarantine in train_ids, "quarantine is not a training episode")
    held_out_ids = {
        episode_id
        for episode_id, episode in episodes.items()
        if episode.get("split") == "held_out"
    }
    _require(
        set(selection.get("preserved_historical_held_out_episode_ids", []))
        == held_out_ids
        and len(held_out_ids) == 3
        and selection.get("held_out_pixels_may_be_opened") is False,
        "historical held-out boundary changed",
    )
    _require(
        selection.get("task_outcomes_may_be_used") is False,
        "task outcome boundary changed",
    )

    identity = contract.get("camera_identity_contract")
    _require(isinstance(identity, dict), "camera identity contract is missing")
    _require(
        identity.get("historical_workspace") == "hackathon_era_workspace"
        and identity.get("current_or10_workspace")
        == "post_hackathon_home_workspace"
        and identity.get("workspace_and_mount_match") is False
        and identity.get("camera_angle_match") is False
        and identity.get("historical_unique_id_present") is False
        and identity.get("same_physical_device_claimed") is False,
        "cross-workspace proof boundary changed",
    )

    seed = _bound_json(
        sources["historical_board_seed"],
        root=root,
        label="historical board seed",
    )
    seed_contract = contract.get("board_seed")
    _require(isinstance(seed_contract, dict), "board seed contract is missing")
    _require(
        seed["source_proposal"]["calibration_id"]
        == seed_contract["calibration_id"]
        and seed["source_proposal"]["homography_sha256"]
        == seed_contract["pixel_to_board_homography_sha256"]
        and seed_contract.get("use")
        == "search_initialization_only_not_an_observation"
        and seed_contract.get("metric_pose_authority") is False,
        "historical board seed authority changed",
    )

    extraction = contract.get("pixel_extraction")
    _require(isinstance(extraction, dict), "pixel extraction is missing")
    _require(
        extraction.get("interior_indices")
        == [[i, j] for j in range(1, 8) for i in range(1, 8)],
        "interior lattice changed",
    )
    _require(
        extraction.get("manual_mask_iteration_after_run_allowed") is False,
        "manual mask iteration was enabled",
    )
    sampling = contract.get("frame_sampling")
    _require(isinstance(sampling, dict), "frame sampling is missing")
    _require(
        sampling.get("frames_per_episode") == 12
        and sampling.get("start_seconds") == 1.0
        and sampling.get("end_inclusive") is False
        and sampling.get("apply_receipt_rotation_before_extraction") is False
        and sampling.get("post_action_frames_allowed") is False,
        "frame sampling changed",
    )
    boundaries = contract.get("proof_boundaries")
    authority = contract.get("authority")
    _require(
        isinstance(boundaries, dict)
        and boundaries
        and not any(boundaries.values()),
        "proof boundary widened",
    )
    _require(
        isinstance(authority, dict) and authority and not any(authority.values()),
        "authority widened",
    )
    return contract


def deterministic_sample_indices(
    *,
    fps: float,
    action_start_seconds: float,
    start_seconds: float,
    count: int,
) -> tuple[np.ndarray, np.ndarray]:
    _require(math.isfinite(fps) and fps > 0.0, "decoded fps is invalid")
    _require(
        math.isfinite(action_start_seconds)
        and action_start_seconds > start_seconds,
        "pre-action interval is invalid",
    )
    _require(count > 0, "sample count is invalid")
    times = np.linspace(
        float(start_seconds),
        float(action_start_seconds),
        int(count) + 1,
        endpoint=True,
        dtype=np.float64,
    )[:-1]
    indices = np.floor(times * float(fps)).astype(np.int64)
    _require(
        len(np.unique(indices)) == count,
        "sample rule produced duplicate frame indices",
    )
    _require(
        bool(np.all(indices.astype(np.float64) / fps < action_start_seconds)),
        "sample rule crossed action start",
    )
    return times, indices


def _historical_episode_bindings(
    contract: dict[str, Any], *, root: Path
) -> list[dict[str, Any]]:
    split = _bound_json(
        contract["sources"]["historical_sysid_split"],
        root=root,
        label="historical sysid split",
    )
    episode_map = _episode_map(split)
    identity = contract["camera_identity_contract"]
    bindings: list[dict[str, Any]] = []
    for episode_id in contract["historical_episode_selection"][
        "included_episode_ids"
    ]:
        episode = episode_map[str(episode_id)]
        _require(episode.get("split") == "train", "non-train episode selected")
        receipt_path = root / str(episode.get("source_receipt_path", ""))
        _require(receipt_path.is_file(), f"{episode_id} receipt is missing")
        _require(
            sha256_file(receipt_path)
            == str(episode.get("source_receipt_sha256", "")),
            f"{episode_id} receipt hash drifted",
        )
        receipt = load_json_object(receipt_path, label=f"{episode_id} receipt")
        video = receipt.get("overhead_video")
        _require(isinstance(video, dict), f"{episode_id} video metadata missing")
        _require(
            video.get("status") == "completed"
            and video.get("camera_name") == identity["recorded_name"]
            and video.get("configured_width") == identity["configured_width"]
            and video.get("configured_height") == identity["configured_height"]
            and video.get("configured_fps") == identity["configured_fps"]
            and video.get("configured_pixel_format")
            == identity["configured_pixel_format"]
            and video.get("orientation_rotation_degrees")
            == contract["frame_sampling"]["receipt_orientation_rotation_degrees"],
            f"{episode_id} camera contract changed",
        )
        video_path = receipt_path.parent / str(video.get("video_path", ""))
        _require(video_path.is_file(), f"{episode_id} video is missing")
        _require(
            sha256_file(video_path) == str(video.get("video_sha256", "")),
            f"{episode_id} video hash drifted",
        )
        bindings.append(
            {
                "episode_id": str(episode_id),
                "receipt_path": receipt_path,
                "receipt_sha256": str(episode["source_receipt_sha256"]),
                "video_path": video_path,
                "video_sha256": str(video["video_sha256"]),
                "action_start_seconds": float(
                    video["action_start_video_offset_seconds"]
                ),
            }
        )
    return bindings


def _playing_corners_px(
    contract: dict[str, Any], *, root: Path
) -> np.ndarray:
    seed = _bound_json(
        contract["sources"]["historical_board_seed"],
        root=root,
        label="historical board seed",
    )
    pixel_to_board = np.asarray(
        seed["source_proposal"]["pixel_to_board_homography"], dtype=np.float64
    )
    _require(pixel_to_board.shape == (3, 3), "board homography shape changed")
    side = float(contract["board_seed"]["playing_side_m"])
    board_corners = np.asarray(
        [[[0.0, side], [side, side], [side, 0.0], [0.0, 0.0]]],
        dtype=np.float64,
    )
    corners = cv2.perspectiveTransform(
        board_corners, np.linalg.inv(pixel_to_board)
    )[0]
    _require(
        np.all(np.isfinite(corners)) and corners.shape == (4, 2),
        "historical playing-corner seed is invalid",
    )
    return corners


def _rectangle_mean(
    integral: np.ndarray, x0: int, y0: int, x1: int, y1: int
) -> float:
    total = (
        integral[y1, x1]
        - integral[y0, x1]
        - integral[y1, x0]
        + integral[y0, x0]
    )
    return float(total) / float((x1 - x0) * (y1 - y0))


def _saddle_score(
    integral: np.ndarray,
    x: int,
    y: int,
    *,
    inner_px: int,
    outer_px: int,
) -> float:
    top_left = _rectangle_mean(
        integral, x - outer_px, y - outer_px, x - inner_px, y - inner_px
    )
    top_right = _rectangle_mean(
        integral, x + inner_px, y - outer_px, x + outer_px, y - inner_px
    )
    bottom_left = _rectangle_mean(
        integral, x - outer_px, y + inner_px, x - inner_px, y + outer_px
    )
    bottom_right = _rectangle_mean(
        integral, x + inner_px, y + inner_px, x + outer_px, y + outer_px
    )
    return abs((top_left + bottom_right) - (top_right + bottom_left)) / 2.0


def extract_frame_intersections(
    image_gray: np.ndarray,
    *,
    playing_corners_px: np.ndarray,
    extraction: dict[str, Any],
) -> dict[tuple[int, int], dict[str, Any]]:
    image = np.asarray(image_gray)
    _require(image.dtype == np.uint8, "decoded frame dtype changed")
    _require(tuple(image.shape) == (480, 640), "decoded frame shape changed")
    canonical_side = int(extraction["canonical_side_px"])
    source = np.asarray(playing_corners_px, dtype=np.float32)
    destination = np.asarray(
        [
            [0.0, 0.0],
            [canonical_side, 0.0],
            [canonical_side, canonical_side],
            [0.0, canonical_side],
        ],
        dtype=np.float32,
    )
    image_to_canonical = cv2.getPerspectiveTransform(source, destination)
    canonical_to_image = np.linalg.inv(image_to_canonical)
    warped = cv2.warpPerspective(
        image,
        image_to_canonical,
        (canonical_side + 1, canonical_side + 1),
        flags=cv2.INTER_LINEAR,
    )
    integral = cv2.integral(warped, sdepth=cv2.CV_64F)
    search = int(extraction["search_radius_px"])
    inner = int(extraction["quadrant_inner_radius_px"])
    outer = int(extraction["quadrant_outer_radius_px"])
    margin = float(extraction["minimum_seed_source_margin_px"])
    spacing = float(canonical_side) / 8.0
    result: dict[tuple[int, int], dict[str, Any]] = {}
    for i, j in extraction["interior_indices"]:
        center_x = int(round(float(i) * spacing))
        center_y = int(round(float(j) * spacing))
        seed_canonical = np.asarray(
            [[[float(center_x), float(center_y)]]], dtype=np.float64
        )
        seed_image = cv2.perspectiveTransform(
            seed_canonical, canonical_to_image
        )[0, 0]
        seed_in_bounds = bool(
            margin <= seed_image[0] <= 640.0 - margin
            and margin <= seed_image[1] <= 480.0 - margin
        )
        candidates: list[tuple[float, int, int]] = []
        for y in range(center_y - search, center_y + search + 1):
            for x in range(center_x - search, center_x + search + 1):
                candidates.append(
                    (
                        _saddle_score(
                            integral,
                            x,
                            y,
                            inner_px=inner,
                            outer_px=outer,
                        ),
                        x,
                        y,
                    )
                )
        score, x, y = max(candidates, key=lambda item: (item[0], -item[2], -item[1]))
        observed_canonical = np.asarray(
            [[[float(x), float(y)]]], dtype=np.float64
        )
        image_point = cv2.perspectiveTransform(
            observed_canonical, canonical_to_image
        )[0, 0]
        result[(int(i), int(j))] = {
            "image_point_px": image_point.tolist(),
            "seed_image_point_px": seed_image.tolist(),
            "canonical_point_px": [float(x), float(y)],
            "saddle_score": float(score),
            "seed_in_bounds": seed_in_bounds,
        }
    return result


def _decode_sampled_frames(
    binding: dict[str, Any], *, sampling: dict[str, Any]
) -> tuple[list[np.ndarray], list[dict[str, Any]], float]:
    capture = cv2.VideoCapture(str(binding["video_path"]))
    _require(capture.isOpened(), f"{binding['episode_id']} video did not open")
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        times, indices = deterministic_sample_indices(
            fps=fps,
            action_start_seconds=float(binding["action_start_seconds"]),
            start_seconds=float(sampling["start_seconds"]),
            count=int(sampling["frames_per_episode"]),
        )
        wanted = {int(index): position for position, index in enumerate(indices)}
        decoded: dict[int, np.ndarray] = {}
        frame_index = 0
        final_index = int(indices[-1])
        while frame_index <= final_index:
            ok, frame = capture.read()
            _require(ok and frame is not None, "sampled video decode failed")
            if frame_index in wanted:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                decoded[frame_index] = np.ascontiguousarray(gray)
            frame_index += 1
        _require(set(decoded) == set(wanted), "sampled frames are incomplete")
        frames = [decoded[int(index)] for index in indices]
        metadata = [
            {
                "sample_time_seconds": float(time),
                "frame_index": int(index),
                "decoded_gray_sha256": hashlib.sha256(frame.tobytes()).hexdigest(),
            }
            for time, index, frame in zip(times, indices, frames, strict=True)
        ]
        return frames, metadata, fps
    finally:
        capture.release()


def aggregate_episode(
    frame_results: list[dict[tuple[int, int], dict[str, Any]]],
    *,
    extraction: dict[str, Any],
) -> dict[tuple[int, int], dict[str, Any]]:
    top_count = int(extraction["top_frames_per_episode_per_intersection"])
    minimum_score = float(extraction["minimum_median_saddle_score"])
    maximum_dispersion = float(
        extraction["maximum_within_episode_rms_dispersion_px"]
    )
    result: dict[tuple[int, int], dict[str, Any]] = {}
    for index in [tuple(item) for item in extraction["interior_indices"]]:
        ranked = sorted(
            (
                (
                    float(frame_result[index]["saddle_score"]),
                    frame_number,
                    np.asarray(
                        frame_result[index]["image_point_px"], dtype=np.float64
                    ),
                    bool(frame_result[index]["seed_in_bounds"]),
                )
                for frame_number, frame_result in enumerate(frame_results)
            ),
            key=lambda item: (-item[0], item[1]),
        )[:top_count]
        points = np.asarray([item[2] for item in ranked], dtype=np.float64)
        scores = np.asarray([item[0] for item in ranked], dtype=np.float64)
        point = np.median(points, axis=0)
        distances = np.linalg.norm(points - point, axis=1)
        dispersion = float(np.sqrt(np.mean(distances**2)))
        median_score = float(np.median(scores))
        seed_in_bounds = all(item[3] for item in ranked)
        accepted = bool(
            seed_in_bounds
            and median_score >= minimum_score
            and dispersion <= maximum_dispersion
        )
        result[index] = {
            "image_point_px": point.tolist(),
            "median_saddle_score": median_score,
            "rms_dispersion_px": dispersion,
            "selected_frame_positions": [int(item[1]) for item in ranked],
            "seed_in_bounds": seed_in_bounds,
            "accepted": accepted,
        }
    return result


def aggregate_cross_episode(
    episode_results: dict[
        str, dict[tuple[int, int], dict[str, Any]]
    ],
    *,
    extraction: dict[str, Any],
    minimum_support: int,
    maximum_dispersion_px: float,
) -> dict[tuple[int, int], dict[str, Any]]:
    result: dict[tuple[int, int], dict[str, Any]] = {}
    for index in [tuple(item) for item in extraction["interior_indices"]]:
        observations = [
            (
                episode_id,
                np.asarray(values[index]["image_point_px"], dtype=np.float64),
            )
            for episode_id, values in episode_results.items()
            if values[index]["accepted"]
        ]
        points = np.asarray([item[1] for item in observations], dtype=np.float64)
        if len(points):
            point = np.median(points, axis=0)
            distances = np.linalg.norm(points - point, axis=1)
            dispersion = float(np.sqrt(np.mean(distances**2)))
        else:
            point = np.asarray([math.nan, math.nan], dtype=np.float64)
            dispersion = math.inf
        accepted = bool(
            len(points) >= minimum_support
            and dispersion <= maximum_dispersion_px
        )
        result[index] = {
            "image_point_px": point.tolist(),
            "episode_support": len(points),
            "episode_ids": [item[0] for item in observations],
            "rms_dispersion_px": dispersion,
            "accepted": accepted,
        }
    return result


def _initial_camera_values(
    contract: dict[str, Any], corners_px: np.ndarray
) -> np.ndarray:
    side = float(contract["board_seed"]["playing_side_m"])
    object_points = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [side, 0.0, 0.0],
            [side, side, 0.0],
            [0.0, side, 0.0],
        ],
        dtype=np.float64,
    )
    # The extraction plane uses image order a8,h8,h1,a1 as
    # canonical (0,0),(side,0),(side,side),(0,side).
    image_points = np.asarray(corners_px, dtype=np.float64)
    focal = float(contract["reference_model"]["focal_px"])
    principal = contract["reference_model"]["principal_point_px"]
    camera_matrix = np.asarray(
        [
            [focal, 0.0, float(principal[0])],
            [0.0, focal, float(principal[1])],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    ok, rotation, translation = cv2.solvePnP(
        object_points,
        image_points,
        camera_matrix,
        np.zeros(5, dtype=np.float64),
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    _require(ok, "historical pose initialization failed")
    return np.asarray(
        [
            focal,
            *rotation.ravel().tolist(),
            *translation.ravel().tolist(),
            0.0,
        ],
        dtype=np.float64,
    )


def _family(contract: dict[str, Any], radial_terms: int) -> dict[str, Any]:
    reference = contract["reference_model"]
    family_id = (
        "centered_square_pixel_zero_distortion"
        if radial_terms == 0
        else "centered_square_pixel_k1"
    )
    return {
        "family_id": family_id,
        "principal_point_px": reference["principal_point_px"],
        "square_pixels": True,
        "skew_px": 0.0,
        "radial_term_count": radial_terms,
        "radial_bound": reference["radial_bound"],
        "minimum_focal_px": reference["minimum_focal_px"],
        "maximum_focal_px": reference["maximum_focal_px"],
    }


def evaluate_cross_pose(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    bindings = _historical_episode_bindings(contract, root=root)
    corners = _playing_corners_px(contract, root=root)
    extraction = contract["pixel_extraction"]
    sampling = contract["frame_sampling"]
    episode_aggregates: dict[
        str, dict[tuple[int, int], dict[str, Any]]
    ] = {}
    episode_receipts: list[dict[str, Any]] = []
    for binding in bindings:
        frames, frame_metadata, decoded_fps = _decode_sampled_frames(
            binding, sampling=sampling
        )
        frame_results = [
            extract_frame_intersections(
                frame,
                playing_corners_px=corners,
                extraction=extraction,
            )
            for frame in frames
        ]
        aggregate = aggregate_episode(frame_results, extraction=extraction)
        episode_aggregates[binding["episode_id"]] = aggregate
        episode_receipts.append(
            {
                "episode_id": binding["episode_id"],
                "receipt_path": str(binding["receipt_path"].relative_to(root)),
                "receipt_sha256": binding["receipt_sha256"],
                "video_path": str(binding["video_path"].relative_to(root)),
                "video_sha256": binding["video_sha256"],
                "decoded_fps": decoded_fps,
                "action_start_seconds": binding["action_start_seconds"],
                "sampled_frames": frame_metadata,
                "accepted_within_episode_intersection_count": sum(
                    bool(item["accepted"]) for item in aggregate.values()
                ),
                "observations": [
                    {"index": list(index), **values}
                    for index, values in aggregate.items()
                ],
            }
        )

    gates = contract["acceptance_gates"]
    cross_episode = aggregate_cross_episode(
        episode_aggregates,
        extraction=extraction,
        minimum_support=int(gates["minimum_episode_support_per_intersection"]),
        maximum_dispersion_px=float(
            gates["maximum_cross_episode_rms_dispersion_px"]
        ),
    )
    accepted_indices = sorted(
        index for index, values in cross_episode.items() if values["accepted"]
    )
    accepted_points = np.asarray(
        [cross_episode[index]["image_point_px"] for index in accepted_indices],
        dtype=np.float64,
    )
    side = float(contract["board_seed"]["playing_side_m"])
    board_xy = np.asarray(
        [[i * side / 8.0, j * side / 8.0] for i, j in accepted_indices],
        dtype=np.float64,
    )
    initial = _initial_camera_values(contract, corners)
    enough_points = len(accepted_indices) >= int(
        gates["minimum_accepted_intersections"]
    )
    zero_fit: dict[str, Any] | None = None
    radial_fit: dict[str, Any] | None = None
    episode_focal_fits: list[dict[str, Any]] = []
    if enough_points:
        zero_fit = fit_camera_family(
            board_xy,
            accepted_points,
            family=_family(contract, 0),
            initial_values=initial,
        )
        radial_fit = fit_camera_family(
            board_xy,
            accepted_points,
            family=_family(contract, 1),
            initial_values=initial,
        )
        for binding in bindings:
            aggregate = episode_aggregates[binding["episode_id"]]
            usable = [
                index for index in accepted_indices if aggregate[index]["accepted"]
            ]
            if len(usable) < 10:
                episode_focal_fits.append(
                    {
                        "episode_id": binding["episode_id"],
                        "intersection_count": len(usable),
                        "fit_available": False,
                    }
                )
                continue
            episode_board = np.asarray(
                [[i * side / 8.0, j * side / 8.0] for i, j in usable],
                dtype=np.float64,
            )
            episode_points = np.asarray(
                [aggregate[index]["image_point_px"] for index in usable],
                dtype=np.float64,
            )
            fit = fit_camera_family(
                episode_board,
                episode_points,
                family=_family(contract, 0),
                initial_values=initial,
            )
            episode_focal_fits.append(
                {
                    "episode_id": binding["episode_id"],
                    "intersection_count": len(usable),
                    "fit_available": True,
                    "focal_px": fit["focal_px"],
                    "reprojection_rms_px": fit["reprojection_rms_px"],
                }
            )

    reference_focal = float(contract["reference_model"]["focal_px"])
    if zero_fit is not None:
        relative_focal_delta = abs(
            float(zero_fit["focal_px"]) - reference_focal
        ) / reference_focal
        radii = np.linalg.norm(
            accepted_points
            - np.asarray(
                contract["reference_model"]["principal_point_px"],
                dtype=np.float64,
            ),
            axis=1,
        )
        historical_radial_span = float(np.ptp(radii))
        radial_span_ratio = historical_radial_span / float(
            contract["reference_model"]["or10_observed_radial_interval_span_px"]
        )
        radial_gain = (
            float(zero_fit["reprojection_rms_px"])
            - float(radial_fit["reprojection_rms_px"])
        ) / float(zero_fit["reprojection_rms_px"])
        positive_depth_fraction = float(zero_fit["positive_depth_fraction"])
    else:
        relative_focal_delta = math.inf
        historical_radial_span = 0.0
        radial_span_ratio = 0.0
        radial_gain = 0.0
        positive_depth_fraction = 0.0
    available_focals = np.asarray(
        [
            item["focal_px"]
            for item in episode_focal_fits
            if item["fit_available"]
        ],
        dtype=np.float64,
    )
    focal_spread = {
        "fit_episode_count": int(len(available_focals)),
        "mean_px": (
            float(np.mean(available_focals)) if len(available_focals) else None
        ),
        "standard_deviation_px": (
            float(np.std(available_focals, ddof=1))
            if len(available_focals) >= 2
            else None
        ),
        "minimum_px": (
            float(np.min(available_focals)) if len(available_focals) else None
        ),
        "maximum_px": (
            float(np.max(available_focals)) if len(available_focals) else None
        ),
    }
    gate_results = {
        "minimum_intersections": enough_points,
        "cross_episode_dispersion": bool(
            enough_points
            and all(
                float(cross_episode[index]["rms_dispersion_px"])
                <= float(gates["maximum_cross_episode_rms_dispersion_px"])
                for index in accepted_indices
            )
        ),
        "radial_span": bool(
            radial_span_ratio
            >= float(gates["minimum_historical_to_or10_radial_span_ratio"])
        ),
        "focal_agreement": bool(
            relative_focal_delta
            <= float(gates["maximum_relative_focal_delta"])
        ),
        "positive_depth": bool(
            positive_depth_fraction
            >= float(gates["minimum_positive_depth_fraction"])
        ),
    }
    corroborated = bool(all(gate_results.values()))
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "card_id": contract["card_id"],
        "contract_sha256": (
            sha256_file(CONTRACT_PATH)
            if root == REPO_ROOT and CONTRACT_PATH.is_file()
            else canonical_digest(contract)
        ),
        "evidence_role": contract["evidence_role"],
        "source_reconciliation": {
            "included_historical_train_episode_count": len(bindings),
            "quarantined_advisory_episode_id": contract[
                "historical_episode_selection"
            ]["quarantined_advisory_inspection"]["episode_id"],
            "preserved_historical_held_out_episode_count": 3,
            "held_out_pixels_opened": False,
            "task_outcomes_used": False,
            "historical_workspace": "hackathon_era_workspace",
            "current_workspace": "post_hackathon_home_workspace",
            "workspace_mount_and_angle_match": False,
            "historical_unique_camera_id_present": False,
            "same_physical_camera_unit_proven": False,
            "new_physical_data_rows": 0,
            "new_camera_opens": 0,
        },
        "playing_corner_seed_px_raw_video": corners.tolist(),
        "episodes": episode_receipts,
        "cross_episode_observations": [
            {"index": list(index), **values}
            for index, values in cross_episode.items()
        ],
        "accepted_intersection_indices": [
            list(index) for index in accepted_indices
        ],
        "accepted_intersection_count": len(accepted_indices),
        "historical_radial_interval_span_px": historical_radial_span,
        "or10_radial_interval_span_px": float(
            contract["reference_model"]["or10_observed_radial_interval_span_px"]
        ),
        "historical_to_or10_radial_span_ratio": radial_span_ratio,
        "reference_or10_focal_px": reference_focal,
        "historical_zero_distortion_fit": zero_fit,
        "relative_focal_delta": relative_focal_delta,
        "per_episode_zero_distortion_fits": episode_focal_fits,
        "per_episode_focal_spread": focal_spread,
        "radial_k1_fit_descriptive_only": radial_fit,
        "radial_k1_in_sample_rms_gain_fraction": radial_gain,
        "radial_k1_reaches_diagnostic_interest_bar": bool(
            radial_gain
            >= float(
                gates[
                    "minimum_radial_family_rms_gain_fraction_for_diagnostic_interest"
                ]
            )
        ),
        "distortion_measured": False,
        "gate_results": gate_results,
        "focal_family_corroborated": corroborated,
        "result": (
            contract["decision_contract"]["pass_result"]
            if corroborated
            else contract["decision_contract"]["negative_result"]
        ),
        "zero_new_data_camera_lane_closed": True,
        "exact_intrinsic_calibration_approved": False,
        "current_home_workspace_extrinsics_approved": False,
        "global_camera_or_robot_mapping_approved": False,
        "simulator_canonical_camera_replaced": False,
        "limitations": [
            "The hackathon-era videos and their initial evidence frames were used by earlier retrospective work, so this is not pristine heldout validation.",
            "The historical workspace, mount, and camera angle differ from the current home workspace; only focal/lens-family corroboration is evaluated.",
            "Historical receipts omit the current C922 unique ID, so same-unit identity is an explicit unresolved assumption.",
            "The centered principal point, square pixels, and zero-distortion family remain assumptions; the radial fit is descriptive and cannot measure distortion.",
            "Agreement cannot validate current camera center, current extrinsics, global robot mapping, contact, replay, or task transfer.",
        ],
        "proof_boundaries": contract["proof_boundaries"],
        "authority": contract["authority"],
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def build_cross_pose_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    _require(not output_path.exists(), "write-once OR10B receipt already exists")
    contract = load_cross_pose_contract(contract_path, root=root)
    receipt = evaluate_cross_pose(contract, root=root)
    atomic_write_json(output_path, receipt)
    return receipt


__all__ = [
    "CONTRACT_PATH",
    "OUTPUT_PATH",
    "aggregate_cross_episode",
    "aggregate_episode",
    "build_cross_pose_receipt",
    "deterministic_sample_indices",
    "evaluate_cross_pose",
    "extract_frame_intersections",
    "load_cross_pose_contract",
]
