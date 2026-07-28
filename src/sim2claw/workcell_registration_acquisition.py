"""Stationary C922 capture and non-authoritative P13 input assembly."""

from __future__ import annotations

import copy
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import cv2
import numpy as np
from PIL import Image

from . import metric_registration_readiness as readiness
from .c922_exact_mode_calibration import load_contract as load_c922_contract
from .native_dual_camera import NativeDualCameraRecorder
from .workcell_registration import (
    BOARD_POSE_ID,
    STATIONARY_CAPTURE_SCHEMA,
    SURVEY_SCHEMA,
    WORKSPACE_POSE_ID,
    WorkcellRegistrationError,
    validate_survey,
)


ANNOTATION_SCHEMA = "sim2claw.workcell_registration_annotation.v1"
FRAME_EXTRACTION_SCHEMA = "sim2claw.frame_extraction_receipt.v1"
CAPTURE_SECONDS = 2.0
ACKNOWLEDGEMENTS = (
    "board_and_camera_fixed",
    "board_cleared",
    "a1_h1_a8_markers_visible",
    "focus_locked",
    "no_competing_camera_owner",
)
POINT_PLAN = (
    ("a1", (-0.375, -0.375), "south_west"),
    ("b2", (-0.125, -0.125), "south_west"),
    ("g2", (0.125, -0.125), "south_east"),
    ("h1", (0.375, -0.375), "south_east"),
    ("a8", (-0.375, 0.375), "north_west"),
    ("b7", (-0.125, 0.125), "north_west"),
    ("g7", (0.125, 0.125), "north_east"),
    ("h8", (0.375, 0.375), "north_east"),
)
CaptureBackend = Callable[[Path], Mapping[str, Any]]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkcellRegistrationError(message)


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkcellRegistrationError(f"Could not load {label}: {error}") from error
    _require(isinstance(value, dict), f"{label} must be an object.")
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    data = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    _require(not path.exists(), f"Output already exists: {path}")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _inside(root: Path, path: Path, label: str) -> Path:
    resolved = path.resolve()
    _require(
        resolved != root.resolve() and resolved.is_relative_to(root.resolve()),
        f"{label} escapes repository root.",
    )
    return resolved


def _relative(path: Path, root: Path) -> str:
    return str(_inside(root, path, "artifact").relative_to(root.resolve()))


def _pointer(path: Path, root: Path) -> dict[str, str]:
    return {
        "artifact_path": _relative(path, root),
        "artifact_sha256": readiness.sha256_file(path),
    }


def _expected_exact_mode() -> dict[str, Any]:
    camera = load_c922_contract()["camera"]
    return {
        key: camera[key]
        for key in (
            "localized_name",
            "model_id",
            "unique_id",
            "media_subtype",
            "format_index",
            "frame_rate_range_index",
            "frame_rate_fps",
            "orientation_filter",
        )
    }


def _native_backend(output: Path) -> dict[str, Any]:
    draft = output / "native_burst"
    recorder = NativeDualCameraRecorder(draft)
    recorder.start()
    started = time.monotonic()
    try:
        while time.monotonic() - started < CAPTURE_SECONDS:
            time.sleep(0.05)
            recorder.ensure_running()
    finally:
        completed = recorder.finish(
            action_started_monotonic=None,
            action_stopped_monotonic=time.monotonic(),
            post_roll_seconds=0.0,
        )
    video = recorder.overhead_browser_path
    capture = cv2.VideoCapture(str(video))
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    _require(capture.isOpened() and fps > 0.0, "Captured C922 video is unreadable.")
    frames: list[dict[str, Any]] = []
    index = 0
    while True:
        ok, pixels = capture.read()
        if not ok:
            break
        frames.append(
            {
                "frame_index": index,
                "source_timestamp_seconds": index / fps,
                "pixels_bgr": pixels,
            }
        )
        index += 1
    capture.release()
    _require(bool(frames), "Captured C922 burst contains no frames.")
    return {
        "frames": frames,
        "source_video_path": video,
        "native_report_path": recorder.report_path,
        "callback_ledger_path": recorder.events_path,
        "exact_mode": _expected_exact_mode(),
        "native_common_session": completed["common_session"],
    }


