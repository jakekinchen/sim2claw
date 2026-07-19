#!/usr/bin/env python3
"""Extract hash-bound before/after frames for the frozen B-G product scorecard."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

import cv2
import numpy as np


PIXEL_TO_BOARD_HOMOGRAPHY = np.asarray(
    [
        [-0.0011119492862807605, 0.0009387084938256955, 0.4844076785803095],
        [0.0006171569868056414, 0.0012405124668525833, -0.4359867660673936],
        [0.001396167788577278, -0.0021385245007049768, 1.0],
    ],
    dtype=np.float64,
)
SQUARE_SIDE_M = 0.04445
CORE_SKILL_IDS = frozenset(
    f"pawn_{column}{source}_to_{column}{destination}"
    for column in "bcdefg"
    for source, destination in (("1", "2"), ("2", "1"))
)
PROPOSAL_CALIBRATION_ID = "c922_board_grid_homography_proposal_20260719_v1"
PROPOSAL_CALIBRATION_REFERENCE_RECORDING_ID = "20260719T030059Z-a26f8400"
PROPOSAL_CALIBRATION_MATRIX_SHA256 = hashlib.sha256(
    json.dumps(
        PIXEL_TO_BOARD_HOMOGRAPHY.tolist(),
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--recording-root",
        type=Path,
        default=Path("datasets/manipulation_source_recordings"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/pawn_composability/recovered_corpus_v2"),
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("configs/data/physical_pawn_move_catalog_20260719.json"),
    )
    return parser.parse_args()


def _folder_squares(folder_label: str) -> tuple[str, str]:
    normalized = folder_label.removesuffix("-redo")
    match = re.fullmatch(r"([a-h][1-8])-to-([a-h][1-8])", normalized)
    if match is None:
        raise RuntimeError(f"folder label is not a chess transition: {folder_label}")
    return match.group(1), match.group(2)


def _candidate_skill_id(source_square: str, destination_square: str) -> str | None:
    skill_id = f"pawn_{source_square}_to_{destination_square}"
    return skill_id if skill_id in CORE_SKILL_IDS else None


def classify_catalog_episodes(
    catalog_episodes: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Classify every catalog row without grouping or overwriting duplicates."""
    classified = []
    seen_recording_ids: set[str] = set()
    for row in catalog_episodes:
        recording_id = str(row.get("recording_id", ""))
        if not recording_id or recording_id in seen_recording_ids:
            raise RuntimeError(f"duplicate or missing catalog recording_id: {recording_id}")
        seen_recording_ids.add(recording_id)
        folder_label = str(row.get("folder_label", ""))
        folder_source, folder_destination = _folder_squares(folder_label)
        candidate_skill_id = _candidate_skill_id(
            folder_source, folder_destination
        )
        metadata_status = str(row.get("metadata_status", ""))
        metadata_consistent = (
            metadata_status == "consistent_folder_label_and_receipt"
        )
        if candidate_skill_id is None:
            inclusion_status = "outside_product_scope_retained_not_admitted"
            adjudication_reason = "folder_transition_is_not_one_of_12_b_g_rank1_rank2_skills"
        elif not metadata_consistent:
            inclusion_status = "candidate_pending_task_label_review"
            adjudication_reason = "folder_and_receipt_task_metadata_conflict"
        else:
            inclusion_status = "candidate_pending_pose_review"
            adjudication_reason = None
        adjudication_required = (
            candidate_skill_id is None or not metadata_consistent
        )
        classified.append(
            {
                "recording_id": recording_id,
                "folder_label": folder_label,
                "folder_source_square": folder_source,
                "folder_destination_square": folder_destination,
                "catalog_source_square": row.get("source_square"),
                "catalog_destination_square": row.get("destination_square"),
                "receipt_label": row.get("receipt_label"),
                "metadata_status": metadata_status,
                "metadata_conflict": not metadata_consistent,
                "candidate_skill_id": candidate_skill_id,
                "candidate_mapping_basis": "folder_label_only_pending_review",
                "inclusion_status": inclusion_status,
                "evaluator_admission_allowed": False,
                "adjudication_required": adjudication_required,
                "adjudication_status": (
                    "pending_review" if adjudication_required else "not_required"
                ),
                "adjudication_reason": adjudication_reason,
            }
        )
    return classified


def summarize_inventory(
    classified: list[dict[str, object]],
) -> dict[str, object]:
    counts = Counter(
        str(row["candidate_skill_id"])
        for row in classified
        if row.get("candidate_skill_id") is not None
    )
    return {
        "total_episode_count": len(classified),
        "candidate_product_episode_count": sum(counts.values()),
        "candidate_skill_coverage_count": len(counts),
        "candidate_skill_coverage_total": len(CORE_SKILL_IDS),
        "candidate_skill_coverage_complete": set(counts) == CORE_SKILL_IDS,
        "per_skill_episode_counts": {
            skill_id: counts.get(skill_id, 0) for skill_id in sorted(CORE_SKILL_IDS)
        },
        "metadata_consistent_episode_count": sum(
            not bool(row["metadata_conflict"]) for row in classified
        ),
        "metadata_conflict_episode_count": sum(
            bool(row["metadata_conflict"]) for row in classified
        ),
        "task_label_adjudication_episode_count": sum(
            bool(row["adjudication_required"]) for row in classified
        ),
    }


