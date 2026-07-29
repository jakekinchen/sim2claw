"""RP04N source-frame preparation and frozen crown-track evaluation."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .bidirectional_registration_v2_fit import project
from .current_workcell import current_square_center
from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .paths import REPO_ROOT


SCHEMA = "sim2claw.rp04n_c922_crown_track.v1"
ANNOTATION_SCHEMA = "sim2claw.rp04n_c922_crown_annotations.v1"
PREPARE_SCHEMA = "sim2claw.rp04n_c922_crown_prepare_receipt.v1"
RECEIPT_SCHEMA = "sim2claw.rp04n_c922_crown_track_receipt.v1"
CONTRACT_PATH = (
    REPO_ROOT / "configs" / "evaluations" / "rp04n_c922_crown_track_v1.json"
)
OUTPUT_DIRECTORY = REPO_ROOT / "outputs" / "rp04n_c922_crown_track_v1"


def _require_hash(root: Path, path: str, expected: str, label: str) -> None:
    candidate = root / path
    if (
        not candidate.is_file()
        or len(expected) != 64
        or sha256_file(candidate) != expected
    ):
        raise FactoryArtifactError(f"{label} hash rejected: {candidate}")


def load_contract(
    path: Path = CONTRACT_PATH,
    *,
    root: Path = REPO_ROOT,
    require_annotations: bool = False,
) -> dict[str, Any]:
    contract = load_json_object(path, label="RP04N contract")
    if contract.get("schema_version") != SCHEMA:
        raise FactoryArtifactError("unsupported RP04N contract")
    source = contract.get("source")
    simulator = contract.get("simulator_reference")
    projection = contract.get("projection")
    annotation = contract.get("annotation")
    if not all(
        isinstance(value, dict)
        for value in (source, simulator, projection, annotation)
    ):
        raise FactoryArtifactError("RP04N contract is incomplete")
    _require_hash(
        root, source["samples_path"], source["samples_sha256"], "source samples"
    )
    _require_hash(
        root, source["video_path"], source["video_sha256"], "source video"
    )
    _require_hash(
        root,
        simulator["rp04k_closeout_path"],
        simulator["rp04k_closeout_sha256"],
        "RP04K closeout",
    )
    _require_hash(
        root, simulator["trace_path"], simulator["trace_sha256"], "RP04K trace"
    )
    _require_hash(
        root,
        projection["candidate_path"],
        projection["candidate_sha256"],
        "projection candidate",
    )
    _require_hash(
        root,
        projection["current_workcell_path"],
        projection["current_workcell_sha256"],
        "current workcell",
    )
    indices = source["sample_indices"]
    if (
        len(indices) != 18
        or indices != sorted(indices)
        or set(annotation["pass_a_sample_order"]) != set(indices)
        or set(annotation["pass_b_sample_order"]) != set(indices)
    ):
        raise FactoryArtifactError("RP04N sample or pass order changed")
    if annotation["pass_a_sample_order"] == annotation["pass_b_sample_order"]:
        raise FactoryArtifactError("RP04N annotation orders are not independent")
    if annotation.get(
        "simulator_pixel_projection_hidden_until_both_passes_frozen"
    ) is not True:
        raise FactoryArtifactError("RP04N source-only annotation boundary widened")
    forbidden = contract.get("forbidden")
    if not isinstance(forbidden, dict) or not all(forbidden.values()):
        raise FactoryArtifactError("RP04N forbidden operation was enabled")
    authority = contract.get("authority")
    if not isinstance(authority, dict) or any(authority.values()):
        raise FactoryArtifactError("RP04N authority widened")
    if require_annotations:
        for name in ("pass_a_path", "pass_b_path"):
            if not (root / annotation[name]).is_file():
                raise FactoryArtifactError("both annotation passes must be frozen")
    return contract


def _load_rows(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as error:
        raise FactoryArtifactError(f"cannot read RP04N samples: {error}") from error
    if not rows:
        raise FactoryArtifactError("RP04N source samples are empty")
    return rows


def _png_bytes(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise FactoryArtifactError("cannot encode RP04N frame")
    return encoded.tobytes()


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _read_frame(
    capture: cv2.VideoCapture, frame_index: int, *, rotate_180: bool
) -> np.ndarray:
    if not capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index):
        raise FactoryArtifactError(f"cannot seek RP04N frame {frame_index}")
    ok, frame = capture.read()
    if not ok or frame is None:
        raise FactoryArtifactError(f"cannot decode RP04N frame {frame_index}")
    return cv2.rotate(frame, cv2.ROTATE_180) if rotate_180 else frame


def _sheet(images: list[tuple[str, np.ndarray]]) -> np.ndarray:
    tiles = []
    for code, image in images:
        tile = image.copy()
        cv2.rectangle(tile, (0, 0), (90, 30), (255, 255, 255), -1)
        cv2.putText(
            tile,
            code,
            (8, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )
        tiles.append(cv2.resize(tile, (320, 240)))
    rows = [
        np.concatenate(tiles[index : index + 3], axis=1)
        for index in range(0, len(tiles), 3)
    ]
    return np.concatenate(rows, axis=0)


def prepare_source_frames(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_contract(contract_path, root=root)
    source = contract["source"]
    rows = _load_rows(root / source["samples_path"])
    capture = cv2.VideoCapture(str(root / source["video_path"]))
    if not capture.isOpened():
        raise FactoryArtifactError("cannot open RP04N C922 video")
    try:
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if (
            frame_count != int(source["expected_video_frame_count"])
            or not math.isfinite(fps)
            or fps <= 0.0
        ):
            raise FactoryArtifactError("RP04N video metadata changed")
        rotate = int(source["rotation_degrees"]) == 180
        source_frames: dict[int, tuple[int, np.ndarray]] = {}
        for sample_index in source["sample_indices"]:
            row = rows[sample_index]
            if row.get("sample_index") != sample_index:
                raise FactoryArtifactError("RP04N source sample index changed")
            video_time = float(row["overhead_video_time_seconds"])
            frame_index = int(round(video_time * fps))
            if not 0 <= frame_index < frame_count:
                raise FactoryArtifactError("RP04N selected frame is out of range")
            source_frames[sample_index] = (
                frame_index,
                _read_frame(capture, frame_index, rotate_180=rotate),
            )
        anchor_image = _read_frame(
            capture,
            int(source["anchor_frame_index_zero_based"]),
            rotate_180=rotate,
        )
    finally:
        capture.release()

    manifest_rows = []
    anchor_path = output_directory / "anchor.png"
    _write_bytes(anchor_path, _png_bytes(anchor_image))
    for sample_index in source["sample_indices"]:
        frame_index, image = source_frames[sample_index]
        path = output_directory / "frames" / f"sample-{sample_index:03d}.png"
        _write_bytes(path, _png_bytes(image))
        manifest_rows.append(
            {
                "sample_index": sample_index,
                "video_frame_index": frame_index,
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
            }
        )
    pass_manifests = {}
    for pass_name, order_key in (
        ("pass_a", "pass_a_sample_order"),
        ("pass_b", "pass_b_sample_order"),
    ):
        order = contract["annotation"][order_key]
        coded = []
        mapping = []
        for position, sample_index in enumerate(order, start=1):
            code = f"{pass_name[-1].upper()}{position:02d}"
            coded.append((code, source_frames[sample_index][1]))
            mapping.append({"code": code, "sample_index": sample_index})
        sheet = _sheet(coded)
        sheet_path = output_directory / f"{pass_name}_sheet.png"
        _write_bytes(sheet_path, _png_bytes(sheet))
        pass_manifests[pass_name] = {
            "mapping": mapping,
            "sheet_path": sheet_path.relative_to(root).as_posix(),
            "sheet_sha256": sha256_file(sheet_path),
        }
    unsigned = {
        "schema_version": PREPARE_SCHEMA,
        "contract_sha256": sha256_file(contract_path),
        "video_frame_count": frame_count,
        "video_fps": fps,
        "anchor": {
            "frame_index": source["anchor_frame_index_zero_based"],
            "path": anchor_path.relative_to(root).as_posix(),
            "sha256": sha256_file(anchor_path),
        },
        "frames": manifest_rows,
        "passes": pass_manifests,
        "simulator_projection_opened": False,
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_directory / "prepare_receipt.json", receipt)
    return receipt


def validate_annotations(
    annotation: dict[str, Any],
    *,
    pass_name: str,
    expected_order: list[int],
) -> dict[int, dict[str, Any]]:
    if (
        annotation.get("schema_version") != ANNOTATION_SCHEMA
        or annotation.get("pass") != pass_name
        or annotation.get("simulator_projection_visible_during_annotation")
        is not False
    ):
        raise FactoryArtifactError(f"invalid RP04N {pass_name} annotation")
    rows = annotation.get("rows")
    if not isinstance(rows, list) or len(rows) != len(expected_order) + 1:
        raise FactoryArtifactError(f"RP04N {pass_name} row count changed")
    if rows[0].get("kind") != "anchor":
        raise FactoryArtifactError(f"RP04N {pass_name} anchor is missing")
    by_sample: dict[int, dict[str, Any]] = {}
    observed_order = []
    for row in rows[1:]:
        sample_index = int(row.get("sample_index", -1))
        observed_order.append(sample_index)
        by_sample[sample_index] = row
    if observed_order != expected_order or len(by_sample) != len(expected_order):
        raise FactoryArtifactError(f"RP04N {pass_name} order changed")
    for row in rows:
        visibility = row.get("visibility")
        point = row.get("crown_center_px")
        if visibility not in {"visible", "occluded", "unusable"}:
            raise FactoryArtifactError("RP04N visibility label is invalid")
        if visibility == "visible":
            array = np.asarray(point, dtype=np.float64)
            if array.shape != (2,) or not np.isfinite(array).all():
                raise FactoryArtifactError("visible RP04N point is invalid")
        elif point is not None:
            raise FactoryArtifactError("invalid RP04N point must be null")
    return by_sample


def discrete_frechet(left: np.ndarray, right: np.ndarray) -> float:
    if (
        left.ndim != 2
        or right.ndim != 2
        or left.shape[1:] != (2,)
        or right.shape[1:] != (2,)
        or not len(left)
        or not len(right)
    ):
        raise FactoryArtifactError("ordered curves must be nonempty Nx2 arrays")
    cache = np.full((len(left), len(right)), np.nan, dtype=np.float64)
    for i in range(len(left)):
        for j in range(len(right)):
            distance = float(np.linalg.norm(left[i] - right[j]))
            if i == 0 and j == 0:
                cache[i, j] = distance
            elif i == 0:
                cache[i, j] = max(cache[i, j - 1], distance)
            elif j == 0:
                cache[i, j] = max(cache[i - 1, j], distance)
            else:
                cache[i, j] = max(
                    min(cache[i - 1, j], cache[i - 1, j - 1], cache[i, j - 1]),
                    distance,
                )
    return float(cache[-1, -1])


def _correct_and_project(
    positions: np.ndarray, candidate: dict[str, Any]
) -> np.ndarray:
    yaw = float(candidate["robot_board_yaw_radians"])
    cosine, sine = math.cos(yaw), math.sin(yaw)
    rotation = np.asarray(
        [[cosine, -sine, 0.0], [sine, cosine, 0.0], [0.0, 0.0, 1.0]]
    )
    corrected = (
        positions @ rotation.T
        + np.asarray(candidate["robot_board_translation_xyz_m"], dtype=np.float64)
    )
    return project(
        np.asarray(candidate["camera_matrix_3x4"], dtype=np.float64), corrected
    )


def evaluate(
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_DIRECTORY / "receipt.json",
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_contract(
        contract_path, root=root, require_annotations=True
    )
    annotation_spec = contract["annotation"]
    pass_a_path = root / annotation_spec["pass_a_path"]
    pass_b_path = root / annotation_spec["pass_b_path"]
    pass_a = load_json_object(pass_a_path, label="RP04N pass A")
    pass_b = load_json_object(pass_b_path, label="RP04N pass B")
    a_by_sample = validate_annotations(
        pass_a,
        pass_name="pass_a",
        expected_order=annotation_spec["pass_a_sample_order"],
    )
    b_by_sample = validate_annotations(
        pass_b,
        pass_name="pass_b",
        expected_order=annotation_spec["pass_b_sample_order"],
    )
    anchor_a = np.asarray(pass_a["rows"][0]["crown_center_px"], dtype=np.float64)
    anchor_b = np.asarray(pass_b["rows"][0]["crown_center_px"], dtype=np.float64)
    anchor_disagreement = float(np.linalg.norm(anchor_a - anchor_b))
    indices = contract["source"]["sample_indices"]
    admitted_indices = []
    physical_points = []
    disagreements = {}
    validity = []
    for sample_index in indices:
        left = a_by_sample[sample_index]
        right = b_by_sample[sample_index]
        admitted = (
            left["visibility"] == "visible"
            and right["visibility"] == "visible"
        )
        validity.append(admitted)
        if not admitted:
            continue
        left_point = np.asarray(left["crown_center_px"], dtype=np.float64)
        right_point = np.asarray(right["crown_center_px"], dtype=np.float64)
        disagreement = float(np.linalg.norm(left_point - right_point))
        disagreements[str(sample_index)] = disagreement
        if disagreement <= float(
            contract["gates"]["carry_two_pass_disagreement_max_px"]
        ):
            admitted_indices.append(sample_index)
            physical_points.append((left_point + right_point) / 2.0)
        else:
            validity[-1] = False
    maximum_invalid_run = 0
    current_invalid_run = 0
    for valid in validity:
        current_invalid_run = 0 if valid else current_invalid_run + 1
        maximum_invalid_run = max(maximum_invalid_run, current_invalid_run)
    tercile_counts = [
        sum(index in admitted_indices for index in indices[start : start + 6])
        for start in (0, 6, 12)
    ]
    coverage_gates = {
        "anchor_agreement": anchor_disagreement
        <= float(contract["gates"]["anchor_two_pass_disagreement_max_px"]),
        "minimum_visible": len(admitted_indices)
        >= int(contract["gates"]["minimum_admitted_visible_points"]),
        "temporal_terciles": min(tercile_counts, default=0)
        >= int(contract["gates"]["minimum_visible_points_per_temporal_tercile"]),
        "consecutive_invalid": maximum_invalid_run
        <= int(contract["gates"]["maximum_consecutive_invalid_points"]),
    }

    trace = load_json_object(
        root / contract["simulator_reference"]["trace_path"], label="RP04K trace"
    )
    trace_by_index = {int(row["sample_index"]): row for row in trace["rows"]}
    candidate = load_json_object(
        root / contract["projection"]["candidate_path"],
        label="projection candidate",
    )
    crown_height = float(contract["projection"]["modeled_crown_height_above_base_m"])
    d1_base = np.asarray(
        current_square_center(contract["projection"]["d1_anchor_square"]),
        dtype=np.float64,
    )
    d1_crown = d1_base + np.asarray([0.0, 0.0, crown_height])
    projected_anchor = _correct_and_project(d1_crown[None, :], candidate)[0]
    physical_anchor = (anchor_a + anchor_b) / 2.0
    translation = physical_anchor - projected_anchor
    translation_norm = float(np.linalg.norm(translation))
    reference_positions = np.asarray(
        [
            np.asarray(
                trace_by_index[index]["selected_pawn_position_m"],
                dtype=np.float64,
            )
            + np.asarray([0.0, 0.0, crown_height])
            for index in admitted_indices
        ]
    )
    projected = (
        _correct_and_project(reference_positions, candidate) + translation
        if len(reference_positions)
        else np.empty((0, 2), dtype=np.float64)
    )
    physical = np.asarray(physical_points, dtype=np.float64)
    residuals = (
        np.linalg.norm(physical - projected, axis=1)
        if len(physical)
        else np.asarray([], dtype=np.float64)
    )
    median = float(np.median(residuals)) if len(residuals) else math.inf
    p90 = float(np.percentile(residuals, 90)) if len(residuals) else math.inf
    maximum = float(np.max(residuals)) if len(residuals) else math.inf
    frechet = (
        discrete_frechet(physical, projected)
        if len(physical)
        else math.inf
    )
    if len(physical) >= 2:
        physical_delta = physical[-1] - physical[0]
        projected_delta = projected[-1] - projected[0]
        denominator = float(
            np.linalg.norm(physical_delta) * np.linalg.norm(projected_delta)
        )
        cosine = (
            float(np.dot(physical_delta, projected_delta) / denominator)
            if denominator > 1e-12
            else -1.0
        )
    else:
        cosine = -1.0
    curve_gates = {
        "d1_translation": translation_norm
        <= float(contract["gates"]["d1_translation_max_px"]),
        "pointwise_median": median
        <= float(contract["gates"]["pointwise_residual_median_max_px"]),
        "pointwise_p90": p90
        <= float(contract["gates"]["pointwise_residual_p90_max_px"]),
        "ordered_discrete_frechet": frechet
        <= float(contract["gates"]["ordered_discrete_frechet_max_px"]),
        "net_displacement_cosine": cosine
        >= float(contract["gates"]["net_displacement_cosine_minimum"]),
    }
    numeric_pass = all(coverage_gates.values()) and all(curve_gates.values())
    strict_blinding = False
    promotable_pass = numeric_pass and strict_blinding
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "contract_sha256": sha256_file(contract_path),
        "annotations": {
            "pass_a_path": annotation_spec["pass_a_path"],
            "pass_a_sha256": sha256_file(pass_a_path),
            "pass_b_path": annotation_spec["pass_b_path"],
            "pass_b_sha256": sha256_file(pass_b_path),
            "anchor_disagreement_px": anchor_disagreement,
            "carry_disagreements_px": disagreements,
            "admitted_indices": admitted_indices,
            "admitted_count": len(admitted_indices),
            "temporal_tercile_counts": tercile_counts,
            "maximum_consecutive_invalid": maximum_invalid_run,
        },
        "comparison": {
            "d1_translation_xy_px": translation.tolist(),
            "d1_translation_norm_px": translation_norm,
            "pointwise_residual_median_px": median,
            "pointwise_residual_p90_px": p90,
            "pointwise_residual_max_px": maximum,
            "ordered_discrete_frechet_px": frechet,
            "net_displacement_cosine": cosine,
        },
        "gates": {
            "coverage": coverage_gates,
            "curve": curve_gates,
            "numeric_pass": numeric_pass,
            "strict_annotation_blinding": strict_blinding,
            "promotable_pass": promotable_pass,
        },
        "verdict": (
            "NUMERIC_PASS_NONPROMOTABLE_BLINDING_LIMITATION"
            if numeric_pass
            else "TERMINAL_DIAGNOSTIC_NEGATIVE"
        ),
        "ledger": {
            "camera_projected_carry_prefix_real_to_sim": {
                "successes": 0,
                "attempts": 1,
                "numeric_successes_nonpromotable": int(numeric_pass),
            },
            "realized_action_outcome_transfer_added": 0,
        },
        "claim_boundary": (
            "Action-free 2D crown correspondence diagnostic only. The executor "
            "inspected raw RP04K 3D rows before annotation freeze, so even a "
            "numeric pass is non-promotable. No timing, depth, metric 3D, "
            "action replay, terminal fit, or transfer claim."
        ),
        "authority": contract["authority"],
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_path, receipt)
    return receipt
