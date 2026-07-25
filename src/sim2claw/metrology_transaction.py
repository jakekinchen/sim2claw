"""Fail-closed control manifest for the versioned P8/P13 metrology run.

This module sequences the existing C922 calibration and stationary workcell
registration commands.  It validates their shared identity and physical-input
boundary without opening a camera, constructing a robot gateway, or running a
metric fit.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import c922_calibration_acquisition as c922_acquisition
from . import c922_exact_mode_calibration as c922_calibration
from . import workcell_registration as registration


TRANSACTION_SCHEMA = "sim2claw.p8_p13_metrology_transaction.v1"
REPORT_SCHEMA = "sim2claw.p8_p13_metrology_readiness.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRANSACTION_PATH = (
    REPO_ROOT
    / "configs/acquisition/current_100mm_p8_p13_metrology_transaction_v1.json"
)
DEFAULT_OUTPUT_PATH = (
    REPO_ROOT / "runs/current-100mm-p8-p13-metrology-v1/readiness.json"
)


class MetrologyTransactionError(RuntimeError):
    """A transaction manifest or bound physical input failed closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MetrologyTransactionError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MetrologyTransactionError(f"Could not load {label}: {error}") from error
    _require(isinstance(value, dict), f"{label} must be an object.")
    return value


def _inside(root: Path, value: Any, label: str) -> Path:
    _require(isinstance(value, str) and value.strip(), f"{label} path is missing.")
    path = (root / value).resolve()
    resolved_root = root.resolve()
    _require(
        path != resolved_root and resolved_root in path.parents,
        f"{label} escapes the repository root.",
    )
    return path


def _finite_positive(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) > 0.0
    )


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _focus_value(value: Any) -> bool:
    return (
        (isinstance(value, str) and bool(value.strip()))
        or (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(float(value))
        )
    )


def _expected_exact_mode(contract: Mapping[str, Any]) -> dict[str, Any]:
    camera = contract["camera"]
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


def _validate_printed_grid(
    path: Path,
    *,
    contract: Mapping[str, Any],
) -> list[str]:
    value = _load_json(path, "printed-grid measurement receipt")
    missing: list[str] = []
    if value.get("schema_version") != "sim2claw.printed_grid_measurement_receipt.v1":
        missing.append("printed_grid_measurement_receipt_schema")
    if value.get("target_asset_sha256") != contract["target"]["asset_sha256"]:
        missing.append("printed_grid_measurement_target_identity")
    for field in (
        "square_pitch_x_mm",
        "square_pitch_y_mm",
        "total_width_x_mm",
        "total_height_y_mm",
        "instrument_resolution_mm",
        "measurement_uncertainty_mm",
    ):
        if not _finite_positive(value.get(field)):
            missing.append(f"printed_grid_measurement:{field}")
    for field in (
        "measurement_id",
        "instrument",
        "measurement_points_description",
        "measured_by",
        "measured_at",
    ):
        if not _nonempty(value.get(field)):
            missing.append(f"printed_grid_measurement:{field}")
    if value.get("measurement_basis") != "physical_post_print_measurement":
        missing.append("printed_grid_measurement_basis")
    if value.get("nominal_values_substituted") is not False:
        missing.append("printed_grid_measurement_nominal_substitution")
    return missing


def _validate_direct_board_measurement(path: Path) -> list[str]:
    value = _load_json(path, "direct board measurement receipt")
    missing: list[str] = []
    if value.get("schema_version") != "sim2claw.direct_board_measurement_receipt.v1":
        missing.append("direct_board_measurement_receipt_schema")
    if value.get("measurement_method") != "direct_physical_measurement":
        missing.append("direct_board_measurement_method")
    if not _finite_positive(value.get("playing_side_m")):
        missing.append("direct_board_measurement:playing_side_m")
    if not _finite_positive(value.get("standard_uncertainty_m")):
        missing.append("direct_board_measurement:standard_uncertainty_m")
    for field in ("measurement_tool_id", "operator", "measured_at"):
        if not _nonempty(value.get(field)):
            missing.append(f"direct_board_measurement:{field}")
    if value.get("nominal_value_substituted") is not False:
        missing.append("direct_board_measurement_nominal_substitution")
    if value.get("synthetic") is not False:
        missing.append("direct_board_measurement_synthetic")
    return missing


