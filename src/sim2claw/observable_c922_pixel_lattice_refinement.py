"""Retrospective, zero-new-data C922 board-pixel camera refinement."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from scipy.optimize import least_squares

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .observable_camera_world import evaluate_camera_world, load_camera_contract
from .paths import REPO_ROOT


SCHEMA = "sim2claw.observable_c922_pixel_lattice_refinement_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_c922_pixel_lattice_refinement_receipt.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_c922_pixel_lattice_refinement_v1.json"
)
OUTPUT_PATH = (
    REPO_ROOT
    / "outputs"
    / "observable_c922_pixel_lattice_refinement_v1"
    / "receipt.json"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _bound_path(binding: dict[str, Any], *, root: Path, label: str) -> Path:
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


def load_refinement_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="C922 pixel-lattice contract")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    _require(
        contract.get("evidence_role")
        == "retrospective_outcome_informed_protocol_diagnostic",
        "retrospective evidence role changed",
    )
    sources = contract.get("sources")
    _require(isinstance(sources, dict) and sources, "sources are missing")
    for source_id, binding in sources.items():
        _require(isinstance(binding, dict), f"invalid source: {source_id}")
        _bound_path(binding, root=root, label=source_id)

    cohorts = contract.get("cohorts")
    _require(isinstance(cohorts, list) and len(cohorts) == 2, "cohorts changed")
    identities: set[tuple[Any, ...]] = set()
    mount_tokens: set[str] = set()
    for cohort in cohorts:
        _require(isinstance(cohort, dict), "cohort is invalid")
        images = cohort.get("images")
        _require(
            isinstance(images, list) and len(images) >= 4,
            "cohort image list is incomplete",
        )
        for index, binding in enumerate(images):
            _bound_path(
                binding,
                root=root,
                label=f"{cohort.get('cohort_id')} image {index}",
            )
        camera = cohort.get("camera_identity")
        _require(isinstance(camera, dict), "cohort camera identity is missing")
        identities.add(
            (
                camera.get("name"),
                camera.get("unique_id"),
                camera.get("width"),
                camera.get("height"),
                camera.get("pixel_format"),
                camera.get("fps"),
            )
        )
        mount_tokens.add(str(cohort.get("fixed_mount_token", "")))
    _require(len(identities) == 1, "camera mode changed between cohorts")
    _require(
        mount_tokens == {"current-workcell-fixed-mount-20260728-v2-registration"},
        "fixed mount token changed",
    )

    extraction = contract.get("pixel_extraction")
    _require(isinstance(extraction, dict), "pixel extraction is missing")
    _require(
        extraction.get("seed_use")
        == "search_initialization_only_not_an_observation",
        "homography seed was promoted to an observation",
    )
    _require(
        extraction.get("interior_indices")
        == [[i, j] for j in range(1, 8) for i in range(1, 8)],
        "interior lattice changed",
    )
    reviewed = extraction.get("reviewed_unoccluded_indices")
    _require(
        isinstance(reviewed, list) and len(reviewed) >= 12,
        "reviewed visible-region mask is missing",
    )
    _require(
        extraction.get("review_basis")
        == "retained_pixel_visibility_and_extraction_stability_only",
        "reviewed mask basis changed",
    )

    families = contract.get("camera_families")
    _require(
        isinstance(families, list)
        and [family.get("radial_term_count") for family in families] == [0, 1, 2],
        "camera challenger families changed",
    )
    _require(
        all(
            family.get("principal_point_px") == [320.0, 240.0]
            and family.get("square_pixels") is True
            and float(family.get("skew_px", 1.0)) == 0.0
            for family in families
        ),
        "camera gauge widened",
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


def extract_image_intersections(
    image_path: Path,
    *,
    playing_corners_px: np.ndarray,
    extraction: dict[str, Any],
) -> dict[tuple[int, int], dict[str, Any]]:
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    _require(image is not None, f"cannot decode {image_path}")
    _require(tuple(image.shape) == (480, 640), "source image dimensions changed")
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
    spacing = float(canonical_side) / 8.0
    result: dict[tuple[int, int], dict[str, Any]] = {}
    for i, j in extraction["interior_indices"]:
        center_x = int(round(float(i) * spacing))
        center_y = int(round(float(j) * spacing))
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
        canonical_point = np.asarray([[[float(x), float(y)]]], dtype=np.float64)
        image_point = cv2.perspectiveTransform(
            canonical_point, canonical_to_image
        )[0, 0]
        result[(int(i), int(j))] = {
            "image_point_px": image_point.tolist(),
            "canonical_point_px": [float(x), float(y)],
            "saddle_score": float(score),
        }
    return result


def aggregate_cohort(
    image_results: list[dict[tuple[int, int], dict[str, Any]]],
    *,
    extraction: dict[str, Any],
) -> dict[tuple[int, int], dict[str, Any]]:
    top_count = int(extraction["top_images_per_intersection"])
    minimum_score = float(extraction["minimum_median_saddle_score"])
    maximum_dispersion = float(extraction["maximum_rms_dispersion_px"])
    result: dict[tuple[int, int], dict[str, Any]] = {}
    for index in [tuple(item) for item in extraction["interior_indices"]]:
        ranked = sorted(
            (
                (
                    float(image_result[index]["saddle_score"]),
                    image_number,
                    np.asarray(
                        image_result[index]["image_point_px"], dtype=np.float64
                    ),
                )
                for image_number, image_result in enumerate(image_results)
            ),
            key=lambda item: (-item[0], item[1]),
        )[:top_count]
        points = np.asarray([item[2] for item in ranked], dtype=np.float64)
        scores = np.asarray([item[0] for item in ranked], dtype=np.float64)
        point = np.median(points, axis=0)
        distances = np.linalg.norm(points - point, axis=1)
        dispersion = float(np.sqrt(np.mean(distances**2)))
        median_score = float(np.median(scores))
        accepted = median_score >= minimum_score and dispersion <= maximum_dispersion
        result[index] = {
            "image_point_px": point.tolist(),
            "median_saddle_score": median_score,
            "rms_dispersion_px": dispersion,
            "selected_image_indices": [int(item[1]) for item in ranked],
            "selected_scores": scores.tolist(),
            "accepted": bool(accepted),
        }
    return result


def project_camera_family(
    object_points: np.ndarray,
    values: np.ndarray,
    *,
    principal_point_px: np.ndarray,
    radial_term_count: int,
) -> tuple[np.ndarray, np.ndarray]:
    rotation, _ = cv2.Rodrigues(np.asarray(values[1:4], dtype=np.float64))
    camera_points = (
        np.asarray(object_points, dtype=np.float64) @ rotation.T
        + np.asarray(values[4:7], dtype=np.float64)
    )
    normalized = camera_points[:, :2] / camera_points[:, 2:3]
    radius_squared = np.sum(normalized**2, axis=1)
    scale = np.ones(len(normalized), dtype=np.float64)
    if radial_term_count >= 1:
        scale += float(values[7]) * radius_squared
    if radial_term_count >= 2:
        scale += float(values[8]) * radius_squared**2
    projected = (
        normalized * scale[:, None] * float(values[0])
        + np.asarray(principal_point_px, dtype=np.float64)
    )
    return projected, camera_points[:, 2]


def fit_camera_family(
    board_xy_m: np.ndarray,
    image_points_px: np.ndarray,
    *,
    family: dict[str, Any],
    initial_values: np.ndarray,
) -> dict[str, Any]:
    board_xy = np.asarray(board_xy_m, dtype=np.float64)
    image = np.asarray(image_points_px, dtype=np.float64)
    _require(
        board_xy.ndim == 2
        and board_xy.shape[1] == 2
        and image.shape == board_xy.shape
        and len(board_xy) >= 10,
        "camera correspondence shape changed",
    )
    object_points = np.column_stack((board_xy, np.zeros(len(board_xy))))
    principal = np.asarray(family["principal_point_px"], dtype=np.float64)
    radial_count = int(family["radial_term_count"])
    parameter_count = 7 + radial_count
    initial = np.asarray(initial_values[:parameter_count], dtype=np.float64)
    lower = np.asarray(
        [
            float(family["minimum_focal_px"]),
            -10.0,
            -10.0,
            -10.0,
            -5.0,
            -5.0,
            -5.0,
            *([-float(family["radial_bound"])] * radial_count),
        ],
        dtype=np.float64,
    )
    upper = np.asarray(
        [
            float(family["maximum_focal_px"]),
            10.0,
            10.0,
            10.0,
            5.0,
            5.0,
            5.0,
            *([float(family["radial_bound"])] * radial_count),
        ],
        dtype=np.float64,
    )

    def residual(values: np.ndarray) -> np.ndarray:
        projected, _ = project_camera_family(
            object_points,
            values,
            principal_point_px=principal,
            radial_term_count=radial_count,
        )
        return (projected - image).ravel()

    fit = least_squares(
        residual,
        initial,
        bounds=(lower, upper),
        x_scale="jac",
        max_nfev=20_000,
        ftol=1e-13,
        xtol=1e-13,
        gtol=1e-13,
    )
    _require(bool(fit.success), f"{family['family_id']} fit did not converge")
    projected, depths = project_camera_family(
        object_points,
        fit.x,
        principal_point_px=principal,
        radial_term_count=radial_count,
    )
    errors = np.linalg.norm(projected - image, axis=1)
    singular = np.linalg.svd(fit.jac, compute_uv=False)
    radial = [float(value) for value in fit.x[7:]]
    radial_at_bound = any(
        abs(abs(value) - float(family["radial_bound"])) <= 1e-6
        for value in radial
    )
    return {
        "family_id": family["family_id"],
        "radial_term_count": radial_count,
        "focal_px": float(fit.x[0]),
        "principal_point_px": principal.tolist(),
        "rotation_vector": fit.x[1:4].tolist(),
        "translation_board_to_camera_m": fit.x[4:7].tolist(),
        "radial_coefficients": radial,
        "parameter_values": fit.x.tolist(),
        "reprojection_errors_px": errors.tolist(),
        "reprojection_rms_px": float(np.sqrt(np.mean(errors**2))),
        "reprojection_max_px": float(np.max(errors)),
        "positive_depth_fraction": float(np.mean(depths > 0.0)),
        "solver": {
            "jacobian_rank": int(np.linalg.matrix_rank(fit.jac)),
            "jacobian_condition_number": float(singular[0] / singular[-1]),
            "active_mask": fit.active_mask.tolist(),
            "radial_at_bound": radial_at_bound,
        },
    }


def evaluate_camera_family(
    fit: dict[str, Any],
    board_xy_m: np.ndarray,
    image_points_px: np.ndarray,
) -> dict[str, Any]:
    object_points = np.column_stack(
        (np.asarray(board_xy_m, dtype=np.float64), np.zeros(len(board_xy_m)))
    )
    projected, depths = project_camera_family(
        object_points,
        np.asarray(fit["parameter_values"], dtype=np.float64),
        principal_point_px=np.asarray(fit["principal_point_px"], dtype=np.float64),
        radial_term_count=int(fit["radial_term_count"]),
    )
    errors = np.linalg.norm(
        projected - np.asarray(image_points_px, dtype=np.float64), axis=1
    )
    return {
        "reprojection_errors_px": errors.tolist(),
        "reprojection_rms_px": float(np.sqrt(np.mean(errors**2))),
        "reprojection_max_px": float(np.max(errors)),
        "positive_depth_fraction": float(np.mean(depths > 0.0)),
    }


def _cohort_observations(
    cohort: dict[str, Any],
    *,
    playing_corners_px: np.ndarray,
    extraction: dict[str, Any],
    root: Path,
) -> tuple[dict[tuple[int, int], dict[str, Any]], list[dict[str, Any]]]:
    image_results = [
        extract_image_intersections(
            root / str(binding["path"]),
            playing_corners_px=playing_corners_px,
            extraction=extraction,
        )
        for binding in cohort["images"]
    ]
    aggregate = aggregate_cohort(image_results, extraction=extraction)
    serializable = [
        {
            "index": list(index),
            **value,
        }
        for index, value in aggregate.items()
    ]
    return aggregate, serializable


def evaluate_refinement(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    sources = contract["sources"]
    annotations = _bound_json(
        sources["fit_annotations"], root=root, label="fit annotations"
    )
    old_contract_path = _bound_path(
        sources["prior_camera_contract"], root=root, label="prior camera contract"
    )
    old_contract = load_camera_contract(old_contract_path, root=root)
    old_receipt = evaluate_camera_world(old_contract, root=root)
    old_model = old_receipt["physical_pinhole"]
    corners = np.asarray(
        annotations["board_lattice"]["playing_corners_px"], dtype=np.float64
    )
    extraction = contract["pixel_extraction"]
    cohort_aggregates: dict[str, dict[tuple[int, int], dict[str, Any]]] = {}
    cohort_serializable: dict[str, list[dict[str, Any]]] = {}
    for cohort in contract["cohorts"]:
        aggregate, serializable = _cohort_observations(
            cohort,
            playing_corners_px=corners,
            extraction=extraction,
            root=root,
        )
        cohort_aggregates[cohort["cohort_id"]] = aggregate
        cohort_serializable[cohort["cohort_id"]] = serializable

    cohort_ids = [cohort["cohort_id"] for cohort in contract["cohorts"]]
    first = cohort_aggregates[cohort_ids[0]]
    second = cohort_aggregates[cohort_ids[1]]
    reviewed_indices = {
        tuple(item) for item in extraction["reviewed_unoccluded_indices"]
    }
    overlap = sorted(
        index
        for index in first
        if index in reviewed_indices
        and first[index]["accepted"]
        and second[index]["accepted"]
    )
    _require(overlap, "no accepted cross-cohort intersections")
    first_points = np.asarray(
        [first[index]["image_point_px"] for index in overlap], dtype=np.float64
    )
    second_points = np.asarray(
        [second[index]["image_point_px"] for index in overlap], dtype=np.float64
    )
    agreement_errors = np.linalg.norm(first_points - second_points, axis=1)
    board_xy = (
        np.asarray(overlap, dtype=np.float64)
        / 8.0
        * float(contract["board_gauge"]["playing_side_m"])
    )

    initial_values = np.asarray(
        [
            old_model["focal_px"],
            *old_model["rotation_vector"],
            *old_model["translation_board_to_camera_m"],
            0.0,
            0.0,
        ],
        dtype=np.float64,
    )
    family_results: list[dict[str, Any]] = []
    for family in contract["camera_families"]:
        fit_first = fit_camera_family(
            board_xy,
            first_points,
            family=family,
            initial_values=initial_values,
        )
        fit_second = fit_camera_family(
            board_xy,
            second_points,
            family=family,
            initial_values=initial_values,
        )
        validate_second = evaluate_camera_family(
            fit_first, board_xy, second_points
        )
        validate_first = evaluate_camera_family(
            fit_second, board_xy, first_points
        )
        mean_validation_rms = float(
            np.mean(
                [
                    validate_second["reprojection_rms_px"],
                    validate_first["reprojection_rms_px"],
                ]
            )
        )
        family_results.append(
            {
                "family_id": family["family_id"],
                "fit_on_first": fit_first,
                "validate_on_second": validate_second,
                "fit_on_second": fit_second,
                "validate_on_first": validate_first,
                "mean_cross_cohort_validation_rms_px": mean_validation_rms,
                "maximum_cross_cohort_validation_max_px": float(
                    max(
                        validate_second["reprojection_max_px"],
                        validate_first["reprojection_max_px"],
                    )
                ),
            }
        )

    zero = family_results[0]
    zero_validation_rms = float(zero["mean_cross_cohort_validation_rms_px"])
    for family_result in family_results:
        radial_count = int(
            family_result["fit_on_first"]["radial_term_count"]
        )
        improvement = (
            (zero_validation_rms - float(
                family_result["mean_cross_cohort_validation_rms_px"]
            ))
            / zero_validation_rms
            if radial_count
            else 0.0
        )
        family_result["validation_improvement_over_zero_fraction"] = improvement
        family_result["radial_promotable"] = bool(
            radial_count > 0
            and improvement
            >= float(contract["selection_gates"]["minimum_radial_validation_gain_fraction"])
            and not family_result["fit_on_first"]["solver"]["radial_at_bound"]
            and not family_result["fit_on_second"]["solver"]["radial_at_bound"]
        )

    selected = next(
        (
            family_result
            for family_result in reversed(family_results)
            if family_result["radial_promotable"]
        ),
        zero,
    )
    pooled_points = (first_points + second_points) / 2.0
    selected_family = next(
        family
        for family in contract["camera_families"]
        if family["family_id"] == selected["family_id"]
    )
    pooled_fit = fit_camera_family(
        board_xy,
        pooled_points,
        family=selected_family,
        initial_values=initial_values,
    )
    board_frame = old_receipt["fit"]["board_frame"]
    board_to_world = np.asarray(
        board_frame["rotation_board_to_world"], dtype=np.float64
    )
    board_origin_world = np.asarray(
        board_frame["origin_world_m"], dtype=np.float64
    )
    board_to_camera, _ = cv2.Rodrigues(
        np.asarray(pooled_fit["rotation_vector"], dtype=np.float64)
    )
    world_to_camera = board_to_camera @ board_to_world.T
    board_translation = np.asarray(
        pooled_fit["translation_board_to_camera_m"], dtype=np.float64
    )
    world_translation = board_translation - world_to_camera @ board_origin_world
    camera_center_world = -world_to_camera.T @ world_translation
    diagnostic_simulator_camera = {
        "camera_center_task_world_m": camera_center_world.tolist(),
        "rotation_world_to_camera_cv": world_to_camera.tolist(),
        "translation_world_to_camera_cv_m": world_translation.tolist(),
        "vertical_fov_degrees": math.degrees(
            2.0
            * math.atan(
                float(contract["cohorts"][0]["camera_identity"]["height"])
                / (2.0 * float(pooled_fit["focal_px"]))
            )
        ),
        "image_width_px": int(
            contract["cohorts"][0]["camera_identity"]["width"]
        ),
        "image_height_px": int(
            contract["cohorts"][0]["camera_identity"]["height"]
        ),
        "canonical_scene_replacement_authority": False,
        "use": "inspection_only_board_plane_candidate",
    }

    old_values = initial_values[:7]
    old_first = evaluate_camera_family(
        {
            "parameter_values": old_values.tolist(),
            "principal_point_px": [320.0, 240.0],
            "radial_term_count": 0,
        },
        board_xy,
        first_points,
    )
    old_second = evaluate_camera_family(
        {
            "parameter_values": old_values.tolist(),
            "principal_point_px": [320.0, 240.0],
            "radial_term_count": 0,
        },
        board_xy,
        second_points,
    )
    old_mean_rms = float(
        np.mean(
            [
                old_first["reprojection_rms_px"],
                old_second["reprojection_rms_px"],
            ]
        )
    )
    improvement_fraction = (
        old_mean_rms - float(selected["mean_cross_cohort_validation_rms_px"])
    ) / old_mean_rms
    gates = contract["selection_gates"]
    agreement_pass = (
        len(overlap) >= int(gates["minimum_overlap_intersections"])
        and float(np.sqrt(np.mean(agreement_errors**2)))
        <= float(gates["maximum_cohort_agreement_rms_px"])
        and float(np.max(agreement_errors))
        <= float(gates["maximum_cohort_agreement_max_px"])
    )
    diagnostic_improvement_pass = (
        improvement_fraction
        >= float(gates["minimum_prior_model_rms_improvement_fraction"])
        and float(selected["mean_cross_cohort_validation_rms_px"])
        <= float(gates["maximum_cross_cohort_validation_rms_px"])
        and float(selected["maximum_cross_cohort_validation_max_px"])
        <= float(gates["maximum_cross_cohort_validation_max_px"])
    )
    board_plane_diagnostic_accepted = bool(
        agreement_pass and diagnostic_improvement_pass
    )
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "contract_sha256": (
            sha256_file(CONTRACT_PATH)
            if root == REPO_ROOT and CONTRACT_PATH.is_file()
            else canonical_digest(contract)
        ),
        "evidence_role": contract["evidence_role"],
        "source_reconciliation": {
            "prior_lattice_observation_count": 4,
            "prior_lattice_generated_intersection_count": 25,
            "prior_lattice_generated_by_single_homography": True,
            "prior_reported_rms_is_not_25_independent_pixel_measurements": True,
            "camera_identity_and_mode_match": True,
            "fixed_mount_token_match": True,
            "new_physical_data_rows": 0,
            "new_camera_opens": 0,
            "reviewed_visible_region_mask_count": len(reviewed_indices),
            "reviewed_visible_region_mask_used_simulator_residuals": False,
            "reviewed_visible_region_mask_used_task_outcomes": False,
        },
        "cohort_observations": cohort_serializable,
        "cross_cohort_agreement": {
            "overlap_intersection_indices": [list(index) for index in overlap],
            "overlap_intersection_count": len(overlap),
            "errors_px": agreement_errors.tolist(),
            "rms_px": float(np.sqrt(np.mean(agreement_errors**2))),
            "max_px": float(np.max(agreement_errors)),
            "passed": agreement_pass,
        },
        "prior_camera_on_observed_pixels": {
            "model_artifact_sha256": old_receipt["artifact_sha256"],
            "first_cohort": old_first,
            "second_cohort": old_second,
            "mean_rms_px": old_mean_rms,
        },
        "family_comparison": family_results,
        "selected_family_id": selected["family_id"],
        "pooled_board_plane_candidate": pooled_fit,
        "diagnostic_simulator_camera": diagnostic_simulator_camera,
        "improvement_over_prior_model_fraction": improvement_fraction,
        "board_plane_diagnostic_accepted": board_plane_diagnostic_accepted,
        "exact_intrinsic_calibration_approved": False,
        "distortion_measured": False,
        "global_camera_or_robot_mapping_approved": False,
        "simulator_canonical_camera_replaced": False,
        "result": (
            "BOARD_PLANE_DIAGNOSTIC_IMPROVED_EXACT_INTRINSICS_UNIDENTIFIED"
            if board_plane_diagnostic_accepted
            else "RETAINED_PIXEL_REFINEMENT_NEGATIVE"
        ),
        "limitations": [
            "The extraction protocol was developed after inspecting retained fit images, so this is an outcome-informed retrospective diagnostic.",
            "Only intersections confidently visible in both retained cohorts are evaluated; coverage is concentrated on the board region not occluded by robot and pieces.",
            "The fixed principal point, square pixels, and selected radial family remain assumptions unless independently calibrated.",
            "No pristine held-out pose remains, so this receipt cannot approve exact intrinsics, distortion, global mapping, contact, or task transfer.",
        ],
        "proof_boundaries": contract["proof_boundaries"],
        "authority": contract["authority"],
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def build_refinement_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_refinement_contract(contract_path, root=root)
    receipt = evaluate_refinement(contract, root=root)
    atomic_write_json(output_path, receipt)
    return receipt


__all__ = [
    "CONTRACT_PATH",
    "OUTPUT_PATH",
    "aggregate_cohort",
    "build_refinement_receipt",
    "evaluate_refinement",
    "extract_image_intersections",
    "fit_camera_family",
    "load_refinement_contract",
    "project_camera_family",
]