def _synthetic_backend(output: Path) -> dict[str, Any]:
    burst = output / "synthetic_burst.bin"
    burst.write_bytes(b"synthetic-stationary-capture")
    report = output / "synthetic_native_report.json"
    report.write_text('{"synthetic":true}\n', encoding="utf-8")
    ledger = output / "synthetic_callback_ledger.jsonl"
    ledger.write_text('{"synthetic":true}\n', encoding="utf-8")
    frames = []
    for index, blur in enumerate((9, 5, 1)):
        pixels = np.zeros((480, 640, 3), dtype=np.uint8)
        pixels[80:400:8, 100:540:8] = 255
        if blur > 1:
            pixels = cv2.GaussianBlur(pixels, (blur, blur), 0)
        frames.append(
            {
                "frame_index": index,
                "source_timestamp_seconds": 0.25 * index,
                "pixels_bgr": pixels,
            }
        )
    return {
        "frames": frames,
        "source_video_path": burst,
        "native_report_path": report,
        "callback_ledger_path": ledger,
        "exact_mode": _expected_exact_mode(),
        "native_common_session": {"synthetic": True},
    }


def _select_frame(
    frames: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], list[dict[str, Any]]]:
    scored: list[tuple[float, float, int, Mapping[str, Any]]] = []
    public: list[dict[str, Any]] = []
    for frame in frames:
        pixels = np.asarray(frame.get("pixels_bgr"))
        _require(
            pixels.shape == (480, 640, 3) and pixels.dtype == np.uint8,
            "Capture candidate is not a 640x480 uint8 frame.",
        )
        score = float(cv2.Laplacian(pixels, cv2.CV_64F).var())
        timestamp = float(frame["source_timestamp_seconds"])
        index = int(frame["frame_index"])
        _require(np.isfinite(score) and np.isfinite(timestamp), "Frame score is invalid.")
        scored.append((-score, timestamp, index, frame))
        public.append(
            {
                "frame_index": index,
                "source_timestamp_seconds": timestamp,
                "sharpness_laplacian_variance": score,
            }
        )
    _require(bool(scored), "Capture produced no selectable frame.")
    scored.sort(key=lambda value: value[:3])
    return scored[0][3], sorted(public, key=lambda value: value["frame_index"])


def write_annotation_bundle(
    capture_receipt_path: Path,
    output_directory: Path,
    *,
    repo_root: Path = readiness.REPO_ROOT,
) -> dict[str, Any]:
    root = repo_root.resolve()
    output = _inside(root, output_directory, "annotation bundle")
    _require(not output.exists(), "Annotation bundle output already exists.")
    receipt = _load(capture_receipt_path, "stationary capture receipt")
    _require(
        receipt.get("schema_version") == STATIONARY_CAPTURE_SCHEMA,
        "Stationary capture receipt schema changed.",
    )
    output.mkdir(parents=True)
    paths: dict[str, str] = {}
    for role in ("annotator_a", "annotator_b"):
        template = {
            "schema_version": ANNOTATION_SCHEMA,
            "status": "incomplete_independent_annotation",
            "annotation_role": role,
            "annotator_id": None,
            "source_frame_sha256": receipt["selected_frame_sha256"],
            "capture_receipt_sha256": readiness.sha256_file(capture_receipt_path),
            "points": [
                {
                    "point_id": point_id,
                    "board_fraction_xy": list(fraction),
                    "board_quadrant": quadrant,
                    "pixel_xy": None,
                    "detector_hint_px": None,
                }
                for point_id, fraction, quadrant in POINT_PLAN
            ],
            "synthetic_capture": receipt["synthetic"],
            "evaluator_owned": False,
            "physical_authority": False,
        }
        path = output / f"{role}.json"
        _write(path, template)
        paths[role] = str(path)
    bundle = {
        "status": "annotation_bundle_incomplete",
        "capture_receipt_path": str(capture_receipt_path),
        "capture_receipt_sha256": readiness.sha256_file(capture_receipt_path),
        "annotation_templates": paths,
        "point_count": len(POINT_PLAN),
        "quadrants": ["north_east", "north_west", "south_east", "south_west"],
        "synthetic": receipt["synthetic"],
        "evaluator_owned": False,
        "physical_authority": False,
    }
    _write(output / "bundle.json", bundle)
    return bundle