def build_adjudication_queue(
    classified: list[dict[str, object]],
    *,
    catalog_sha256: str,
    existing: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build a queue that preserves prior review history and never groups labels."""
    existing_entries = {}
    for entry in (existing or {}).get("entries", []):
        recording_id = str(entry.get("recording_id", ""))
        if not recording_id or recording_id in existing_entries:
            raise RuntimeError(
                f"duplicate or missing existing adjudication recording_id: {recording_id}"
            )
        existing_entries[recording_id] = entry

    entries = []
    current_ids: set[str] = set()
    retained_keys = (
        "recording_id",
        "folder_label",
        "folder_source_square",
        "folder_destination_square",
        "catalog_source_square",
        "catalog_destination_square",
        "receipt_label",
        "receipt_source_square",
        "receipt_destination_square",
        "metadata_status",
        "metadata_conflict",
        "candidate_skill_id",
        "candidate_mapping_basis",
        "inclusion_status",
        "adjudication_status",
        "adjudication_reason",
        "evaluator_admission_allowed",
    )
    for row in classified:
        if not bool(row["adjudication_required"]):
            continue
        recording_id = str(row["recording_id"])
        current_ids.add(recording_id)
        prior = existing_entries.get(recording_id, {})
        entry = {key: row.get(key) for key in retained_keys}
        entry["catalog_membership_status"] = "present_in_current_hash_bound_catalog"
        entry["review_history"] = list(prior.get("review_history", []))
        entries.append(entry)

    for recording_id, prior in existing_entries.items():
        if recording_id in current_ids:
            continue
        historical = dict(prior)
        historical["catalog_membership_status"] = (
            "historical_entry_preserved_not_in_current_catalog"
        )
        historical["evaluator_admission_allowed"] = False
        entries.append(historical)

    return {
        "schema_version": "sim2claw.pawn_task_label_adjudication_queue.v1",
        "source_catalog_sha256": catalog_sha256,
        "mutation_policy": (
            "append_only_review_history_by_recording_id_never_drop_or_overwrite_rows"
        ),
        "admission_policy": (
            "no_entry_is_evaluator_evidence_without_reviewed_task_label_correction_"
            "and_separate_reviewed_pose_annotations"
        ),
        "entry_count": len(entries),
        "entries": sorted(entries, key=lambda item: str(item["recording_id"])),
    }


def proposal_calibration_payload(
    *, reference_frame_path: str, reference_frame_sha256: str
) -> dict[str, object]:
    return {
        "calibration_id": PROPOSAL_CALIBRATION_ID,
        "review_status": "unreviewed_proposal_only",
        "evaluator_calibration_admission_allowed": False,
        "pixel_to_board_homography": PIXEL_TO_BOARD_HOMOGRAPHY.tolist(),
        "matrix_sha256": PROPOSAL_CALIBRATION_MATRIX_SHA256,
        "reference_recording_id": PROPOSAL_CALIBRATION_REFERENCE_RECORDING_ID,
        "reference_frame_path": reference_frame_path,
        "reference_frame_sha256": reference_frame_sha256,
        "correspondence_source": "81 proposed intersections from nine file-line and nine rank-line Hough families on the reference frame",
        "correspondence_count": 81,
        "proposal_fit_board_rms_m": 0.0013448643994074436,
        "provenance": "manually selected Hough line-family proposal; not independently reviewed calibration",
        "board_offset_semantics": "approximate_unreviewed_mm_for_proposal_review_only",
        "claim_boundary": "must_not_flow_into_evaluator_calibrations_without_explicit_review_lineage",
    }


def _square_center_pixel(square: str) -> tuple[float, float]:
    board = np.asarray(
        [[(ord(square[0]) - ord("a") + 0.5) * SQUARE_SIDE_M,
          (int(square[1]) - 0.5) * SQUARE_SIDE_M]],
        dtype=np.float64,
    )
    projected = cv2.perspectiveTransform(
        board.reshape(1, 1, 2), np.linalg.inv(PIXEL_TO_BOARD_HOMOGRAPHY)
    )[0, 0]
    return float(projected[0]), float(projected[1])


def _board_offset_mm(square: str, center_px: list[float]) -> list[float]:
    point = np.asarray(center_px, dtype=np.float64).reshape(1, 1, 2)
    board = cv2.perspectiveTransform(point, PIXEL_TO_BOARD_HOMOGRAPHY)[0, 0]
    nominal = np.asarray(
        [
            (ord(square[0]) - ord("a") + 0.5) * SQUARE_SIDE_M,
            (int(square[1]) - 0.5) * SQUARE_SIDE_M,
        ],
        dtype=np.float64,
    )
    return ((board - nominal) * 1000.0).astype(float).tolist()


def _dark_visual_fiducial_candidate(
    frame_path: Path, comparison_path: Path, square: str
) -> dict[str, object]:
    """Find a compact dark pawn feature with tone-specific foreground contrast."""
    image = cv2.imread(str(frame_path))
    comparison = cv2.imread(str(comparison_path))
    if image is None or comparison is None:
        raise RuntimeError(f"fiducial image read failed for {frame_path}")
    nominal_x, nominal_y = _square_center_pixel(square)
    half = 28
    left = max(0, int(round(nominal_x)) - half)
    top = max(0, int(round(nominal_y)) - half)
    right = min(image.shape[1], left + 2 * half)
    bottom = min(image.shape[0], top + 2 * half)
    current_gray = cv2.cvtColor(
        image[top:bottom, left:right], cv2.COLOR_BGR2GRAY
    ).astype(np.int16)
    comparison_gray = cv2.cvtColor(
        comparison[top:bottom, left:right], cv2.COLOR_BGR2GRAY
    ).astype(np.int16)
    local_x = nominal_x - left
    local_y = nominal_y - top
    yy, xx = np.ogrid[: current_gray.shape[0], : current_gray.shape[1]]
    radius_squared = np.square(xx - local_x) + np.square(yy - local_y)
    annulus = (radius_squared >= 19.0**2) & (radius_squared <= 26.0**2)
    background_luminance = float(np.median(comparison_gray[annulus]))
    square_tone = "brown" if background_luminance < 105.0 else "beige"
    darkness_threshold = 5 if square_tone == "brown" else 12
    signed_darkness = np.clip(
        comparison_gray - current_gray - darkness_threshold, 0, 255
    ).astype(np.uint8)
    signed_darkness = cv2.normalize(
        signed_darkness, None, 0, 255, cv2.NORM_MINMAX
    )
    circles = cv2.HoughCircles(
        cv2.GaussianBlur(signed_darkness, (5, 5), 1.0),
        cv2.HOUGH_GRADIENT,
        1.0,
        6.0,
        param1=45.0 if square_tone == "brown" else 70.0,
        param2=7.0,
        minRadius=5,
        maxRadius=14,
    )
    candidates = []
    if circles is not None:
        for local_center_x, local_center_y, radius in circles[0]:
            center_x = float(left + local_center_x)
            center_y = float(top + local_center_y)
            distance = float(
                np.hypot(center_x - nominal_x, center_y - nominal_y)
            )
            if distance > 16.0:
                continue
            mask = np.zeros(signed_darkness.shape, dtype=np.uint8)
            cv2.circle(
                mask,
                (int(round(local_center_x)), int(round(local_center_y))),
                int(round(radius)),
                255,
                -1,
            )
            darkness_score = float(cv2.mean(signed_darkness, mask=mask)[0])
            candidates.append(
                {
                    "center_px": [center_x, center_y],
                    "radius_px": float(radius),
                    "distance_from_nominal_square_center_px": distance,
                    "normalized_signed_darkness_score": darkness_score,
                    "selection_score": (
                        0.035 * darkness_score
                        - 0.55 * distance
                        - 0.18 * abs(float(radius) - 9.5)
                    ),
                }
            )
    if candidates:
        selected = max(candidates, key=lambda item: float(item["selection_score"]))
        confidence = "medium" if len(candidates) >= 1 else "low"
        selection_method = "tone_adaptive_signed_darkness_hough"
    else:
        fallback = _difference_transform_candidate(
            frame_path, comparison_path, square
        )
        selected = {
            "center_px": list(fallback["center_px"]),
            "radius_px": float(
                np.clip(float(fallback["inscribed_radius_px"]), 5.0, 14.0)
            ),
            "distance_from_nominal_square_center_px": float(
                fallback["distance_from_nominal_square_center_px"]
            ),
            "normalized_signed_darkness_score": None,
            "selection_score": None,
        }
        confidence = "low"
        selection_method = "paired_frame_distance_transform_fallback"
    return {
        **selected,
        "review_status": "proposed_pending_human_review",
        "confidence": confidence,
        "selection_method": selection_method,
        "observed_square_tone": square_tone,
        "comparison_background_luminance": background_luminance,
        "foreground_darkness_threshold_luma": darkness_threshold,
        "marker_semantics": (
            "compact_dark_visual_fiducial_not_a_reviewed_board_contact_center"
        ),
        "claim_boundary": "proposal_only_not_reviewed_pose_evidence",
    }


def infer_contact_center_proposals(
    episodes: list[dict[str, object]],
) -> dict[str, object]:
    """Apply the owner-supplied centered-initial prior to visual fiducials."""
    initial_offsets = []
    calibration_rows = []
    for episode in episodes:
        source_square = str(episode["folder_source_square"])
        nominal = np.asarray(_square_center_pixel(source_square), dtype=np.float64)
        fiducial = episode["visual_fiducial_proposals"]["initial"]
        center = np.asarray(fiducial["center_px"], dtype=np.float64)
        offset = center - nominal
        if float(np.linalg.norm(offset)) <= 16.0:
            initial_offsets.append(offset)
            calibration_rows.append(
                {
                    "recording_id": episode["recording_id"],
                    "square": source_square,
                    "visual_minus_nominal_offset_px": offset.astype(float).tolist(),
                    "task_label_status": episode["metadata_status"],
                }
            )
    if not initial_offsets:
        raise RuntimeError("no supported initial fiducials for contact-center proposal")
    offset_array = np.asarray(initial_offsets, dtype=np.float64)
    mean_offset = np.mean(offset_array, axis=0)
    covariance = (
        np.cov(offset_array, rowvar=False, ddof=1).astype(float).tolist()
        if len(offset_array) >= 2
        else None
    )
    for episode in episodes:
        for phase, square in (
            ("initial", str(episode["folder_source_square"])),
            ("final", str(episode["folder_destination_square"])),
        ):
            fiducial = episode["visual_fiducial_proposals"][phase]
            visual_center = np.asarray(fiducial["center_px"], dtype=np.float64)
            nominal = np.asarray(_square_center_pixel(square), dtype=np.float64)
            contact_center = visual_center - mean_offset
            fiducial["contact_center_px"] = contact_center.astype(float).tolist()
            fiducial["visual_fiducial_minus_nominal_offset_px"] = (
                visual_center - nominal
            ).astype(float).tolist()
            fiducial["signed_contact_center_offset_px"] = (
                contact_center - nominal
            ).astype(float).tolist()
            fiducial["signed_board_offset_mm_approximate_unreviewed"] = (
                _board_offset_mm(square, contact_center.astype(float).tolist())
            )
            fiducial["contact_center_inference"] = (
                "visual_fiducial_minus_global_mean_initial_visual_offset"
            )
            fiducial["proposal_calibration_id"] = PROPOSAL_CALIBRATION_ID
            fiducial["evaluator_pose_admission_allowed"] = False
    return {
        "status": "unreviewed_proposal_only",
        "prior": (
            "owner_supplied_observation_that_initial_placements_are_centered"
        ),
        "prior_scope": (
            "proposal_calibration_only_not_endpoint_measurement_not_self_centering_evidence"
        ),
        "included_initial_episode_count": len(initial_offsets),
        "mean_visual_fiducial_minus_nominal_offset_px": mean_offset.astype(float).tolist(),
        "covariance_px2": covariance,
        "rows": calibration_rows,
        "evaluator_pose_admission_allowed": False,
    }


def _review_tile(
    frame_path: Path,
    square: str,
    label: str,
    fiducial: dict[str, object],
) -> np.ndarray:
    image = cv2.imread(str(frame_path))
    center_x, center_y = _square_center_pixel(square)
    half = 42
    left = max(0, int(round(center_x)) - half)
    top = max(0, int(round(center_y)) - half)
    crop = image[top : top + 2 * half, left : left + 2 * half].copy()
    local = (int(round(center_x)) - left, int(round(center_y)) - top)
    cv2.drawMarker(crop, local, (0, 0, 255), cv2.MARKER_CROSS, 13, 1)
    fiducial_center = fiducial["center_px"]
    fiducial_local = (
        int(round(fiducial_center[0])) - left,
        int(round(fiducial_center[1])) - top,
    )
    fiducial_radius = int(round(float(fiducial["radius_px"])))
    cv2.circle(crop, fiducial_local, fiducial_radius, (255, 255, 0), 1)
    contact_center = fiducial["contact_center_px"]
    contact_local = (
        int(round(contact_center[0])) - left,
        int(round(contact_center[1])) - top,
    )
    cv2.drawMarker(
        crop, contact_local, (255, 255, 0), cv2.MARKER_CROSS, 11, 1
    )
    image_panel = cv2.resize(crop, (336, 336), interpolation=cv2.INTER_NEAREST)
    tile = np.zeros((410, 336, 3), dtype=np.uint8)
    tile[:336] = image_panel
    cv2.rectangle(tile, (0, 0), (335, 28), (0, 0, 0), -1)
    cv2.putText(
        tile,
        label,
        (7, 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    pixel_offset = fiducial["signed_contact_center_offset_px"]
    board_offset = fiducial[
        "signed_board_offset_mm_approximate_unreviewed"
    ]
    cv2.putText(
        tile,
        (
            f"cyan ring=fiducial r={fiducial['radius_px']:.1f}px; "
            f"cyan +=contact proposal {fiducial['confidence']}"
        ),
        (7, 357),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        (255, 255, 0),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        tile,
        (
            f"contact dpx=({pixel_offset[0]:+.1f},{pixel_offset[1]:+.1f}) "
            f"approx unreviewed dmm=({board_offset[0]:+.1f},{board_offset[1]:+.1f})"
        ),
        (7, 376),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        tile,
        (
            f"{fiducial['observed_square_tone']} square; "
            f"dark threshold={fiducial['foreground_darkness_threshold_luma']}"
        ),
        (7, 397),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.32,
        (180, 210, 220),
        1,
        cv2.LINE_AA,
    )
    return tile


def _circle_candidates(
    frame_path: Path, comparison_path: Path, square: str
) -> list[dict[str, float]]:
    image = cv2.imread(str(frame_path))
    comparison = cv2.imread(str(comparison_path))
    center_x, center_y = _square_center_pixel(square)
    half = 32
    left = max(0, int(round(center_x)) - half)
    top = max(0, int(round(center_y)) - half)
    crop = image[top : top + 2 * half, left : left + 2 * half]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    circles = cv2.HoughCircles(
        cv2.GaussianBlur(gray, (7, 7), 1.2),
        cv2.HOUGH_GRADIENT,
        1.0,
        8.0,
        param1=90.0,
        param2=8.0,
        minRadius=8,
        maxRadius=22,
    )
    if circles is None:
        return []
    result = []
    difference = cv2.cvtColor(cv2.absdiff(image, comparison), cv2.COLOR_BGR2GRAY)
    for x_value, y_value, radius in circles[0]:
        x_pixel = float(left + x_value)
        y_pixel = float(top + y_value)
        mask = np.zeros(difference.shape, dtype=np.uint8)
        cv2.circle(mask, (int(round(x_pixel)), int(round(y_pixel))), int(radius), 255, -1)
        difference_score = float(cv2.mean(difference, mask=mask)[0])
        result.append(
            {
                "center_px": [x_pixel, y_pixel],
                "radius_px": float(radius),
                "distance_from_nominal_square_center_px": float(
                    np.hypot(x_pixel - center_x, y_pixel - center_y)
                ),
                "paired_frame_difference_score": difference_score,
            }
        )
    return sorted(
        result,
        key=lambda item: (
            -item["paired_frame_difference_score"]
            + 0.35 * item["distance_from_nominal_square_center_px"]
        ),
    )


def _difference_transform_candidate(
    frame_path: Path, comparison_path: Path, square: str
) -> dict[str, object]:
    image = cv2.imread(str(frame_path))
    comparison = cv2.imread(str(comparison_path))
    center_x, center_y = _square_center_pixel(square)
    difference = cv2.cvtColor(cv2.absdiff(image, comparison), cv2.COLOR_BGR2GRAY)
    mask = np.where(difference >= 14, 255, 0).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    support = np.zeros(mask.shape, dtype=np.uint8)
    cv2.circle(
        support,
        (int(round(center_x)), int(round(center_y))),
        25,
        255,
        -1,
    )
    mask = cv2.bitwise_and(mask, support)
    distance = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    _, maximum, _, location = cv2.minMaxLoc(distance)
    return {
        "center_px": [float(location[0]), float(location[1])],
        "inscribed_radius_px": float(maximum),
        "distance_from_nominal_square_center_px": float(
            np.hypot(location[0] - center_x, location[1] - center_y)
        ),
    }


def _radial_footprint_candidate(
    frame_path: Path, comparison_path: Path, square: str
) -> dict[str, float | list[float]]:
    image = cv2.imread(str(frame_path))
    comparison = cv2.imread(str(comparison_path))
    gray = cv2.GaussianBlur(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (5, 5), 1.0)
    difference = cv2.cvtColor(cv2.absdiff(image, comparison), cv2.COLOR_BGR2GRAY)
    gradient_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gradient_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    gradient = cv2.magnitude(gradient_x, gradient_y)
    nominal_x, nominal_y = _square_center_pixel(square)
    angles = np.linspace(0.0, 2.0 * np.pi, 96, endpoint=False)
    best: dict[str, float | list[float]] | None = None
    for center_y in range(int(round(nominal_y)) - 14, int(round(nominal_y)) + 15):
        for center_x in range(int(round(nominal_x)) - 14, int(round(nominal_x)) + 15):
            distance = float(np.hypot(center_x - nominal_x, center_y - nominal_y))
            if distance > 16.0:
                continue
            for radius in range(10, 20):
                x_values = np.rint(center_x + radius * np.cos(angles)).astype(int)
                y_values = np.rint(center_y + radius * np.sin(angles)).astype(int)
                if (
                    x_values.min() < 0
                    or y_values.min() < 0
                    or x_values.max() >= image.shape[1]
                    or y_values.max() >= image.shape[0]
                ):
                    continue
                boundary_score = float(np.mean(gradient[y_values, x_values]))
                mask = np.zeros(gray.shape, dtype=np.uint8)
                cv2.circle(mask, (center_x, center_y), radius, 255, -1)
                difference_score = float(cv2.mean(difference, mask=mask)[0])
                score = (
                    0.28 * boundary_score
                    + 0.22 * difference_score
                    + 0.55 * radius
                    - 0.75 * distance
                )
                if best is None or score > float(best["selection_score"]):
                    best = {
                        "center_px": [float(center_x), float(center_y)],
                        "radius_px": float(radius),
                        "distance_from_nominal_square_center_px": distance,
                        "paired_frame_difference_score": difference_score,
                        "radial_boundary_score": boundary_score,
                        "selection_score": score,
                    }
    if best is None:
        raise RuntimeError(f"base-footprint proposal failed for {frame_path} {square}")
    return best


def _select_base_footprint_proposal(
    frame_path: Path,
    comparison_path: Path,
    square: str,
    hough_candidates: list[dict[str, float]],
    difference_candidate: dict[str, object],
) -> dict[str, object]:
    radial = _radial_footprint_candidate(frame_path, comparison_path, square)
    nominal_x, nominal_y = _square_center_pixel(square)
    eligible_hough = [
        candidate
        for candidate in hough_candidates
        if candidate["distance_from_nominal_square_center_px"] <= 16.0
        and candidate["radius_px"] >= 10.0
    ]
    scored_hough = []
    for candidate in eligible_hough:
        value = dict(candidate)
        value["selection_score"] = (
            0.55 * min(value["radius_px"], 18.0)
            + 0.12 * value["paired_frame_difference_score"]
            - 0.70 * value["distance_from_nominal_square_center_px"]
        )
        scored_hough.append(value)
    radial["selection_score"] = (
        0.55 * min(float(radial["radius_px"]), 18.0)
        + 0.12 * float(radial["paired_frame_difference_score"])
        + 0.02 * float(radial["radial_boundary_score"])
        - 0.70 * float(radial["distance_from_nominal_square_center_px"])
    )
    pool = scored_hough + [radial]
    selected = max(pool, key=lambda candidate: float(candidate["selection_score"]))
    selected_method = "hough_large_footprint" if selected in scored_hough else "radial_large_footprint"
    selected_center = [float(value) for value in selected["center_px"]]
    difference_center = difference_candidate["center_px"]
    method_agreement = float(
        np.hypot(
            selected_center[0] - difference_center[0],
            selected_center[1] - difference_center[1],
        )
    )
    if (
        method_agreement <= 5.0
        and float(selected["distance_from_nominal_square_center_px"]) <= 10.0
    ):
        confidence = "medium"
        rationale = "large footprint; hough/radial agrees with paired-frame change"
    else:
        confidence = "low"
        rationale = "large-footprint radius/edge prior; manual acceptance required"
    return {
        "review_status": "proposed_pending_human_review",
        "center_px": selected_center,
        "radius_px": float(selected["radius_px"]),
        "confidence": confidence,
        "selection_method": selected_method,
        "selection_rationale": rationale,
        "signed_pixel_offset": [
            selected_center[0] - nominal_x,
            selected_center[1] - nominal_y,
        ],
        "signed_board_offset_mm_approximate_unreviewed": _board_offset_mm(
            square, selected_center
        ),
        "distance_from_nominal_square_center_px": float(
            selected["distance_from_nominal_square_center_px"]
        ),
        "paired_frame_difference_score": float(
            selected["paired_frame_difference_score"]
        ),
        "method_agreement_px": method_agreement,
        "proposal_calibration_id": PROPOSAL_CALIBRATION_ID,
        "board_offset_semantics": (
            "approximate_unreviewed_mm_for_proposal_review_only"
        ),
        "claim_boundary": (
            "legacy_large_footprint_proposal_only_not_reviewed_pose_evidence"
        ),
    }


def main() -> int:
    args = _arguments()
    catalog_path = args.catalog.resolve()
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog_rows = catalog.get("episodes")
    if not isinstance(catalog_rows, list):
        raise RuntimeError("source catalog must contain an episodes list")
    catalog_sha256 = _sha256(catalog_path)
    classified = classify_catalog_episodes(catalog_rows)
    catalog_by_recording_id = {
        str(row["recording_id"]): row for row in catalog_rows
    }

    local_directories: dict[str, Path] = {}
    for directory in sorted(args.recording_root.iterdir()):
        if not directory.is_dir() or "__" not in directory.name:
            continue
        recording_id = directory.name.split("__", 1)[1]
        if recording_id in local_directories:
            raise RuntimeError(f"duplicate local recording_id: {recording_id}")
        local_directories[recording_id] = directory
    catalog_ids = set(catalog_by_recording_id)
    local_ids = set(local_directories)
    missing_ids = sorted(catalog_ids - local_ids)
    extra_ids = sorted(local_ids - catalog_ids)
    if missing_ids or extra_ids:
        raise RuntimeError(
            "local/catalog recording inventory mismatch; "
            f"missing={missing_ids}; extra={extra_ids}"
        )

    frame_directory = args.output / "evidence_frames"
    frame_directory.mkdir(parents=True, exist_ok=True)
    expected_frame_names = {
        f"{recording_id}__{phase}.png"
        for recording_id in catalog_ids
        for phase in ("initial", "final")
    }
    for prior_frame in frame_directory.glob("*.png"):
        if prior_frame.name not in expected_frame_names:
            prior_frame.unlink()

    episodes = []
    for classification in classified:
        recording_id = str(classification["recording_id"])
        directory = local_directories[recording_id]
        catalog_row = catalog_by_recording_id[recording_id]
        directory_folder_label = directory.name.split("__", 1)[0]
        if directory_folder_label != str(catalog_row["folder_label"]):
            raise RuntimeError(
                f"folder label drift for {recording_id}: "
                f"{directory_folder_label} != {catalog_row['folder_label']}"
            )
        metadata_path = directory / "overhead_video.json"
        receipt_path = directory / "recording_receipt.json"
        samples_path = directory / "samples.jsonl"
        video_path = directory / "overhead_c922.mp4"
        bound_assets = {
            "receipt": (receipt_path, "receipt_sha256"),
            "samples": (samples_path, "samples_sha256"),
            "overhead_video": (video_path, "overhead_video_sha256"),
        }
        actual_hashes = {}
        for asset_name, (asset_path, catalog_hash_key) in bound_assets.items():
            actual_hash = _sha256(asset_path)
            expected_hash = str(catalog_row[catalog_hash_key])
            if actual_hash != expected_hash:
                raise RuntimeError(
                    f"catalog-bound {asset_name} hash drift for {recording_id}"
                )
            actual_hashes[asset_name] = actual_hash

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt_source = receipt.get("source_square")
        receipt_destination = receipt.get("destination_square")
        if (
            receipt_source != catalog_row.get("source_square")
            or receipt_destination != catalog_row.get("destination_square")
        ):
            raise RuntimeError(
                f"catalog/receipt square drift for {recording_id}"
            )
        episode_classification = {
            **classification,
            "receipt_source_square": receipt_source,
            "receipt_destination_square": receipt_destination,
            "receipt_language_instruction": receipt.get("language_instruction"),
            "proposal_square_basis": (
                "folder_label_unreviewed_when_metadata_conflicts"
            ),
        }
        duration = float(metadata["observed_video"]["format"]["duration"])
        initial_time = max(
            0.0, float(metadata["action_start_video_offset_seconds"]) - 0.45
        )
        final_time = min(
            duration - 0.08,
            float(metadata["action_stop_video_offset_seconds"]) + 0.35,
        )
        capture = cv2.VideoCapture(str(video_path))
        frames = []
        try:
            for phase, timestamp in (
                ("initial", initial_time),
                ("final", final_time),
            ):
                capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
                ok, image = capture.read()
                if not ok:
                    raise RuntimeError(
                        f"frame read failed: {video_path} at {timestamp}"
                    )
                frame_path = frame_directory / f"{recording_id}__{phase}.png"
                if not cv2.imwrite(str(frame_path), image):
                    raise RuntimeError(f"frame write failed: {frame_path}")
                frames.append(
                    {
                        "phase": phase,
                        "time_seconds": timestamp,
                        "path": str(frame_path.resolve()),
                        "sha256": _sha256(frame_path),
                        "source_video_sha256": actual_hashes["overhead_video"],
                    }
                )
        finally:
            capture.release()
        source_square = str(classification["folder_source_square"])
        destination_square = str(classification["folder_destination_square"])
        initial_path = Path(frames[0]["path"])
        final_path = Path(frames[1]["path"])
        circle_proposals = {
            "initial": _circle_candidates(initial_path, final_path, source_square),
            "final": _circle_candidates(final_path, initial_path, destination_square),
        }
        difference_proposals = {
            "initial": _difference_transform_candidate(
                initial_path, final_path, source_square
            ),
            "final": _difference_transform_candidate(
                final_path, initial_path, destination_square
            ),
        }
        selected_proposals = {
            "initial": _select_base_footprint_proposal(
                initial_path,
                final_path,
                source_square,
                circle_proposals["initial"],
                difference_proposals["initial"],
            ),
            "final": _select_base_footprint_proposal(
                final_path,
                initial_path,
                destination_square,
                circle_proposals["final"],
                difference_proposals["final"],
            ),
        }
        visual_fiducial_proposals = {
            "initial": _dark_visual_fiducial_candidate(
                initial_path, final_path, source_square
            ),
            "final": _dark_visual_fiducial_candidate(
                final_path, initial_path, destination_square
            ),
        }
        episodes.append(
            {
                **episode_classification,
                "episode_directory": str(directory.resolve()),
                "catalog_bound_asset_sha256": actual_hashes,
                "integrity_status": "all_three_catalog_bound_asset_hashes_match",
                "overhead_metadata_path": str(metadata_path.resolve()),
                "overhead_metadata_sha256": _sha256(metadata_path),
                "frames": frames,
                "circle_proposals": circle_proposals,
                "difference_transform_proposals": difference_proposals,
                "legacy_large_base_footprint_proposals": selected_proposals,
                "visual_fiducial_proposals": visual_fiducial_proposals,
            }
        )

    contact_center_proposal_calibration = infer_contact_center_proposals(episodes)
    inventory_summary = summarize_inventory(episodes)
    if not inventory_summary["candidate_skill_coverage_complete"]:
        raise RuntimeError("catalog does not provide 12/12 candidate skill coverage")

    queue_path = args.output / "task_label_adjudication_queue.json"
    existing_queue = (
        json.loads(queue_path.read_text(encoding="utf-8"))
        if queue_path.is_file()
        else None
    )
    adjudication_queue = build_adjudication_queue(
        episodes,
        catalog_sha256=catalog_sha256,
        existing=existing_queue,
    )
    queue_path.write_text(
        json.dumps(adjudication_queue, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    tiles = []
    for episode in episodes:
        source_square = str(episode["folder_source_square"])
        destination_square = str(episode["folder_destination_square"])
        initial_path = Path(episode["frames"][0]["path"])
        final_path = Path(episode["frames"][1]["path"])
        candidate_label = episode["candidate_skill_id"] or "outside_product_scope"
        short_recording_id = str(episode["recording_id"])[-8:]
        tiles.extend(
            [
                _review_tile(
                    initial_path,
                    source_square,
                    f"{candidate_label} {short_recording_id} initial {source_square}",
                    episode["visual_fiducial_proposals"]["initial"],
                ),
                _review_tile(
                    final_path,
                    destination_square,
                    f"{candidate_label} {short_recording_id} final {destination_square}",
                    episode["visual_fiducial_proposals"]["final"],
                ),
            ]
        )
    rows = [np.hstack(tiles[index : index + 4]) for index in range(0, len(tiles), 4)]
    sheet_body = np.vstack(rows)
    banner = np.zeros((104, sheet_body.shape[1], 3), dtype=np.uint8)
    cv2.putText(
        banner,
        "RED +=NOMINAL; CYAN RING=TONE-ADAPTIVE DARK FIDUCIAL; CYAN +=INFERRED CONTACT CENTER",
        (12, 27),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.60,
        (0, 80, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        banner,
        "BROWN/BEIGE USE DIFFERENT DARKNESS THRESHOLDS; INITIAL-CENTER OFFSET PRIOR IS PROPOSAL-ONLY",
        (12, 58),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.56,
        (255, 255, 0),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        banner,
        "ALL 36 MARKERS AND APPROXIMATE MM OFFSETS ARE UNREVIEWED; CONFLICT ROWS ARE NOT ADMITTED",
        (12, 89),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.56,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    review_sheet = args.output / "base_center_review_sheet.png"
    if not cv2.imwrite(str(review_sheet), np.vstack([banner, sheet_body])):
        raise RuntimeError(f"review sheet write failed: {review_sheet}")

    reference_frame = next(
        frame
        for episode in episodes
        if episode["recording_id"] == PROPOSAL_CALIBRATION_REFERENCE_RECORDING_ID
        for frame in episode["frames"]
        if frame["phase"] == "initial"
    )
    proposal_calibration = proposal_calibration_payload(
        reference_frame_path=str(reference_frame["path"]),
        reference_frame_sha256=str(reference_frame["sha256"]),
    )
    proposal_calibration["contact_center_inference"] = (
        contact_center_proposal_calibration
    )
    raw_files = [
        path for path in args.recording_root.rglob("*") if path.is_file()
    ]
    selection_path = args.output / "frame_selection.json"
    selection = {
        "schema_version": "sim2claw.pawn_rank12_frame_selection.v2",
        **inventory_summary,
        "review_panel_count": len(tiles),
        "extracted_frame_count": sum(len(episode["frames"]) for episode in episodes),
        "raw_payload_file_count": len(raw_files),
        "raw_payload_bytes": sum(path.stat().st_size for path in raw_files),
        "catalog_bound_hash_match_count": 3 * len(episodes),
        "catalog_bound_hash_expected_count": 3 * len(episodes),
        "source_catalog_path": str(catalog_path),
        "source_catalog_sha256": catalog_sha256,
        "admitted_base_center_annotation_count": 0,
        "candidate_status": "proposed_pending_human_review",
        "review_finding": (
            "Square-tone-specific signed-darkness fiducials replace the prior "
            "single-threshold visual marker. The owner-supplied centered-initial "
            "observation calibrates a mean visual-to-contact offset for proposals only."
        ),
        "required_next_review": (
            "A human must inspect every cyan ring and inferred contact-center cross "
            "in its hash-bound full-resolution frame, adjudicate conflicting task "
            "labels, and explicitly accept or correct each pose with reviewer lineage "
            "before an evaluator annotation manifest is admitted."
        ),
        "review_sheet_path": str(review_sheet.resolve()),
        "review_sheet_sha256": _sha256(review_sheet),
        "review_sheet_marker_meaning": {
            "red_cross": "nominal_square_center_reference_not_a_measured_pose",
            "cyan_ring": (
                "tone_adaptive_compact_dark_visual_fiducial_not_a_contact_measurement"
            ),
            "cyan_cross": (
                "offset_corrected_contact_center_proposal_pending_human_review"
            ),
            "millimeter_offsets": (
                "approximate_unreviewed_proposal_values_never_evaluator_calibration"
            ),
        },
        "proposal_calibration": proposal_calibration,
        "task_label_adjudication_queue_path": str(queue_path.resolve()),
        "task_label_adjudication_queue_sha256": _sha256(queue_path),
        "task_label_adjudication_queue_entry_count": adjudication_queue[
            "entry_count"
        ],
        "episodes": episodes,
    }
    selection_path.write_text(
        json.dumps(selection, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(selection_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
