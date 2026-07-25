"""Evaluator-owned exact-mode C922 intrinsics and distortion calibration."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import cv2
import numpy as np
from PIL import Image


CONTRACT_SCHEMA = "sim2claw.c922_exact_mode_calibration_contract.v1"
INPUT_SCHEMA = "sim2claw.c922_exact_mode_calibration_inputs.v1"
FRAME_RECEIPT_SCHEMA = "sim2claw.c922_calibration_frame_receipt.v1"
EVALUATION_SCHEMA = "sim2claw.c922_exact_mode_calibration_evaluation.v1"
RECEIPT_SCHEMA = "sim2claw.c922_exact_mode_calibration_receipt.v1"
INTRINSICS_SCHEMA = "sim2claw.camera_intrinsics_receipt.v1"
DISTORTION_SCHEMA = "sim2claw.lens_distortion_receipt.v1"
CONTRACT_SHA256 = "d586d262929063c924895f56142dfe88196c521cb039d2392dc4ba53259b087c"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT_PATH = (
    REPO_ROOT / "configs/evaluations/c922_exact_mode_calibration_v1.json"
)
DEFAULT_INPUT_PATH = (
    REPO_ROOT / "configs/evaluations/c922_exact_mode_calibration_inputs_v1.json"
)
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "outputs/c922-exact-mode-calibration-v1"
CornerDetector = Callable[[Path, tuple[int, int], tuple[int, int]], np.ndarray | None]


class C922CalibrationError(RuntimeError):
    """A frozen contract, public input, or output identity is invalid."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise C922CalibrationError(f"Could not load {label}: {error}") from error
    if not isinstance(value, dict):
        raise C922CalibrationError(f"{label} must be an object.")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = _canonical_bytes(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise C922CalibrationError(
                f"Existing output is not byte-identical: {path}"
            )
        return
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise C922CalibrationError(message)


def _repo_path(declared: Any, label: str) -> Path:
    _require(isinstance(declared, str) and bool(declared), f"{label} path is missing.")
    path = (REPO_ROOT / declared).resolve()
    root = REPO_ROOT.resolve()
    _require(path != root and root in path.parents, f"{label} path escapes repository.")
    return path


def _finite(value: Any, *, positive: bool = False) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    number = float(value)
    return math.isfinite(number) and (number > 0.0 if positive else True)


def _camera_matches(value: Any, expected: Mapping[str, Any]) -> bool:
    if not isinstance(value, Mapping):
        return False
    keys = (
        "camera_id",
        "localized_name",
        "model_id",
        "unique_id",
        "image_size_px",
        "media_subtype",
        "format_index",
        "frame_rate_range_index",
        "frame_rate_fps",
        "orientation_filter",
    )
    return all(value.get(key) == expected.get(key) for key in keys)


def load_contract(path: Path = DEFAULT_CONTRACT_PATH) -> dict[str, Any]:
    _require(path.is_file(), "Calibration contract is missing.")
    _require(sha256_file(path) == CONTRACT_SHA256, "Calibration contract identity changed.")
    contract = _load_json(path, "calibration contract")
    _require(contract.get("schema_version") == CONTRACT_SCHEMA, "Contract schema changed.")
    _require(contract.get("status") == "preregistered", "Contract status changed.")
    target = contract.get("target")
    _require(isinstance(target, dict), "Target contract is missing.")
    asset = _repo_path(target.get("asset_path"), "target asset")
    _require(asset.is_file(), "Target asset is missing.")
    _require(sha256_file(asset) == target.get("asset_sha256"), "Target asset changed.")
    dataset = contract.get("dataset")
    _require(isinstance(dataset, dict), "Dataset contract is missing.")
    split_counts = dataset.get("required_split_counts")
    _require(
        split_counts == {"fit": 12, "validation": 3, "held_out": 3},
        "Required split counts changed.",
    )
    _require(
        dataset.get("minimum_accepted_frames") == sum(split_counts.values()),
        "Accepted-frame denominator changed.",
    )
    _require(
        contract.get("models", {}).get("candidates")
        == [
            "opencv_pinhole_zero_distortion",
            "opencv_pinhole_k1_k2_p1_p2_k3",
        ],
        "Model family changed.",
    )
    budgets = contract.get("budgets")
    _require(
        isinstance(budgets, dict)
        and budgets.get("dataset_evaluations_maximum") == 1
        and budgets.get("model_fits_maximum") == 2
        and all(
            budgets.get(name) == 0
            for name in (
                "camera_sessions_maximum",
                "new_camera_frames_maximum",
                "robot_motions_maximum",
                "simulator_replays_maximum",
                "provider_calls_maximum",
                "training_rows_maximum",
            )
        ),
        "Software-only budget changed.",
    )
    return contract


def load_inputs(
    path: Path = DEFAULT_INPUT_PATH,
    *,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = _load_json(path, "calibration input manifest")
    _require(manifest.get("schema_version") == INPUT_SCHEMA, "Input schema changed.")
    _require(
        _camera_matches(manifest.get("camera"), contract["camera"]),
        "Input camera or exact-mode identity changed.",
    )
    target = manifest.get("target")
    _require(
        isinstance(target, Mapping)
        and target.get("asset_path") == contract["target"]["asset_path"]
        and target.get("asset_sha256") == contract["target"]["asset_sha256"],
        "Input target identity changed.",
    )
    _require(
        manifest.get("splits_frozen_before_fit") is True,
        "Input splits were not frozen before fitting.",
    )
    frames = manifest.get("frames")
    _require(isinstance(frames, list), "Input frames must be a list.")
    _require(
        len(frames) <= int(contract["dataset"]["maximum_declared_frames"]),
        "Declared-frame budget exceeded.",
    )
    return manifest


def _load_frame(
    declaration: Any,
    *,
    contract: Mapping[str, Any],
    expected_focus_setting: Any,
) -> tuple[dict[str, Any], Path, str]:
    _require(isinstance(declaration, Mapping), "Frame declaration must be an object.")
    _require(
        set(declaration) == {"frame_id", "split", "receipt_path", "receipt_sha256"},
        "Frame declaration contains substituted or caller-result fields.",
    )
    _require(
        isinstance(declaration.get("frame_id"), str) and bool(declaration["frame_id"]),
        "Frame ID is missing.",
    )
    _require(
        declaration.get("split") in {"fit", "validation", "held_out"},
        "Frame split is invalid.",
    )
    receipt_path = _repo_path(declaration.get("receipt_path"), "frame receipt")
    _require(receipt_path.is_file(), "Frame receipt is missing.")
    _require(
        isinstance(declaration.get("receipt_sha256"), str)
        and sha256_file(receipt_path) == declaration["receipt_sha256"],
        "Frame receipt identity changed.",
    )
    receipt = _load_json(receipt_path, "frame receipt")
    _require(receipt.get("schema_version") == FRAME_RECEIPT_SCHEMA, "Frame receipt schema changed.")
    _require(
        receipt.get("frame_id") == declaration["frame_id"]
        and receipt.get("split") == declaration["split"],
        "Frame declaration and receipt disagree.",
    )
    _require(
        _camera_matches(receipt.get("camera"), contract["camera"]),
        "Frame camera or exact-mode identity changed.",
    )
    _require(
        receipt.get("focus_setting") == expected_focus_setting,
        "Frame focus setting changed within the dataset.",
    )
    _require(receipt.get("caller_supplied_corners") is None, "Caller-supplied corners are forbidden.")
    _require(
        receipt.get("capture_authority") == "physical_camera_frame"
        and receipt.get("synthetic") is False,
        "Frame proof class is not physical camera evidence.",
    )
    _require(
        _finite(receipt.get("source_pts_seconds"))
        and float(receipt["source_pts_seconds"]) >= 0.0,
        "Frame source PTS is invalid.",
    )
    image_path = _repo_path(receipt.get("image_path"), "frame image")
    _require(image_path.is_file(), "Frame image is missing.")
    image_sha = sha256_file(image_path)
    _require(image_sha == receipt.get("image_sha256"), "Frame image identity changed.")
    return receipt, image_path, image_sha


def detect_corners(
    image_path: Path,
    inner_corners: tuple[int, int],
    expected_size: tuple[int, int],
) -> np.ndarray | None:
    """Detect public-image corners; caller annotations are never accepted."""

    try:
        with Image.open(image_path) as image:
            _require(image.size == expected_size, "Frame dimensions changed.")
            image.verify()
    except C922CalibrationError:
        raise
    except Exception as error:
        raise C922CalibrationError(f"Frame image is malformed: {error}") from error
    gray = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    _require(gray is not None, "Frame decoder returned no pixels.")
    found, corners = cv2.findChessboardCorners(
        gray,
        inner_corners,
        flags=cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE,
    )
    if not found or corners is None:
        return None
    expected = inner_corners[0] * inner_corners[1]
    _require(len(corners) == expected, "Detected corner count changed.")
    refined = cv2.cornerSubPix(
        gray,
        corners.astype(np.float32),
        (5, 5),
        (-1, -1),
        (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 40, 1e-4),
    )
    _require(refined is not None and np.all(np.isfinite(refined)), "Detected corners are non-finite.")
    return refined.reshape(-1, 2).astype(np.float32)


def _centroid_bin(x: float, y: float) -> str:
    horizontal = "west" if x < 1 / 3 else "east" if x > 2 / 3 else "center"
    vertical = "north" if y < 1 / 3 else "south" if y > 2 / 3 else "center"
    return "center" if horizontal == vertical == "center" else f"{vertical}_{horizontal}"


def frame_geometry(
    corners: np.ndarray,
    *,
    image_size: tuple[int, int],
    inner_corners: tuple[int, int],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    columns, rows = inner_corners
    _require(corners.shape == (columns * rows, 2), "Corner geometry shape changed.")
    width, height = image_size
    _require(np.all(np.isfinite(corners)), "Detected corners are non-finite.")
    _require(
        bool(
            np.all(corners[:, 0] >= 0.0)
            and np.all(corners[:, 0] < width)
            and np.all(corners[:, 1] >= 0.0)
            and np.all(corners[:, 1] < height)
        ),
        "Detected corners fall outside the image.",
    )
    hull_fraction = float(cv2.contourArea(cv2.convexHull(corners))) / float(width * height)
    centroid = np.mean(corners, axis=0)
    top_left, top_right = corners[0], corners[columns - 1]
    bottom_left, bottom_right = corners[(rows - 1) * columns], corners[-1]
    edge_lengths = (
        float(np.linalg.norm(top_right - top_left)),
        float(np.linalg.norm(bottom_right - bottom_left)),
        float(np.linalg.norm(bottom_left - top_left)),
        float(np.linalg.norm(bottom_right - top_right)),
    )
    _require(min(edge_lengths) > 0.0, "Detected grid edge is degenerate.")
    top, bottom, left, right = edge_lengths
    edge_log_ratio = max(abs(math.log(top / bottom)), abs(math.log(left / right)))
    angle = math.degrees(
        math.atan2(
            float(top_right[1] - top_left[1]),
            float(top_right[0] - top_left[0]),
        )
    )
    dataset = contract["dataset"]
    scale_low, scale_high = dataset["scale_bin_board_hull_fraction"]
    angle_low, angle_high = dataset["orientation_bin_degrees"]
    scale_bin = "small" if hull_fraction < scale_low else "large" if hull_fraction > scale_high else "medium"
    orientation_bin = "negative" if angle < angle_low else "positive" if angle > angle_high else "neutral"
    x_fraction, y_fraction = float(centroid[0] / width), float(centroid[1] / height)
    return {
        "centroid_fraction": [x_fraction, y_fraction],
        "centroid_bin": _centroid_bin(x_fraction, y_fraction),
        "board_hull_fraction": hull_fraction,
        "scale_bin": scale_bin,
        "edge_log_ratio": edge_log_ratio,
        "tilted_view": edge_log_ratio >= dataset["tilted_view_minimum_edge_log_ratio"],
        "near_frontal_view": edge_log_ratio <= dataset["near_frontal_maximum_edge_log_ratio"],
        "row_angle_degrees": angle,
        "orientation_bin": orientation_bin,
    }


def _object_points(inner_corners: tuple[int, int]) -> np.ndarray:
    columns, rows = inner_corners
    points = np.zeros((columns * rows, 3), np.float32)
    points[:, :2] = np.mgrid[0:columns, 0:rows].T.reshape(-1, 2)
    return points


def _fit_model(
    model_id: str,
    frames: Sequence[Mapping[str, Any]],
    *,
    image_size: tuple[int, int],
    object_points: np.ndarray,
) -> dict[str, Any]:
    if model_id == "opencv_pinhole_zero_distortion":
        flags = (
            cv2.CALIB_ZERO_TANGENT_DIST
            | cv2.CALIB_FIX_K1
            | cv2.CALIB_FIX_K2
            | cv2.CALIB_FIX_K3
            | cv2.CALIB_FIX_K4
            | cv2.CALIB_FIX_K5
            | cv2.CALIB_FIX_K6
        )
    elif model_id == "opencv_pinhole_k1_k2_p1_p2_k3":
        flags = cv2.CALIB_FIX_K4 | cv2.CALIB_FIX_K5 | cv2.CALIB_FIX_K6
    else:
        raise C922CalibrationError(f"Unknown model {model_id}.")
    rms, matrix, distortion, _, _ = cv2.calibrateCamera(
        [object_points for _ in frames],
        [np.asarray(row["_corners"], dtype=np.float32) for row in frames],
        image_size,
        None,
        None,
        flags=flags,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-12),
    )
    _require(
        math.isfinite(float(rms))
        and np.all(np.isfinite(matrix))
        and np.all(np.isfinite(distortion)),
        "Calibration fit produced non-finite values.",
    )
    return {
        "model_id": model_id,
        "opencv_fit_rms_px": float(rms),
        "camera_matrix": matrix.astype(np.float64),
        "distortion": distortion.reshape(-1).astype(np.float64),
    }


def _score_frames(
    model: Mapping[str, Any],
    frames: Sequence[Mapping[str, Any]],
    *,
    object_points: np.ndarray,
) -> dict[str, Any]:
    matrix = np.asarray(model["camera_matrix"], dtype=np.float64)
    distortion = np.asarray(model["distortion"], dtype=np.float64)
    all_errors: list[float] = []
    per_frame: list[dict[str, Any]] = []
    for row in frames:
        corners = np.asarray(row["_corners"], dtype=np.float32)
        solved, rvec, tvec = cv2.solvePnP(
            object_points,
            corners,
            matrix,
            distortion,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        _require(bool(solved), f"PnP failed for frame {row['frame_id']}.")
        projected, _ = cv2.projectPoints(object_points, rvec, tvec, matrix, distortion)
        errors = np.linalg.norm(projected.reshape(-1, 2) - corners, axis=1)
        _require(np.all(np.isfinite(errors)), "Reprojection errors are non-finite.")
        all_errors.extend(float(value) for value in errors)
        per_frame.append(
            {
                "frame_id": row["frame_id"],
                "frame_sha256": row["image_sha256"],
                "rms_px": float(np.sqrt(np.mean(np.square(errors)))),
                "maximum_px": float(np.max(errors)),
            }
        )
    values = np.asarray(all_errors, dtype=np.float64)
    return {
        "frame_count": len(frames),
        "point_count": len(all_errors),
        "rms_px": float(np.sqrt(np.mean(np.square(values)))),
        "maximum_px": float(np.max(values)),
        "per_frame": per_frame,
    }


def _public_frame(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def _evaluate_manifest(
    contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    input_sha256: str,
    detector: CornerDetector,
) -> dict[str, Any]:
    camera = contract["camera"]
    expected_size = tuple(int(value) for value in camera["image_size_px"])
    inner = tuple(int(value) for value in contract["target"]["inner_corners"])
    rows: list[dict[str, Any]] = []
    invalid: list[dict[str, str]] = []
    frame_ids: set[str] = set()
    image_hashes: set[str] = set()
    focus = manifest["camera"].get("focus_setting")
    for declaration in manifest["frames"]:
        frame_id = (
            str(declaration.get("frame_id"))
            if isinstance(declaration, Mapping)
            else "<invalid>"
        )
        try:
            receipt, image_path, image_sha = _load_frame(
                declaration,
                contract=contract,
                expected_focus_setting=focus,
            )
            _require(receipt["frame_id"] not in frame_ids, "Duplicate frame ID.")
            _require(image_sha not in image_hashes, "Duplicate/replayed frame bytes.")
            frame_ids.add(receipt["frame_id"])
            image_hashes.add(image_sha)
            corners = detector(image_path, inner, expected_size)
            if corners is None:
                invalid.append({"frame_id": frame_id, "reason": "checkerboard_not_detected"})
                continue
            geometry = frame_geometry(
                corners,
                image_size=expected_size,
                inner_corners=inner,
                contract=contract,
            )
            rows.append(
                {
                    "frame_id": receipt["frame_id"],
                    "split": receipt["split"],
                    "image_path": receipt["image_path"],
                    "image_sha256": image_sha,
                    "source_pts_seconds": float(receipt["source_pts_seconds"]),
                    "receipt_sha256": declaration["receipt_sha256"],
                    "geometry": geometry,
                    "_corners": corners,
                }
            )
        except C922CalibrationError as error:
            invalid.append({"frame_id": frame_id, "reason": str(error)})
    split_counts = {
        split: sum(row["split"] == split for row in rows)
        for split in ("fit", "validation", "held_out")
    }
    centroid_bins = sorted({row["geometry"]["centroid_bin"] for row in rows})
    scale_bins = sorted({row["geometry"]["scale_bin"] for row in rows})
    orientation_bins = sorted({row["geometry"]["orientation_bin"] for row in rows})
    tilted = sum(bool(row["geometry"]["tilted_view"]) for row in rows)
    near_frontal = sum(bool(row["geometry"]["near_frontal_view"]) for row in rows)
    dataset = contract["dataset"]
    missing: list[str] = []
    if not isinstance(focus, (str, int, float)) or isinstance(focus, bool) or focus == "":
        missing.append("constant_focus_setting")
    if len(rows) < dataset["minimum_accepted_frames"]:
        missing.append("minimum_accepted_frames")
    for split, required in dataset["required_split_counts"].items():
        if split_counts[split] != required:
            missing.append(f"{split}_split_count")
    if not set(dataset["required_centroid_bins"]).issubset(centroid_bins):
        missing.append("required_centroid_bins")
    if len(scale_bins) < dataset["minimum_scale_bins"]:
        missing.append("minimum_scale_bins")
    if tilted < dataset["minimum_tilted_views"]:
        missing.append("minimum_tilted_views")
    if near_frontal < dataset["minimum_near_frontal_views"]:
        missing.append("minimum_near_frontal_views")
    if len(orientation_bins) < dataset["minimum_orientation_bins"]:
        missing.append("minimum_orientation_bins")
    readiness = {
        "declared_frame_count": len(manifest["frames"]),
        "accepted_frame_count": len(rows),
        "rejected_frame_count": len(invalid),
        "split_counts": split_counts,
        "centroid_bins": centroid_bins,
        "scale_bins": scale_bins,
        "orientation_bins": orientation_bins,
        "tilted_view_count": tilted,
        "near_frontal_view_count": near_frontal,
        "missing_prerequisites": sorted(set(missing)),
        "rejected_frames": invalid,
    }
    evaluation: dict[str, Any] = {
        "schema_version": EVALUATION_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": CONTRACT_SHA256,
        "input_sha256": input_sha256,
        "input_digest": canonical_digest(manifest),
        "evaluator": {
            "path": str(Path(__file__).relative_to(REPO_ROOT)),
            "sha256": sha256_file(Path(__file__)),
            "opencv_version": cv2.__version__,
            "corner_owner": "evaluator",
            "caller_supplied_corners_used": False,
        },
        "readiness": readiness,
        "frames": [_public_frame(row) for row in rows],
        "model_budget": {"maximum": contract["budgets"]["model_fits_maximum"], "used": 0},
        "selected_model": None,
        "fit_metrics": None,
        "validation_metrics": None,
        "held_out_metrics": None,
        "gates": [],
        "authority": contract["authority"],
    }
    if invalid:
        evaluation.update(
            verdict=contract["outputs"]["failed_verdict"],
            reason="one_or_more_declared_frames_invalid_or_rejected",
        )
        return evaluation
    if missing:
        evaluation.update(
            verdict=contract["outputs"]["not_ready_verdict"],
            reason="required_dataset_or_focus_prerequisites_missing",
        )
        return evaluation

    object_points = _object_points(inner)
    fit_rows = [row for row in rows if row["split"] == "fit"]
    validation_rows = [row for row in rows if row["split"] == "validation"]
    held_out_rows = [row for row in rows if row["split"] == "held_out"]
    candidates: list[dict[str, Any]] = []
    for model_id in contract["models"]["candidates"]:
        model = _fit_model(
            model_id,
            fit_rows,
            image_size=expected_size,
            object_points=object_points,
        )
        model["validation_metrics"] = _score_frames(
            model,
            validation_rows,
            object_points=object_points,
        )
        candidates.append(model)
    evaluation["model_budget"]["used"] = len(candidates)
    zero, distorted = candidates
    improvement = (
        zero["validation_metrics"]["rms_px"]
        - distorted["validation_metrics"]["rms_px"]
    )
    selected = (
        distorted
        if improvement
        >= contract["models"][
            "minimum_validation_rms_improvement_px_for_distortion_model"
        ]
        else zero
    )
    # Held-out bytes become score inputs only after the selected object is fixed.
    fit_metrics = _score_frames(selected, fit_rows, object_points=object_points)
    held_out_metrics = _score_frames(selected, held_out_rows, object_points=object_points)
    matrix = np.asarray(selected["camera_matrix"], dtype=np.float64)
    fx, fy = float(matrix[0, 0]), float(matrix[1, 1])
    cx, cy = float(matrix[0, 2]), float(matrix[1, 2])
    width, height = expected_size
    limits = contract["acceptance"]
    gates = [
        ("fit_rms", fit_metrics["rms_px"] <= limits["maximum_fit_rms_px"]),
        ("validation_rms", selected["validation_metrics"]["rms_px"] <= limits["maximum_validation_rms_px"]),
        ("held_out_rms", held_out_metrics["rms_px"] <= limits["maximum_held_out_rms_px"]),
        ("held_out_maximum", held_out_metrics["maximum_px"] <= limits["maximum_held_out_point_error_px"]),
        (
            "focal_bounds",
            limits["minimum_focal_length_px"] <= fx <= limits["maximum_focal_length_px"]
            and limits["minimum_focal_length_px"] <= fy <= limits["maximum_focal_length_px"],
        ),
        ("focal_aspect", limits["minimum_focal_aspect_ratio"] <= fx / fy <= limits["maximum_focal_aspect_ratio"]),
        (
            "principal_point_x",
            limits["principal_point_x_fraction_bounds"][0]
            <= cx / width
            <= limits["principal_point_x_fraction_bounds"][1],
        ),
        (
            "principal_point_y",
            limits["principal_point_y_fraction_bounds"][0]
            <= cy / height
            <= limits["principal_point_y_fraction_bounds"][1],
        ),
    ]
    evaluation["selected_model"] = {
        "model_id": selected["model_id"],
        "validation_rms_improvement_px_for_distortion_model": float(improvement),
        "camera_matrix": matrix.tolist(),
        "distortion_coefficients": np.asarray(selected["distortion"], dtype=np.float64).tolist(),
    }
    evaluation["fit_metrics"] = fit_metrics
    evaluation["validation_metrics"] = selected["validation_metrics"]
    evaluation["held_out_metrics"] = held_out_metrics
    evaluation["gates"] = [{"gate": name, "passed": bool(value)} for name, value in gates]
    passed = all(value for _, value in gates)
    evaluation.update(
        verdict=(
            contract["outputs"]["pass_verdict"]
            if passed
            else contract["outputs"]["failed_verdict"]
        ),
        reason=(
            "all_preregistered_calibration_gates_passed"
            if passed
            else "one_or_more_calibration_gates_failed"
        ),
    )
    return evaluation


def evaluate_manifest(
    contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    input_sha256: str,
) -> dict[str, Any]:
    """Evaluate public inputs with the evaluator-owned corner detector."""

    return _evaluate_manifest(
        contract,
        manifest,
        input_sha256=input_sha256,
        detector=detect_corners,
    )


def _receipt_digest(value: Mapping[str, Any]) -> str:
    return canonical_digest(
        {key: item for key, item in value.items() if key != "receipt_digest"}
    )


def materialize(
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    input_path: Path = DEFAULT_INPUT_PATH,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    manifest = load_inputs(input_path, contract=contract)
    input_sha = sha256_file(input_path)
    evaluation = evaluate_manifest(contract, manifest, input_sha256=input_sha)
    key = canonical_digest(
        {
            "contract_sha256": CONTRACT_SHA256,
            "input_sha256": input_sha,
            "evaluator_sha256": evaluation["evaluator"]["sha256"],
        }
    )
    root = (output_root / key).resolve()
    repo = REPO_ROOT.resolve()
    _require(root != repo and repo in root.parents, "Output root escapes repository.")
    evaluation_path = root / "evaluation.json"
    _write_json(evaluation_path, evaluation)
    result: dict[str, Any] = {
        "verdict": evaluation["verdict"],
        "output_root": str(root),
        "evaluation_path": str(evaluation_path),
        "evaluation_sha256": sha256_file(evaluation_path),
        "receipt_path": None,
        "intrinsics_path": None,
        "distortion_path": None,
    }
    if evaluation["verdict"] != contract["outputs"]["pass_verdict"]:
        for name in (
            "receipt.json",
            "camera_intrinsics_receipt.json",
            "lens_distortion_receipt.json",
        ):
            _require(
                not (root / name).exists(),
                f"Non-pass output contains stale calibration artifact: {name}",
            )
        return result

    selected = evaluation["selected_model"]
    common = {
        "camera_id": contract["camera"]["camera_id"],
        "image_size_px": contract["camera"]["image_size_px"],
        "exact_mode": {
            key: contract["camera"][key]
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
        },
        "dataset_id": manifest["dataset_id"],
        "dataset_input_sha256": input_sha,
        "source_frame_sha256s": sorted(
            row["image_sha256"] for row in evaluation["frames"]
        ),
        "selected_model": selected["model_id"],
        "fit_metrics": evaluation["fit_metrics"],
        "validation_metrics": evaluation["validation_metrics"],
        "held_out_metrics": evaluation["held_out_metrics"],
        "contract_sha256": CONTRACT_SHA256,
        "evaluator_identity": evaluation["evaluator"],
        "evaluator_owned": True,
        "self_scored": False,
        "metric_scale_claimed": False,
        "camera_to_workcell_extrinsics_claimed": False,
    }
    intrinsics = {
        "schema_version": INTRINSICS_SCHEMA,
        **common,
        "camera_matrix": selected["camera_matrix"],
    }
    distortion = {
        "schema_version": DISTORTION_SCHEMA,
        **common,
        "model": selected["model_id"],
        "coefficients": selected["distortion_coefficients"],
    }
    intrinsics_path = root / "camera_intrinsics_receipt.json"
    distortion_path = root / "lens_distortion_receipt.json"
    _write_json(intrinsics_path, intrinsics)
    _write_json(distortion_path, distortion)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "verdict": evaluation["verdict"],
        "contract_sha256": CONTRACT_SHA256,
        "input_sha256": input_sha,
        "evaluation_sha256": sha256_file(evaluation_path),
        "intrinsics_sha256": sha256_file(intrinsics_path),
        "distortion_sha256": sha256_file(distortion_path),
        "accepted_frame_count": evaluation["readiness"]["accepted_frame_count"],
        "split_counts": evaluation["readiness"]["split_counts"],
        "model_fits_used": evaluation["model_budget"]["used"],
        "camera_sessions_used": 0,
        "new_camera_frames_used": 0,
        "robot_motions_used": 0,
        "simulator_replays_used": 0,
        "provider_calls_used": 0,
        "training_rows_used": 0,
        "authority": contract["authority"],
    }
    receipt["receipt_digest"] = _receipt_digest(receipt)
    receipt_path = root / "receipt.json"
    _write_json(receipt_path, receipt)
    result.update(
        receipt_path=str(receipt_path),
        receipt_sha256=sha256_file(receipt_path),
        intrinsics_path=str(intrinsics_path),
        intrinsics_sha256=sha256_file(intrinsics_path),
        distortion_path=str(distortion_path),
        distortion_sha256=sha256_file(distortion_path),
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args(argv)
    print(
        json.dumps(
            materialize(args.contract, args.inputs, args.output_root),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