def capture_stationary_bundle(
    output_directory: Path,
    *,
    acknowledgements: Mapping[str, bool],
    focus_setting: str | None,
    dry_run: bool = False,
    capture_backend: CaptureBackend | None = None,
    repo_root: Path = readiness.REPO_ROOT,
    selector_path: Path = Path(__file__),
) -> dict[str, Any]:
    root = repo_root.resolve()
    output = _inside(root, output_directory, "stationary capture")
    _require(not output.exists(), "Stationary capture output already exists.")
    if not dry_run:
        _require(
            set(acknowledgements) == set(ACKNOWLEDGEMENTS)
            and all(acknowledgements.values()),
            "Every stationary capture acknowledgement must be explicit.",
        )
        _require(
            isinstance(focus_setting, str) and bool(focus_setting.strip()),
            "Observable locked focus setting is required.",
        )
    output.mkdir(parents=True)
    backend = capture_backend or (_synthetic_backend if dry_run else _native_backend)
    captured = dict(backend(output))
    _require(captured.get("exact_mode") == _expected_exact_mode(), "C922 exact mode changed.")
    selected, scores = _select_frame(captured.get("frames") or [])
    selected_path = output / "selected_frame.png"
    Image.fromarray(
        cv2.cvtColor(np.asarray(selected["pixels_bgr"]), cv2.COLOR_BGR2RGB)
    ).save(selected_path)
    video = Path(captured["source_video_path"]).resolve()
    native_report = Path(captured["native_report_path"]).resolve()
    callback_ledger = Path(captured["callback_ledger_path"]).resolve()
    for path, label in (
        (video, "source video"),
        (native_report, "native report"),
        (callback_ledger, "callback ledger"),
    ):
        _require(path.is_file() and path.is_relative_to(root), f"{label} is unavailable.")
    extraction = {
        "schema_version": FRAME_EXTRACTION_SCHEMA,
        "source_video_sha256": readiness.sha256_file(video),
        "source_timestamp_seconds": float(selected["source_timestamp_seconds"]),
        "source_frame_index": int(selected["frame_index"]),
        "selection_rule": "maximum_laplacian_variance_then_earliest_timestamp_then_frame_index",
        "candidate_scores": scores,
        "decoder_identity": {
            "name": "sim2claw-stationary-frame-selector",
            "version": "1",
            "executable_path": _relative(selector_path, root),
            "executable_sha256": readiness.sha256_file(selector_path),
        },
        "orientation_filter": "hflip,vflip",
        "output_frame_sha256": readiness.sha256_file(selected_path),
        "synthetic": dry_run,
        "evaluator_owned": False,
    }
    extraction_path = output / "frame_extraction_receipt.json"
    _write(extraction_path, extraction)
    receipt = {
        "schema_version": STATIONARY_CAPTURE_SCHEMA,
        "status": "synthetic_non_authoritative" if dry_run else "physical_capture_complete",
        "proof_class": "synthetic_fixture" if dry_run else "physical_camera_frame",
        "synthetic": dry_run,
        "camera_id": "logitech-overhead",
        "image_size_px": [640, 480],
        "exact_mode": captured["exact_mode"],
        "focus_setting": "synthetic_fixture" if dry_run else focus_setting,
        "operator_acknowledgements": dict(acknowledgements),
        "source_video_path": _relative(video, root),
        "source_video_sha256": readiness.sha256_file(video),
        "native_report_path": _relative(native_report, root),
        "native_report_sha256": readiness.sha256_file(native_report),
        "callback_ledger_path": _relative(callback_ledger, root),
        "callback_ledger_sha256": readiness.sha256_file(callback_ledger),
        "selected_frame_path": _relative(selected_path, root),
        "selected_frame_sha256": readiness.sha256_file(selected_path),
        "frame_extraction_receipt": _pointer(extraction_path, root),
        "native_common_session": captured["native_common_session"],
        "capture_duration_limit_seconds": CAPTURE_SECONDS,
        "robot_gateway_constructed": False,
        "robot_motion_used": 0,
        "evaluator_owned": False,
        "physical_authority": False,
        "captured_at": (
            "2000-01-01T00:00:00+00:00" if dry_run else datetime.now(UTC).isoformat()
        ),
    }
    receipt_path = output / "capture_receipt.json"
    _write(receipt_path, receipt)
    bundle = write_annotation_bundle(
        receipt_path, output / "annotations", repo_root=root
    )
    return {
        "capture_receipt_path": str(receipt_path),
        "capture_receipt_sha256": readiness.sha256_file(receipt_path),
        "selected_frame_path": str(selected_path),
        "selected_frame_sha256": readiness.sha256_file(selected_path),
        "annotation_bundle": bundle,
        "synthetic": dry_run,
        "evaluator_owned": False,
        "physical_authority": False,
    }