def _validate_stationary_capture(
    path: Path,
    *,
    exact_mode: Mapping[str, Any],
    expected_focus: Any,
    acknowledgements: Sequence[str],
) -> list[str]:
    value = _load_json(path, "stationary capture receipt")
    missing: list[str] = []
    if value.get("schema_version") != registration.STATIONARY_CAPTURE_SCHEMA:
        missing.append("stationary_capture_receipt_schema")
    if value.get("status") != "physical_capture_complete":
        missing.append("stationary_capture_complete")
    if value.get("proof_class") != "physical_camera_frame":
        missing.append("stationary_capture_proof_class")
    if value.get("synthetic") is not False:
        missing.append("stationary_capture_synthetic")
    if value.get("exact_mode") != dict(exact_mode):
        missing.append("stationary_capture_exact_c922_mode")
    if expected_focus in (None, "") or value.get("focus_setting") != expected_focus:
        missing.append("stationary_capture_constant_focus")
    ack = value.get("operator_acknowledgements")
    if not isinstance(ack, Mapping) or set(ack) != set(acknowledgements) or not all(
        ack.get(name) is True for name in acknowledgements
    ):
        missing.append("stationary_capture_operator_acknowledgements")
    if value.get("robot_gateway_constructed") is not False:
        missing.append("stationary_capture_robot_gateway")
    if value.get("robot_motion_used") != 0:
        missing.append("stationary_capture_robot_motion")
    return missing


def _validate_annotation(
    path: Path,
    *,
    role: str,
    capture: Mapping[str, Any] | None,
    other_annotator: str | None,
) -> tuple[list[str], str | None]:
    value = _load_json(path, f"{role} annotation")
    missing: list[str] = []
    if value.get("schema_version") != "sim2claw.workcell_registration_annotation.v1":
        missing.append(f"{role}_schema")
    if value.get("status") != "complete_independent_annotation":
        missing.append(f"{role}_complete")
    if value.get("annotation_role") != role:
        missing.append(f"{role}_role")
    if value.get("synthetic_capture") is not False:
        missing.append(f"{role}_synthetic")
    annotator = value.get("annotator_id")
    if not _nonempty(annotator):
        missing.append(f"{role}_identity")
    elif other_annotator is not None and annotator == other_annotator:
        missing.append("independent_annotator_identity")
    points = value.get("points")
    if not isinstance(points, list) or len(points) != 8:
        missing.append(f"{role}_eight_point_annotation")
    else:
        point_ids = [row.get("point_id") for row in points if isinstance(row, Mapping)]
        if len(point_ids) != 8 or len(set(point_ids)) != 8:
            missing.append(f"{role}_distinct_point_ids")
        for row in points:
            if not isinstance(row, Mapping) or not isinstance(row.get("pixel_xy"), list):
                missing.append(f"{role}_pixel_annotations")
                break
    if capture is not None:
        if value.get("source_frame_sha256") != capture.get("selected_frame_sha256"):
            missing.append(f"{role}_source_frame_binding")
        if value.get("capture_receipt_sha256") is None:
            missing.append(f"{role}_capture_binding")
    return missing, str(annotator) if _nonempty(annotator) else None


def _artifact_path(
    inputs: Mapping[str, Any],
    key: str,
    *,
    root: Path,
    missing: list[str],
) -> Path | None:
    value = inputs.get(key)
    if value is None:
        missing.append(key)
        return None
    try:
        path = _inside(root, value, key)
    except MetrologyTransactionError:
        missing.append(f"{key}_path")
        return None
    if not path.is_file():
        missing.append(key)
        return None
    return path


