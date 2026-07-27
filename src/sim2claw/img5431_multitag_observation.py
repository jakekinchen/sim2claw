"""Hash-bound AprilTag pixel observations from the new phone workspace video.

Integer tag IDs are deliberately not treated as physical instance identity.
IMG_5431 contains two physically different tags with integer ID 0, so every
detection remains a frame-local observation until a future association owner
has calibrated intrinsics and independently justified tracks.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterator, Mapping

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json
from .paths import REPO_ROOT


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "acquisition"
    / "img5431_multitag_observation_v1.json"
)
CONTRACT_SCHEMA = "sim2claw.img5431_multitag_observation_contract.v1"
RECEIPT_SCHEMA = "sim2claw.img5431_multitag_observation.v1"


class Img5431ObservationError(RuntimeError):
    """The source, detector, or no-authority observation contract changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Img5431ObservationError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Img5431ObservationError(
            f"cannot read {label}: {error}"
        ) from error
    _require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = _load_json(path, "IMG_5431 observation contract")
    detector = contract.get("detector", {})
    tags = contract.get("tags", {})
    authority = contract.get("authority", {})
    _require(
        contract.get("schema_version") == CONTRACT_SCHEMA
        and contract.get("status")
        == "preregistered_before_manifest_materialization"
        and contract.get("sampling", {}).get("frame_stride") == 30
        and detector.get("dictionary") == "DICT_APRILTAG_36h11"
        and detector.get("corner_refinement") == "CORNER_REFINE_SUBPIX"
        and detector.get("error_correction_rate") == 0.0
        and tags.get("required_integer_ids") == list(range(7))
        and tags.get("integer_id_is_cross_frame_physical_identity") is False,
        "IMG_5431 detector, sampling, or identity contract changed",
    )
    _require(
        authority.get("pixel_observations") is True
        and all(
            authority.get(field) is False
            for field in (
                "camera_intrinsics",
                "camera_trajectory",
                "cross_frame_instance_association",
                "metric_bundle_adjustment",
                "camera_extrinsics",
                "tag_to_link_transform_promotion",
                "simulator_parameter_promotion",
                "physical_authority",
                "task_success",
            )
        ),
        "IMG_5431 observation authority widened",
    )
    return contract


def _make_detector(
    settings: Mapping[str, Any],
) -> cv2.aruco.ArucoDetector:
    parameters = cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    parameters.aprilTagQuadDecimate = float(
        settings["april_tag_quad_decimate"]
    )
    parameters.aprilTagMinClusterPixels = int(
        settings["april_tag_min_cluster_pixels"]
    )
    parameters.minMarkerPerimeterRate = float(
        settings["minimum_marker_perimeter_rate"]
    )
    parameters.adaptiveThreshWinSizeMin = int(
        settings["adaptive_threshold_window_minimum"]
    )
    parameters.adaptiveThreshWinSizeMax = int(
        settings["adaptive_threshold_window_maximum"]
    )
    parameters.adaptiveThreshWinSizeStep = int(
        settings["adaptive_threshold_window_step"]
    )
    parameters.errorCorrectionRate = float(
        settings["error_correction_rate"]
    )
    dictionary = cv2.aruco.getPredefinedDictionary(
        cv2.aruco.DICT_APRILTAG_36h11
    )
    return cv2.aruco.ArucoDetector(dictionary, parameters)


def _detect_frame(
    frame: np.ndarray,
    *,
    frame_index: int,
    detector: cv2.aruco.ArucoDetector,
) -> list[dict[str, Any]]:
    corners, ids, _rejected = detector.detectMarkers(frame)
    if ids is None:
        return []
    observations: list[dict[str, Any]] = []
    for detection_index, (tag_id, raw_corners) in enumerate(
        zip(ids.reshape(-1), corners, strict=True)
    ):
        points = np.asarray(raw_corners, dtype=np.float64).reshape(4, 2)
        edges = np.linalg.norm(np.roll(points, -1, axis=0) - points, axis=1)
        observations.append(
            {
                "instance_key": f"{frame_index}:{detection_index}",
                "frame_index": frame_index,
                "detection_index": detection_index,
                "tag_id": int(tag_id),
                "corners_px": points.tolist(),
                "center_px": np.mean(points, axis=0).tolist(),
                "edge_lengths_px": edges.tolist(),
                "integer_id_used_as_physical_instance_identity": False,
            }
        )
    return observations


def _iter_sampled_video_frames(
    source_path: Path,
    *,
    stride: int,
) -> Iterator[tuple[int, np.ndarray]]:
    capture = cv2.VideoCapture(str(source_path))
    _require(capture.isOpened(), "could not open IMG_5431 video")
    index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if index % stride == 0:
                yield index, frame
            index += 1
    finally:
        capture.release()


def _geometry_inputs(
    contract: Mapping[str, Any],
) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    for item in contract["geometry_inputs"]:
        path = REPO_ROOT / str(item["path"])
        _require(
            path.is_file() and _sha256(path) == item["sha256"],
            f"geometry input changed: {item['role']}",
        )
        verified.append(
            {
                **item,
                "path": str(path.resolve()),
                "hash_verified": True,
                "consumed_as_metric_transform": False,
            }
        )
    return verified