def _validate_board_receipt(path: Path) -> tuple[dict[str, Any], str]:
    value = _load(path, "direct board measurement")
    digest = readiness.sha256_file(path)
    _require(
        value.get("schema_version")
        == "sim2claw.direct_board_measurement_receipt.v1"
        and value.get("measurement_method") == "direct_physical_measurement"
        and readiness._finite_number(value.get("playing_side_m"), positive=True)  # noqa: SLF001
        and readiness._finite_number(  # noqa: SLF001
            value.get("standard_uncertainty_m"), positive=True
        )
        and isinstance(value.get("measurement_tool_id"), str)
        and bool(value["measurement_tool_id"])
        and value.get("nominal_value_substituted") is False
        and value.get("synthetic") is False,
        "Board measurement is nominal, synthetic, or untraceable.",
    )
    return value, digest


def _validate_annotation(
    value: Mapping[str, Any],
    *,
    role: str,
    frame_sha256: str,
    capture_sha256: str,
) -> tuple[str, dict[str, list[float]]]:
    _require(
        value.get("schema_version") == ANNOTATION_SCHEMA
        and value.get("status") == "complete_independent_annotation"
        and value.get("annotation_role") == role
        and value.get("source_frame_sha256") == frame_sha256
        and value.get("capture_receipt_sha256") == capture_sha256
        and value.get("synthetic_capture") is False
        and value.get("evaluator_owned") is False,
        f"{role} annotation identity or authority changed.",
    )
    annotator = value.get("annotator_id")
    _require(
        isinstance(annotator, str) and bool(annotator.strip()),
        f"{role} annotator is missing.",
    )
    points = value.get("points")
    _require(isinstance(points, list) and len(points) == len(POINT_PLAN), f"{role} points changed.")
    result: dict[str, list[float]] = {}
    expected = {point_id: (fraction, quadrant) for point_id, fraction, quadrant in POINT_PLAN}
    for row in points:
        _require(isinstance(row, Mapping), f"{role} point is malformed.")
        point_id = row.get("point_id")
        pixel = row.get("pixel_xy")
        _require(
            point_id in expected
            and row.get("board_fraction_xy") == list(expected[point_id][0])
            and row.get("board_quadrant") == expected[point_id][1]
            and isinstance(pixel, list)
            and len(pixel) == 2
            and all(
                isinstance(item, (int, float))
                and not isinstance(item, bool)
                and np.isfinite(float(item))
                for item in pixel
            )
            and 0.0 <= float(pixel[0]) < 640.0
            and 0.0 <= float(pixel[1]) < 480.0
            and point_id not in result,
            f"{role} point identity, plan, or pixel bounds changed.",
        )
        result[str(point_id)] = [float(pixel[0]), float(pixel[1])]
    _require(set(result) == set(expected), f"{role} point set is incomplete.")
    return annotator, result