def _validate_manifest_shape(transaction: Mapping[str, Any]) -> list[str]:
    invalid: list[str] = []
    if transaction.get("schema_version") != TRANSACTION_SCHEMA:
        invalid.append("transaction_schema")
    if transaction.get("status") != "preregistered_readiness_only_no_camera_or_robot_authority":
        invalid.append("transaction_status")
    bindings = transaction.get("bindings")
    identity = transaction.get("identity")
    physical = transaction.get("physical_inputs")
    evaluation = transaction.get("evaluation")
    sequence = transaction.get("sequence")
    authority = transaction.get("authority")
    for value, name in (
        (bindings, "bindings"),
        (identity, "identity"),
        (physical, "physical_inputs"),
        (evaluation, "evaluation"),
        (authority, "authority"),
    ):
        if not isinstance(value, Mapping):
            invalid.append(name)
    if not isinstance(sequence, list) or [
        row.get("step_id") for row in sequence if isinstance(row, Mapping)
    ] != [
        "readiness",
        "p8_plan_preflight",
        "p8_capture",
        "p8_evaluate",
        "p13_stationary_capture",
        "p13_annotation_bundle",
        "p13_finalize",
        "p13_evaluate",
    ]:
        invalid.append("sequence")
    if isinstance(authority, Mapping):
        expected_zero = {
            "readiness_camera_opened": False,
            "readiness_camera_sessions_used": 0,
            "readiness_new_frames_captured": 0,
            "robot_motion_used": 0,
            "simulator_replays_used": 0,
            "provider_calls": 0,
            "training_rows": 0,
            "metric_fit_authorized": False,
            "evaluator_admission": False,
            "physical_authority": False,
            "task_success_verified": False,
        }
        if dict(authority) != expected_zero:
            invalid.append("authority_boundary")
    if isinstance(physical, Mapping):
        c922 = physical.get("c922_capture")
        if not isinstance(c922, Mapping) or c922.get("frame_count") != 18:
            invalid.append("physical_c922_frame_count")
        if not isinstance(c922, Mapping) or c922.get("split_counts") != {
            "fit": 12,
            "validation": 3,
            "held_out": 3,
        }:
            invalid.append("physical_c922_split_counts")
        stationary = physical.get("stationary_capture")
        if not isinstance(stationary, Mapping) or stationary.get(
            "operator_acknowledgements"
        ) != [
            "board_and_camera_fixed",
            "board_cleared",
            "a1_h1_a8_markers_visible",
            "focus_locked",
            "no_competing_camera_owner",
        ]:
            invalid.append("physical_stationary_acknowledgements")
        annotations = physical.get("independent_annotations")
        if not isinstance(annotations, Mapping) or annotations.get(
            "annotator_count"
        ) != 2 or annotations.get("points_per_annotator") != 8:
            invalid.append("physical_annotation_denominator")
    if isinstance(evaluation, Mapping):
        if evaluation.get("maximum_leave_one_out_board_rms_m") != 0.0015:
            invalid.append("evaluation_board_rms_threshold")
        if evaluation.get("maximum_annotator_disagreement_m") != 0.0015:
            invalid.append("evaluation_annotator_threshold")
        if evaluation.get("maximum_reprojection_rms_px") != registration.MAX_REPROJECTION_RMS_PX:
            invalid.append("evaluation_reprojection_threshold")
    return sorted(set(invalid))


