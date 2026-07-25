"""Detect the scene AprilTag in an existing D405 RGB image or video.

The detector is deliberately camera-only and offline.  It can bind a native
D405 recorder report to its exact video, but it does not open a camera,
construct a robot gateway, infer metric scale from nominal print dimensions,
or solve wrist/workcell extrinsics.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, sha256_file
from .paths import REPO_ROOT


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "acquisition"
    / "d405_wrist_apriltag_observation_v1.json"
)
CONTRACT_SCHEMA = "sim2claw.d405_wrist_apriltag_observation_contract.v1"
RECEIPT_SCHEMA = "sim2claw.d405_wrist_apriltag_observation_receipt.v1"
NATIVE_REPORT_SCHEMA = "sim2claw.native_dual_camera_recorder_report.v1"


class D405AprilTagObservationError(RuntimeError):
    """An input or evidence binding is invalid."""


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise D405AprilTagObservationError(
            f"cannot read {label} {path}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise D405AprilTagObservationError(f"{label} must be a JSON object")
    return value


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = _load_json(path, "contract")
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise D405AprilTagObservationError("unexpected observation contract schema")
    tag = contract.get("tag")
    if not isinstance(tag, Mapping):
        raise D405AprilTagObservationError("tag contract is missing")
    if tag.get("family") != "tag36h11" or tag.get("id") != 0:
        raise D405AprilTagObservationError("expected tag36h11 id 0 changed")
    if tag.get("physical_black_border_measured") is not False:
        raise D405AprilTagObservationError(
            "nominal tag size must remain explicitly unmeasured"
        )
    authority = contract.get("authority")
    if not isinstance(authority, Mapping) or not authority or any(authority.values()):
        raise D405AprilTagObservationError("observation authority widened")
    detector = contract.get("detector")
    if (
        not isinstance(detector, Mapping)
        or detector.get("backend") != "opencv_aruco"
        or detector.get("dictionary") != "DICT_APRILTAG_36h11"
        or detector.get("corner_refinement") != "CORNER_REFINE_SUBPIX"
    ):
        raise D405AprilTagObservationError("detector identity changed")
    maximum_frames = detector.get("maximum_video_frames")
    if not isinstance(maximum_frames, int) or maximum_frames <= 0:
        raise D405AprilTagObservationError("invalid video-frame budget")
    return contract


def _validate_native_report(
    path: Path,
    *,
    source_path: Path,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    report = _load_json(path, "native D405 capture report")
    if (
        report.get("schema_version") != NATIVE_REPORT_SCHEMA
        or report.get("status") != "completed"
        or report.get("session_count") != 1
        or report.get("independent_camera_sessions") != 0
    ):
        raise D405AprilTagObservationError(
            "native capture report is not one completed common session"
        )
    expected = contract["camera"]
    stages = {
        row.get("name"): row
        for row in report.get("stages", [])
        if isinstance(row, Mapping)
    }
    for name in ("before_commit", "after_commit", "after_start"):
        stage = stages.get(name)
        if not isinstance(stage, Mapping):
            raise D405AprilTagObservationError(
                f"native capture report lacks {name} identity"
            )
        camera = stage.get("d405")
        if not isinstance(camera, Mapping):
            raise D405AprilTagObservationError(
                f"native capture report lacks {name} D405 identity"
            )
        expected_fields = {
            "role": expected["role"],
            "localized_name": expected["localized_name"],
            "model_id": expected["model_id"],
            "width": expected["width_px"],
            "height": expected["height_px"],
            "subtype": expected["media_subtype"],
            "format_index": expected["format_index"],
            "minimum_duration_seconds": expected["frame_interval_seconds"],
            "maximum_duration_seconds": expected["frame_interval_seconds"],
        }
        if any(camera.get(key) != value for key, value in expected_fields.items()):
            raise D405AprilTagObservationError(
                f"native capture report {name} D405 mode changed"
            )
        if (
            stage.get("d405_input_admitted") is not True
            or stage.get("d405_output_admitted") is not True
            or stage.get("d405_output_bound_to_exact_input") is not True
        ):
            raise D405AprilTagObservationError(
                f"native capture report {name} did not admit the D405 stream"
            )
    streams = [
        row
        for row in report.get("streams", [])
        if isinstance(row, Mapping) and row.get("role") == "d405"
    ]
    if len(streams) != 1:
        raise D405AprilTagObservationError(
            "native capture report must contain one D405 stream"
        )
    stream = streams[0]
    reported_source = (path.parent / str(stream.get("output_path"))).resolve()
    if reported_source != source_path.resolve():
        raise D405AprilTagObservationError(
            "source video is not the D405 output bound by the native report"
        )
    if (
        stream.get("writer_status") != "completed"
        or stream.get("errors") != []
        or int(stream.get("writer_append_count", 0)) <= 0
    ):
        raise D405AprilTagObservationError(
            "native capture report D405 stream is incomplete"
        )
    camera = stages["after_start"]["d405"]
    return {
        "report_path": str(path.resolve()),
        "report_sha256": sha256_file(path),
        "camera_unique_id": camera.get("unique_id"),
        "camera_mode": {
            "localized_name": camera.get("localized_name"),
            "model_id": camera.get("model_id"),
            "width_px": camera.get("width"),
            "height_px": camera.get("height"),
            "media_subtype": camera.get("subtype"),
            "format_index": camera.get("format_index"),
            "frame_interval_seconds": camera.get("minimum_duration_seconds"),
        },
        "writer_append_count": int(stream["writer_append_count"]),
        "first_pts_seconds": stream.get("first_pts_seconds"),
        "last_pts_seconds": stream.get("last_pts_seconds"),
        "camera_exposure_timestamps": False,
        "metric_depth": False,
    }


def _frames(
    source_path: Path, maximum_video_frames: int
) -> tuple[Iterator[tuple[int, np.ndarray]], dict[str, Any]]:
    image = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
    if image is not None:
        height, width = image.shape[:2]
        return iter(((0, image),)), {
            "kind": "image",
            "reported_frame_count": 1,
            "reported_fps": None,
            "width_px": int(width),
            "height_px": int(height),
        }
    capture = cv2.VideoCapture(str(source_path))
    if not capture.isOpened():
        raise D405AprilTagObservationError(
            f"source is not a readable image or video: {source_path}"
        )
    reported_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    reported_fps = float(capture.get(cv2.CAP_PROP_FPS))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))

    def iterate() -> Iterator[tuple[int, np.ndarray]]:
        try:
            for frame_index in range(maximum_video_frames):
                ok, frame = capture.read()
                if not ok:
                    break
                yield frame_index, frame
        finally:
            capture.release()

    return iterate(), {
        "kind": "video",
        "reported_frame_count": reported_count,
        "reported_fps": reported_fps if math.isfinite(reported_fps) else None,
        "width_px": width,
        "height_px": height,
    }


def observe_d405_apriltag(
    *,
    source_path: Path,
    output_path: Path,
    contract_path: Path = CONTRACT_PATH,
    capture_report_path: Path | None = None,
    selected_frame_output: Path | None = None,
) -> dict[str, Any]:
    """Detect the frozen scene tag and write a hash-bound observation receipt."""

    source_path = source_path.resolve()
    contract_path = contract_path.resolve()
    output_path = output_path.resolve()
    if not source_path.is_file():
        raise D405AprilTagObservationError(f"source does not exist: {source_path}")
    contract = load_contract(contract_path)
    capture_binding = (
        _validate_native_report(
            capture_report_path.resolve(),
            source_path=source_path,
            contract=contract,
        )
        if capture_report_path is not None
        else None
    )
    detector_settings = contract["detector"]
    frames, source_metadata = _frames(
        source_path, int(detector_settings["maximum_video_frames"])
    )
    parameters = cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector = cv2.aruco.ArucoDetector(
        cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11),
        parameters,
    )
    expected_id = int(contract["tag"]["id"])
    minimum_edge = float(contract["tag"]["minimum_mean_detected_edge_px"])
    detections: list[dict[str, Any]] = []
    duplicate_target_frames: list[int] = []
    observed_ids: set[int] = set()
    frames_scanned = 0
    selected_frame: np.ndarray | None = None
    selected_key: tuple[float, int] | None = None
    for frame_index, frame in frames:
        frames_scanned += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, _rejected = detector.detectMarkers(gray)
        if ids is None:
            continue
        raw_ids = [int(value) for value in ids.reshape(-1)]
        observed_ids.update(raw_ids)
        target_indices = [
            index for index, value in enumerate(raw_ids) if value == expected_id
        ]
        if len(target_indices) > int(contract["tag"]["maximum_instances_per_frame"]):
            duplicate_target_frames.append(frame_index)
        for target_index in target_indices:
            points = np.asarray(corners[target_index], dtype=np.float64).reshape(4, 2)
            edge_lengths = np.linalg.norm(
                np.roll(points, -1, axis=0) - points, axis=1
            )
            mean_edge = float(np.mean(edge_lengths))
            row = {
                "frame_index": frame_index,
                "corners_px": points.tolist(),
                "edge_lengths_px": edge_lengths.tolist(),
                "mean_edge_length_px": mean_edge,
                "passes_minimum_edge": mean_edge >= minimum_edge,
            }
            detections.append(row)
            key = (mean_edge, -frame_index)
            if row["passes_minimum_edge"] and (
                selected_key is None or key > selected_key
            ):
                selected_key = key
                selected_frame = frame.copy()
    passing = [row for row in detections if row["passes_minimum_edge"]]
    if duplicate_target_frames:
        verdict = "invalid_duplicate_target"
    elif passing:
        verdict = "target_observed"
    else:
        verdict = "target_not_observed"
    selected = (
        max(passing, key=lambda row: (row["mean_edge_length_px"], -row["frame_index"]))
        if passing
        else None
    )
    selected_artifact = None
    if selected is not None and selected_frame_output is not None:
        selected_frame_output = selected_frame_output.resolve()
        selected_frame_output.parent.mkdir(parents=True, exist_ok=True)
        if selected_frame is None or not cv2.imwrite(
            str(selected_frame_output), selected_frame
        ):
            raise D405AprilTagObservationError(
                f"cannot write selected frame: {selected_frame_output}"
            )
        selected_artifact = {
            "path": str(selected_frame_output),
            "sha256": sha256_file(selected_frame_output),
            "source_frame_index": selected["frame_index"],
        }
    missing = list(contract["required_for_wrist_registration"])
    if capture_binding is not None:
        missing.remove("native_d405_capture_report_binding")
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_path": str(contract_path),
        "contract_sha256": sha256_file(contract_path),
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "status": verdict,
        "source": {
            "path": str(source_path),
            "sha256": sha256_file(source_path),
            "size_bytes": source_path.stat().st_size,
            **source_metadata,
            "frames_scanned": frames_scanned,
        },
        "capture_binding": capture_binding,
        "detector": {
            **detector_settings,
            "opencv_version": cv2.__version__,
        },
        "tag": {
            "family": contract["tag"]["family"],
            "id": expected_id,
            "nominal_black_border_side_m": contract["tag"][
                "nominal_black_border_side_m"
            ],
            "physical_black_border_measured": False,
            "observed_ids": sorted(observed_ids),
            "target_detection_count": len(detections),
            "passing_target_detection_count": len(passing),
            "duplicate_target_frames": duplicate_target_frames,
            "selected_detection": selected,
            "selected_frame_artifact": selected_artifact,
        },
        "registration_readiness": {
            "tag_pixel_observation_available": selected is not None,
            "source_lineage_bound_to_native_d405_capture": capture_binding is not None,
            "metric_scale_established": False,
            "wrist_extrinsics_established": False,
            "board_to_workcell_registration_established": False,
            "missing_facts": missing,
        },
        "authority": dict(contract["authority"]),
    }
    atomic_write_json(output_path, receipt)
    return receipt