def finalize_metric_registration_input(
    *,
    capture_receipt_path: Path,
    annotator_a_path: Path,
    annotator_b_path: Path,
    board_measurement_path: Path,
    survey_path: Path,
    intrinsics_path: Path,
    distortion_path: Path,
    output_path: Path,
    repo_root: Path = readiness.REPO_ROOT,
) -> dict[str, Any]:
    root = repo_root.resolve()
    output = _inside(root, output_path, "finalized manifest")
    _require(not output.exists(), "Finalized manifest output already exists.")
    capture = _load(capture_receipt_path, "stationary capture receipt")
    capture_sha = readiness.sha256_file(capture_receipt_path)
    _require(
        capture.get("schema_version") == STATIONARY_CAPTURE_SCHEMA
        and capture.get("status") == "physical_capture_complete"
        and capture.get("proof_class") == "physical_camera_frame"
        and capture.get("synthetic") is False
        and capture.get("exact_mode") == _expected_exact_mode()
        and capture.get("robot_gateway_constructed") is False
        and capture.get("robot_motion_used") == 0
        and set(capture.get("operator_acknowledgements") or {})
        == set(ACKNOWLEDGEMENTS)
        and all(capture["operator_acknowledgements"].values()),
        "Capture is synthetic, unacknowledged, wrong-mode, or motion-coupled.",
    )
    frame = _inside(root, root / capture["selected_frame_path"], "selected frame")
    video = _inside(root, root / capture["source_video_path"], "source video")
    _require(
        frame.is_file()
        and readiness.sha256_file(frame) == capture["selected_frame_sha256"]
        and video.is_file()
        and readiness.sha256_file(video) == capture["source_video_sha256"],
        "Capture frame or video hash changed.",
    )
    extraction_pointer = capture.get("frame_extraction_receipt")
    _require(isinstance(extraction_pointer, Mapping), "Extraction receipt is missing.")
    extraction_path = _inside(
        root, root / str(extraction_pointer.get("artifact_path")), "extraction receipt"
    )
    extraction = _load(extraction_path, "frame extraction receipt")
    _require(
        readiness.sha256_file(extraction_path)
        == extraction_pointer.get("artifact_sha256")
        and extraction.get("schema_version") == FRAME_EXTRACTION_SCHEMA
        and extraction.get("source_video_sha256") == capture["source_video_sha256"]
        and extraction.get("output_frame_sha256") == capture["selected_frame_sha256"]
        and extraction.get("synthetic") is False,
        "Extraction lineage changed or is synthetic.",
    )
    board, board_sha = _validate_board_receipt(board_measurement_path)
    survey = _load(survey_path, "board-to-workcell survey")
    _require(survey.get("schema_version") == SURVEY_SCHEMA, "Survey schema changed.")
    validate_survey(survey, root=root, board_measurement_sha256=board_sha)
    for camera_path, schema in (
        (intrinsics_path, "sim2claw.camera_intrinsics_receipt.v1"),
        (distortion_path, "sim2claw.lens_distortion_receipt.v1"),
    ):
        value = _load(camera_path, "P8 camera receipt")
        _require(
            value.get("schema_version") == schema
            and value.get("camera_id") == "logitech-overhead"
            and value.get("image_size_px") == [640, 480]
            and value.get("exact_mode") == _expected_exact_mode()
            and value.get("evaluator_owned") is True
            and value.get("self_scored") is False,
            "P8 camera receipt identity or ownership changed.",
        )
    _require(
        readiness.sha256_file(annotator_a_path)
        != readiness.sha256_file(annotator_b_path),
        "Independent annotation files are byte-identical.",
    )
    annotation_a = _load(annotator_a_path, "annotator A")
    annotation_b = _load(annotator_b_path, "annotator B")
    annotator_a, points_a = _validate_annotation(
        annotation_a,
        role="annotator_a",
        frame_sha256=capture["selected_frame_sha256"],
        capture_sha256=capture_sha,
    )
    annotator_b, points_b = _validate_annotation(
        annotation_b,
        role="annotator_b",
        frame_sha256=capture["selected_frame_sha256"],
        capture_sha256=capture_sha,
    )
    _require(annotator_a != annotator_b, "Annotator identities must be independent.")
    correspondences = []
    for point_id, fraction, quadrant in POINT_PLAN:
        correspondences.append(
            {
                "point_id": point_id,
                "board_xy_m": [
                    float(fraction[0]) * float(board["playing_side_m"]),
                    float(fraction[1]) * float(board["playing_side_m"]),
                ],
                "board_quadrant": quadrant,
                "source_frame_sha256": capture["selected_frame_sha256"],
                "synthetic": False,
                "annotations": [
                    {"annotator_id": annotator_a, "pixel_xy": points_a[point_id]},
                    {"annotator_id": annotator_b, "pixel_xy": points_b[point_id]},
                ],
            }
        )
    template = _load(
        readiness.DEFAULT_CONTRACT_PATH.parent
        / "current_100mm_metric_registration_inputs_v1.json",
        "metric registration template",
    )
    manifest = copy.deepcopy(template)
    manifest["input_id"] = (
        "stationary_workcell_registration_"
        + readiness.canonical_digest(
            {
                "capture": capture_sha,
                "annotation_a": readiness.sha256_file(annotator_a_path),
                "annotation_b": readiness.sha256_file(annotator_b_path),
                "board": board_sha,
                "survey": readiness.sha256_file(survey_path),
            }
        )[:16]
    )
    manifest["physical_source"] = {
        "observation_id": manifest["input_id"],
        "capture_receipt_path": _relative(capture_receipt_path, root),
        "capture_receipt_sha256": capture_sha,
        "overhead_video_path": capture["source_video_path"],
        "overhead_video_sha256": capture["source_video_sha256"],
        "source_frame_path": capture["selected_frame_path"],
        "source_frame_sha256": capture["selected_frame_sha256"],
        "source_frame_size_px": [640, 480],
        "frame_extraction_receipt": _pointer(extraction_path, root),
        "camera_id": "logitech-overhead",
        "camera_name": "C922 Pro Stream Webcam",
        "camera_role": "overhead_workspace",
        "capture_orientation_filter": "hflip,vflip",
        "proof_class": "physical_camera_frame",
        "exact_mode": capture["exact_mode"],
        "workspace_pose_id": WORKSPACE_POSE_ID,
        "board_pose_id": BOARD_POSE_ID,
    }
    manifest["metric_measurements"] = {
        "board_playing_side": _pointer(board_measurement_path, root),
        "camera_intrinsics_receipt": _pointer(intrinsics_path, root),
        "lens_distortion_receipt": _pointer(distortion_path, root),
        "board_correspondences": correspondences,
        "board_fit_evaluation": None,
        "object_keypoint_observations": [],
        "overhead_camera_to_workcell_transform": None,
        "wrist_camera_extrinsics": None,
        "board_to_workcell_survey": _pointer(survey_path, root),
    }
    _write(output, manifest)
    return {
        "status": "metric_registration_input_finalized",
        "manifest_path": str(output),
        "manifest_sha256": readiness.sha256_file(output),
        "point_count": len(correspondences),
        "annotator_ids": [annotator_a, annotator_b],
        "synthetic": False,
        "evaluator_owned": False,
        "physical_authority": False,
        "next_command": (
            "sim2claw workcell-registration --phase evaluate "
            f"--survey {survey_path} --manifest {output} --output <ignored-output>"
        ),
    }