def _readiness(
    transaction_path: Path,
    *,
    repo_root: Path,
) -> dict[str, Any]:
    root = repo_root.resolve()
    transaction = _load_json(transaction_path, "metrology transaction")
    invalid = _validate_manifest_shape(transaction)
    bindings = transaction.get("bindings", {})
    identity = transaction.get("identity", {})
    inputs = transaction.get("operator_inputs", {})
    if not isinstance(bindings, Mapping):
        bindings = {}
    if not isinstance(identity, Mapping):
        identity = {}
    if not isinstance(inputs, Mapping):
        invalid.append("operator_inputs")
        inputs = {}

    c922_binding = bindings.get("c922_calibration_contract", {})
    p13_binding = bindings.get("p13_readiness_contract", {})
    plan_binding = bindings.get("c922_acquisition_plan", {})
    try:
        c922_contract_path = _inside(
            root, c922_binding.get("path"), "C922 calibration contract"
        )
        p13_contract_path = _inside(
            root, p13_binding.get("path"), "P13 readiness contract"
        )
        plan_path = _inside(root, plan_binding.get("path"), "C922 acquisition plan")
    except MetrologyTransactionError as error:
        invalid.append(str(error))
        c922_contract_path = p13_contract_path = plan_path = None

    c922_contract: dict[str, Any] = {}
    p13_contract: dict[str, Any] = {}
    plan: dict[str, Any] = {}
    binding_hashes: dict[str, Any] = {}
    if c922_contract_path is not None:
        if not c922_contract_path.is_file():
            invalid.append("c922_calibration_contract_missing")
        else:
            observed = sha256_file(c922_contract_path)
            binding_hashes["c922_calibration_contract"] = observed
            if observed != c922_binding.get("sha256"):
                invalid.append("c922_calibration_contract_hash")
            c922_contract = _load_json(c922_contract_path, "C922 calibration contract")
            if c922_contract.get("schema_version") != c922_calibration.CONTRACT_SCHEMA:
                invalid.append("c922_calibration_contract_schema")
    if p13_contract_path is not None:
        if not p13_contract_path.is_file():
            invalid.append("p13_readiness_contract_missing")
        else:
            observed = sha256_file(p13_contract_path)
            binding_hashes["p13_readiness_contract"] = observed
            if observed != p13_binding.get("sha256"):
                invalid.append("p13_readiness_contract_hash")
            p13_contract = _load_json(p13_contract_path, "P13 readiness contract")
            if p13_contract.get("schema_version") != "sim2claw.metric_registration_readiness_contract.v1":
                invalid.append("p13_readiness_contract_schema")
    if plan_path is not None:
        if not plan_path.is_file():
            invalid.append("c922_acquisition_plan_missing")
        else:
            binding_hashes["c922_acquisition_plan"] = sha256_file(plan_path)
            plan = _load_json(plan_path, "C922 acquisition plan")
            if plan.get("schema_version") != plan_binding.get("schema_version"):
                invalid.append("c922_acquisition_plan_schema")

    if c922_contract:
        dataset = c922_contract.get("dataset", {})
        if dataset.get("required_split_counts") != {
            "fit": 12,
            "validation": 3,
            "held_out": 3,
        } or dataset.get("minimum_accepted_frames") != 18:
            invalid.append("p8_frame_denominator")
        if c922_contract.get("target", {}).get("nominal_dimensions_are_metric_authority") is not False:
            invalid.append("p8_nominal_target_authority")
    if p13_contract:
        thresholds = p13_contract.get("readiness_thresholds", {})
        if thresholds.get("minimum_spatially_distributed_correspondences") != 8:
            invalid.append("p13_point_denominator")
        if thresholds.get("minimum_independent_annotators_per_point") != 2:
            invalid.append("p13_annotator_denominator")
        if thresholds.get("maximum_held_out_or_leave_one_out_board_rms_m") != 0.0015:
            invalid.append("p13_board_rms_threshold")
        if thresholds.get("maximum_pairwise_annotator_disagreement_m") != 0.0015:
            invalid.append("p13_annotator_threshold")

    exact_mode = _expected_exact_mode(c922_contract) if c922_contract else {}
    if identity.get("camera") != {
        key: c922_contract.get("camera", {}).get(key)
        for key in (
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
    }:
        invalid.append("shared_exact_c922_identity")
    if identity.get("workspace_pose_id") != registration.WORKSPACE_POSE_ID:
        invalid.append("workspace_pose_identity")
    if identity.get("board_pose_id") != registration.BOARD_POSE_ID:
        invalid.append("board_pose_identity")
    if identity.get("transform_direction") != "board_to_workcell":
        invalid.append("transform_direction")

    p8_preflight: dict[str, Any] = {
        "status": "not_run_invalid_binding",
        "missing_physical_inputs": [],
        "invalid_plan_reasons": [],
        "capture_ready": False,
    }
    if plan_path is not None and c922_contract_path is not None and not invalid:
        p8_preflight = c922_acquisition.preflight_acquisition(
            plan_path, contract_path=c922_contract_path
        )
    elif plan:
        invalid.append("p8_preflight_not_run")

    remaining_physical: list[str] = []
    if not plan or plan.get("target", {}).get("printed_and_mounted_flat") is not True:
        remaining_physical.append("printed_target_mounted_flat")
    printed_path = _artifact_path(
        inputs, "printed_grid_measurement_receipt", root=root, missing=remaining_physical
    )
    if printed_path is not None and c922_contract:
        remaining_physical.extend(
            _validate_printed_grid(printed_path, contract=c922_contract)
        )
    focus = plan.get("focus", {}) if isinstance(plan, Mapping) else {}
    focus_setting = focus.get("setting") if isinstance(focus, Mapping) else None
    if (
        not isinstance(focus, Mapping)
        or focus.get("mode") != "manual_locked"
        or not _focus_value(focus_setting)
        or not _nonempty(focus.get("observation_method"))
    ):
        remaining_physical.append("fixed_observable_c922_focus_setting")
    if plan.get("owner_capture_approved") is not True:
        remaining_physical.append("owner_approved_stationary_18_view_capture")
    if not p8_preflight.get("frame_plan_valid"):
        remaining_physical.append("18_distinct_views_with_existing_p8_coverage_gates")
    remaining_physical.append("18_exact_mode_c922_frame_receipts")

    capture_path = _artifact_path(
        inputs, "stationary_capture_receipt", root=root, missing=remaining_physical
    )
    if capture_path is None:
        remaining_physical.append("stationary_fixed_board_capture")
    else:
        remaining_physical.extend(
            _validate_stationary_capture(
                capture_path,
                exact_mode=exact_mode,
                expected_focus=focus_setting,
                acknowledgements=(
                    "board_and_camera_fixed",
                    "board_cleared",
                    "a1_h1_a8_markers_visible",
                    "focus_locked",
                    "no_competing_camera_owner",
                ),
            )
        )

    board_path = _artifact_path(
        inputs, "direct_board_measurement_receipt", root=root, missing=remaining_physical
    )
    if board_path is not None:
        remaining_physical.extend(_validate_direct_board_measurement(board_path))
    survey_path = _artifact_path(
        inputs, "physical_survey", root=root, missing=remaining_physical
    )
    if survey_path is None:
        remaining_physical.append("a1_h1_a8_physical_survey")
    else:
        survey = _load_json(survey_path, "physical survey")
        if board_path is not None:
            try:
                registration.validate_survey(
                    survey,
                    root=root,
                    board_measurement_sha256=sha256_file(board_path),
                )
            except registration.WorkcellRegistrationError as error:
                remaining_physical.append(f"physical_survey:{error}")
        else:
            remaining_physical.append("physical_survey_board_measurement_binding")

    annotator_a = _artifact_path(
        inputs, "annotator_a", root=root, missing=remaining_physical
    )
    annotator_b = _artifact_path(
        inputs, "annotator_b", root=root, missing=remaining_physical
    )
    annotator_a_id: str | None = None
    if annotator_a is not None:
        annotation_missing, annotator_a_id = _validate_annotation(
            annotator_a, role="annotator_a", capture=None, other_annotator=None
        )
        remaining_physical.extend(annotation_missing)
    if annotator_b is not None:
        annotation_missing, _ = _validate_annotation(
            annotator_b,
            role="annotator_b",
            capture=None,
            other_annotator=annotator_a_id,
        )
        remaining_physical.extend(annotation_missing)
    if annotator_a is None or annotator_b is None:
        remaining_physical.append("two_independent_eight_point_annotations")

    derived: list[str] = []
    if _artifact_path(inputs, "p8_inputs_manifest", root=root, missing=[]):
        pass
    else:
        derived.append("p8_calibration_input_manifest_after_18_frame_capture")
    if _artifact_path(inputs, "p13_inputs_manifest", root=root, missing=[]):
        pass
    else:
        derived.append("p13_metric_registration_input_manifest_after_finalize")
    derived.extend(
        [
            "evaluator_owned_p8_intrinsics_and_distortion_receipts",
            "evaluator_owned_p13_leave_one_out_board_fit_and_camera_workcell_transform",
        ]
    )
    remaining_physical = sorted(
        set(remaining_physical)
        - {"annotator_a", "annotator_b", "physical_survey", "stationary_capture_receipt"}
    )
    invalid = sorted(set(invalid))
    status = (
        "invalid_transaction"
        if invalid
        else "ready_for_live_capture_sequence"
        if not remaining_physical
        else "blocked_physical_inputs"
    )
    return {
        "schema_version": REPORT_SCHEMA,
        "transaction_id": transaction.get("transaction_id"),
        "status": status,
        "transaction_path": str(transaction_path.resolve()),
        "transaction_sha256": sha256_file(transaction_path),
        "baseline_commit": transaction.get("baseline_commit"),
        "binding_hashes": binding_hashes,
        "p8": {
            "plan_path": str(plan_path) if plan_path is not None else None,
            "plan_sha256": binding_hashes.get("c922_acquisition_plan"),
            "preflight": p8_preflight,
            "exact_mode": exact_mode,
            "split_counts": {"fit": 12, "validation": 3, "held_out": 3},
        },
        "p13": {
            "workspace_pose_id": registration.WORKSPACE_POSE_ID,
            "board_pose_id": registration.BOARD_POSE_ID,
            "stationary_capture_schema": registration.STATIONARY_CAPTURE_SCHEMA,
            "point_count": 8,
            "independent_annotator_count": 2,
            "thresholds": {
                "maximum_leave_one_out_board_rms_m": 0.0015,
                "maximum_annotator_disagreement_m": 0.0015,
                "maximum_reprojection_rms_px": registration.MAX_REPROJECTION_RMS_PX,
            },
        },
        "remaining_physical_inputs": remaining_physical,
        "remaining_derived_evaluator_inputs": sorted(set(derived)),
        "invalid_transaction_reasons": invalid,
        "sequence": transaction.get("sequence", []),
        "authority": {
            "camera_opened": False,
            "camera_sessions_used": 0,
            "new_frames_captured": 0,
            "robot_motion_used": 0,
            "simulator_replays_used": 0,
            "provider_calls": 0,
            "training_rows": 0,
            "metric_fit_authorized": False,
            "evaluator_admission": False,
            "physical_authority": False,
            "task_success_verified": False,
        },
    }


def preflight_transaction(
    transaction_path: Path = DEFAULT_TRANSACTION_PATH,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Return a read-only readiness report; no device APIs are called."""

    return _readiness(transaction_path.resolve(), repo_root=repo_root.resolve())


def preflight_and_write(
    transaction_path: Path = DEFAULT_TRANSACTION_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    report = preflight_transaction(transaction_path, repo_root=repo_root)
    output = output_path.resolve()
    _require(
        output.is_relative_to(repo_root.resolve()),
        "Readiness output escapes the repository root.",
    )
    _require(not output.exists(), "Readiness output already exists; replay is forbidden.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transaction", type=Path, default=DEFAULT_TRANSACTION_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args(argv)
    report = preflight_and_write(args.transaction, args.output)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ready_for_live_capture_sequence" else 1


if __name__ == "__main__":
    raise SystemExit(main())
