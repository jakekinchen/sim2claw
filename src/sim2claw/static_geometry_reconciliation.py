"""Read-only reconciliation of existing static geometry evidence channels."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .paths import REPO_ROOT


SCHEMA = "sim2claw.realized_action_static_geometry_reconciliation.v1"
RECEIPT_SCHEMA = (
    "sim2claw.realized_action_static_geometry_reconciliation_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "realized_action_static_geometry_reconciliation_v1.json"
)
OUTPUT_PATH = (
    REPO_ROOT
    / "outputs"
    / "realized_action_static_geometry_reconciliation_v1"
    / "receipt.json"
)


def _require_hash(root: Path, path: str, expected: str, label: str) -> None:
    source = root / path
    if not source.is_file() or len(expected) != 64 or sha256_file(source) != expected:
        raise FactoryArtifactError(f"{label} hash rejected: {source}")


def load_geometry_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="static geometry contract")
    if contract.get("schema_version") != SCHEMA:
        raise FactoryArtifactError("unsupported static geometry contract")
    sources = contract.get("sources")
    if not isinstance(sources, dict) or set(sources) != {
        "task_plane",
        "pawn_endpoints",
        "fixed_base",
        "articulated_differential",
        "silhouette",
        "floor_support_visual",
    }:
        raise FactoryArtifactError("static geometry sources changed")
    for name, source in sources.items():
        if name == "pawn_endpoints":
            _require_hash(
                root,
                source["closeout_path"],
                source["closeout_sha256"],
                "pawn endpoint closeout",
            )
            _require_hash(
                root,
                source["receipt_path"],
                source["receipt_sha256"],
                "pawn endpoint receipt",
            )
        else:
            _require_hash(root, source["path"], source["sha256"], name)
    rules = contract.get("rules")
    if (
        not isinstance(rules, dict)
        or rules.get("preserve_accepted_task_plane") is not True
        or any(
            rules.get(name) is not False
            for name in (
                "joint_camera_robot_object_refit_allowed",
                "camera_pose_may_absorb_joint_or_link_error",
                "retrospective_silhouette_may_promote_parameters",
                "nominal_3dgs_scale_is_metric_floor_measurement",
                "rejected_factor_may_be_promoted",
            )
        )
    ):
        raise FactoryArtifactError("static geometry proof rules widened")
    authority = contract.get("authority")
    if not isinstance(authority, dict) or any(authority.values()):
        raise FactoryArtifactError("static geometry authority widened")
    return contract


def reconcile_geometry(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    sources = contract["sources"]
    gates = contract["frozen_gates"]
    task_plane = load_json_object(
        root / sources["task_plane"]["path"], label="task plane closeout"
    )
    endpoint_closeout = load_json_object(
        root / sources["pawn_endpoints"]["closeout_path"],
        label="pawn endpoint closeout",
    )
    endpoint_receipt = load_json_object(
        root / sources["pawn_endpoints"]["receipt_path"],
        label="pawn endpoint receipt",
    )
    fixed_base = load_json_object(
        root / sources["fixed_base"]["path"], label="fixed base diagnostic"
    )
    articulated = load_json_object(
        root / sources["articulated_differential"]["path"],
        label="articulated differential closeout",
    )
    silhouette = load_json_object(
        root / sources["silhouette"]["path"], label="silhouette diagnostic"
    )
    floor_visual = load_json_object(
        root / sources["floor_support_visual"]["path"],
        label="3DGS board registration",
    )

    task_metrics = task_plane["result"]
    task_pass = (
        task_plane["status"] == "accepted_registration_prerequisite_satisfied"
        and float(task_metrics["task_plane_max_mm"])
        < float(gates["task_plane_registration_maximum_mm"])
    )
    initial_error = float(
        endpoint_closeout["observations"]["initial_d1_square_center_error_m"]
    )
    terminal_error = float(
        endpoint_closeout["observations"]["terminal_d2_square_center_error_m"]
    )
    pawn_pass = (
        initial_error <= float(gates["initial_pawn_base_maximum_error_m"])
        and terminal_error <= float(gates["terminal_pawn_base_maximum_error_m"])
    )
    fixed_metric = fixed_base["metric"]
    fixed_pass = (
        float(fixed_metric["p90_nearest_consensus_edge_px"])
        <= float(gates["fixed_base_p90_maximum_px"])
        and float(fixed_metric["within_4_px_fraction"])
        >= float(gates["fixed_base_within_4px_minimum_fraction"])
        and fixed_base.get("reliable_next_camera_constraint") is True
    )
    articulated_result = articulated["result"]
    upper_arm = articulated_result["upper_arm_tag"]
    wrist = articulated_result["wrist_tag"]
    articulated_pass = (
        upper_arm["passed"] is True
        and wrist["passed"] is True
        and float(upper_arm["displacement_residual_rmse_px"])
        <= float(gates["articulated_displacement_rmse_maximum_px"])
        and float(wrist["displacement_residual_rmse_px"])
        <= float(gates["articulated_displacement_rmse_maximum_px"])
    )
    pose = silhouette["pose_metrics"][sources["silhouette"]["pose"]]
    silhouette_numeric_pass = (
        float(pose["CAD_edge_median_px"])
        <= float(gates["silhouette_heldout_median_maximum_px"])
        and float(pose["CAD_edge_p80_px"])
        <= float(gates["silhouette_heldout_p80_maximum_px"])
    )
    silhouette_promotable = (
        silhouette_numeric_pass
        and silhouette["limitations"]["heldout_was_retrospectively_inspected"]
        is False
        and silhouette["all_diagnostic_gates_passed"] is True
    )
    metric_floor_available = bool(
        floor_visual["authority"].get("metric_scale", False)
    )

    channels = {
        "task_plane_board_corners": {
            "status": "accepted" if task_pass else "rejected",
            "task_plane_rms_mm": task_metrics["task_plane_rms_mm"],
            "task_plane_max_mm": task_metrics["task_plane_max_mm"],
            "reprojection_rms_px": task_metrics["reprojection_rms_px"],
            "reprojection_max_px": task_metrics["reprojection_max_px"],
            "denominator": "canonical registration correspondence set",
            "heldout": True,
            "source": sources["task_plane"],
        },
        "pawn_base_endpoints": {
            "status": "accepted_endpoint_only" if pawn_pass else "rejected",
            "initial_d1_error_m": initial_error,
            "terminal_d2_error_m": terminal_error,
            "endpoint_states_passed": endpoint_closeout["ledger"][
                "camera_endpoint_states_real_to_sim"
            ],
            "initial_world_position_m": endpoint_receipt["observations"]["initial"][
                "world_position_m"
            ],
            "terminal_used_as_replay_input": False,
            "source": sources["pawn_endpoints"],
        },
        "fixed_base_robot": {
            "status": "rejected_unreliable_constraint"
            if not fixed_pass
            else "accepted",
            "median_nearest_consensus_edge_px": fixed_metric[
                "median_nearest_consensus_edge_px"
            ],
            "p90_nearest_consensus_edge_px": fixed_metric[
                "p90_nearest_consensus_edge_px"
            ],
            "within_4px_fraction": fixed_metric["within_4_px_fraction"],
            "denominator": fixed_metric["projected_contour_sample_count"],
            "source": sources["fixed_base"],
        },
        "articulated_keypoint_differential": {
            "status": "rejected_partial_proximal_only"
            if not articulated_pass
            else "accepted",
            "upper_arm": upper_arm,
            "wrist": wrist,
            "physical_model_mapping_approved": articulated_result[
                "physical_model_mapping_approved"
            ],
            "source": sources["articulated_differential"],
        },
        "robot_silhouette": {
            "status": "retrospective_numeric_pass_not_promotable"
            if silhouette_numeric_pass and not silhouette_promotable
            else ("accepted" if silhouette_promotable else "rejected"),
            "cad_edge_median_px": pose["CAD_edge_median_px"],
            "cad_edge_p80_px": pose["CAD_edge_p80_px"],
            "cad_edge_clipped_rmse_px": pose["CAD_edge_clipped_rmse_px"],
            "projected_sample_count": pose["CAD_edge_sample_count"],
            "tag_corner_rmse_px": pose["tag_corner_rmse_px"],
            "tag_corner_max_px": pose["tag_corner_max_px"],
            "heldout_was_retrospectively_inspected": silhouette["limitations"][
                "heldout_was_retrospectively_inspected"
            ],
            "all_diagnostic_gates_passed": silhouette[
                "all_diagnostic_gates_passed"
            ],
            "source": sources["silhouette"],
        },
        "floor_and_support_plane": {
            "status": "metric_residual_unavailable",
            "visual_board_heldout_corner_count": floor_visual["validation"][
                "heldout_corner_count"
            ],
            "visual_board_heldout_weighted_rms_px": floor_visual["validation"][
                "heldout_weighted_rms_px"
            ],
            "nominal_playing_surface_z_m": floor_visual["target_binding"][
                "playing_surface_z_m"
            ],
            "metric_scale_authority": metric_floor_available,
            "physical_floor_or_support_height_residual_m": None,
            "source": sources["floor_support_visual"],
        },
    }
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": sha256_file(CONTRACT_PATH)
        if root == REPO_ROOT
        else canonical_digest(contract),
        "channels": channels,
        "summary": {
            "accepted_task_plane_preserved": task_pass,
            "initial_pawn_within_frozen_gate": initial_error
            <= float(gates["initial_pawn_base_maximum_error_m"]),
            "global_physical_model_mapping_approved": False,
            "joint_refit_performed": False,
            "result": "PARTIAL_ACCEPTED_WITH_ROBOT_AND_FLOOR_GAPS",
        },
        "authority": contract["authority"],
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def build_geometry_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_geometry_contract(contract_path, root=root)
    receipt = reconcile_geometry(contract, root=root)
    atomic_write_json(output_path, receipt)
    return receipt