def observe_img5431_multitags(
    *,
    source_path: Path,
    output_path: Path,
    contract_path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    contract_path = contract_path.resolve()
    contract = load_contract(contract_path)
    source_path = source_path.resolve()
    output_path = output_path.resolve()
    source = contract["source"]
    _require(
        source_path.is_file()
        and source_path.stat().st_size == source["bytes"]
        and _sha256(source_path) == source["sha256"],
        "IMG_5431 source bytes changed",
    )
    _require(not output_path.exists(), "refusing to overwrite IMG_5431 manifest")
    cv2.setNumThreads(1)
    detector = _make_detector(contract["detector"])
    stride = int(contract["sampling"]["frame_stride"])
    observations: list[dict[str, Any]] = []
    sampled_frames: list[dict[str, Any]] = []
    width: int | None = None
    height: int | None = None
    for frame_index, frame in _iter_sampled_video_frames(
        source_path, stride=stride
    ):
        current_height, current_width = frame.shape[:2]
        width = current_width if width is None else width
        height = current_height if height is None else height
        _require(
            current_width == width and current_height == height,
            "decoded IMG_5431 frame dimensions changed",
        )
        frame_sha256 = hashlib.sha256(
            np.ascontiguousarray(frame).tobytes()
        ).hexdigest()
        rows = _detect_frame(
            frame, frame_index=frame_index, detector=detector
        )
        for row in rows:
            row["decoded_frame_sha256"] = frame_sha256
        observations.extend(rows)
        sampled_frames.append(
            {
                "frame_index": frame_index,
                "decoded_frame_sha256": frame_sha256,
                "detection_count": len(rows),
            }
        )
    _require(width is not None and height is not None, "IMG_5431 decoded no frames")
    _require(
        width == source["decoded_width"]
        and height == source["decoded_height"],
        "IMG_5431 decoded dimensions changed",
    )
    required = set(int(value) for value in contract["tags"]["required_integer_ids"])
    counts = {
        tag_id: sum(row["tag_id"] == tag_id for row in observations)
        for tag_id in sorted(required)
    }
    observed = {tag_id for tag_id, count in counts.items() if count > 0}
    missing = sorted(required - observed)
    complete = not missing
    payload = {
        "schema_version": RECEIPT_SCHEMA,
        "status": (
            "all_required_ids_observed_identity_ambiguous"
            if complete
            else "incomplete_required_ids_identity_ambiguous"
        ),
        "proof_class": "physical_video_pixel_observation_only",
        "contract": {
            "path": str(contract_path),
            "sha256": _sha256(contract_path),
        },
        "source": {
            "path": str(source_path),
            "sha256": source["sha256"],
            "bytes": source["bytes"],
            "decoded_width": width,
            "decoded_height": height,
            "encoded_width_contract": source["encoded_width"],
            "encoded_height_contract": source["encoded_height"],
            "display_rotation_degrees_contract": source[
                "display_rotation_degrees"
            ],
            "video_frame_count_contract": source["frame_count"],
            "video_fps_approximate_contract": source["fps_approximate"],
        },
        "detector": {
            **contract["detector"],
            "opencv_version": cv2.__version__,
            "opencv_threads": 1,
        },
        "sampling": {
            **contract["sampling"],
            "sampled_frame_count": len(sampled_frames),
        },
        "sampled_frames": sampled_frames,
        "observations": observations,
        "summary": {
            "required_integer_ids": sorted(required),
            "observed_integer_ids": sorted(observed),
            "missing_integer_ids": missing,
            "detection_count_by_integer_id": {
                str(key): value for key, value in counts.items()
            },
            "maximum_simultaneous_detections": max(
                (row["detection_count"] for row in sampled_frames),
                default=0,
            ),
            "all_required_ids_observed": complete,
            "integer_id_zero_known_physically_duplicated": True,
        },
        "tag_size": {
            "operator_declared_full_square_side_m": contract["tags"][
                "operator_declared_full_square_side_m"
            ],
            "black_boundary_side_m": None,
        },
        "assignment_priors": contract["assignment_priors"],
        "geometry_inputs": _geometry_inputs(contract),
        "registration_readiness": {
            "pixel_observation_graph_ready": complete,
            "cross_frame_instance_association_ready": False,
            "camera_intrinsics_available": False,
            "camera_trajectory_available": False,
            "metric_bundle_adjustment_ready": False,
        },
        "authority": contract["authority"],
    }
    _require(
        all(
            math.isfinite(coordinate)
            for row in observations
            for corner in row["corners_px"]
            for coordinate in corner
        ),
        "IMG_5431 observation contains a non-finite corner",
    )
    atomic_write_json(output_path, payload)
    return {
        **payload,
        "receipt_path": str(output_path),
        "receipt_sha256": _sha256(output_path),
    }


__all__ = [
    "CONTRACT_PATH",
    "Img5431ObservationError",
    "_detect_frame",
    "_make_detector",
    "load_contract",
    "observe_img5431_multitags",
]
