"""Receipt-bound application of Phase 1 SAIL to retained project evidence."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from ..pawn_bg_grasp_coordinate_descent import _summary
from ..paths import REPO_ROOT


CONFIG_PATH = REPO_ROOT / "configs" / "sail" / "project_application_v1.json"
FREEZE_PATH = (
    REPO_ROOT
    / "configs"
    / "sail"
    / "project_application_candidate_freeze_v1.json"
)


class ProjectApplicationError(RuntimeError):
    """The project application campaign failed closed."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProjectApplicationError(f"cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise ProjectApplicationError(f"JSON root must be an object: {path}")
    return value


def _resolve(root: Path, path: str) -> Path:
    resolved = (root / path).resolve()
    if root.resolve() not in resolved.parents and resolved != root.resolve():
        raise ProjectApplicationError(f"path escapes repository root: {path}")
    return resolved


def _verify_binding(root: Path, binding: dict[str, Any], label: str) -> dict[str, Any]:
    path = _resolve(root, str(binding["path"]))
    actual = sha256_file(path)
    expected = str(binding["sha256"])
    if actual != expected:
        raise ProjectApplicationError(
            f"{label} SHA-256 drifted: expected {expected}, got {actual}"
        )
    return {"path": str(path), "sha256": actual}


def _wrong_contact_keys(row: dict[str, Any]) -> set[tuple[str, str, str]]:
    return {
        (
            str(row["recording_id"]),
            str(contact["piece_name"]),
            str(contact["robot_body_name"]),
        )
        for contact in row.get("wrong_piece_robot_contacts", [])
    }


def _failure_flags(row: dict[str, Any]) -> list[str]:
    gates = row["original_gate_results"]
    flags: list[str] = []
    if not row["bilateral_contact_observed"]:
        flags.append("no_bilateral_contact")
    if not row["qualified_bilateral_contact_observed"]:
        flags.append("no_qualified_pinch")
    if not row["piece_lifted"]:
        flags.append("no_40mm_lift")
    elif not row["lift_and_transport"]:
        flags.append("no_transport_while_above_lift_gate")
    if not row["whole_base_inside_destination"]:
        flags.append("terminal_destination_containment_failure")
    if not gates["upright"]:
        flags.append("terminal_upright_failure")
    if not gates["settled"]:
        flags.append("terminal_settle_failure")
    if not gates["released"]:
        flags.append("release_failure")
    if not gates["no_wrong_piece_contact"]:
        flags.append("wrong_piece_robot_contact")
    if not gates["collateral_within_limit"]:
        flags.append("collateral_displacement")
    post_lift = row.get("post_first_lift_task_diagnostic") or {}
    if post_lift.get("destination_entry") and not row["lift_and_transport"]:
        flags.append("destination_entry_hidden_below_instantaneous_lift_gate")
    return flags


def _candidate_status(
    *, name: str, summary: dict[str, Any], baseline: dict[str, Any], config: dict[str, Any]
) -> tuple[str, list[str]]:
    if name == "baseline":
        return "reference", []
    reasons: list[str] = []
    if summary["strict_successes"] < baseline["strict_successes"]:
        reasons.append("strict_success_regression")
    if summary["lift_and_transport"] < baseline["lift_and_transport"]:
        reasons.append("lift_and_transport_regression")
    if summary["lifted"] < baseline["lifted"]:
        reasons.append("lift_regression")
    guards = config["frozen_metrics"]["trace_guardrails"]
    trace = summary["trace_metrics"]
    if trace["overall_joint_rms_degrees"] > guards["maximum_joint_rms_degrees"]:
        reasons.append("joint_trace_guard_failure")
    if trace["ee_rms_m"] > guards["maximum_ee_rms_m"]:
        reasons.append("ee_trace_guard_failure")
    if name == "solver_cg":
        reasons.append("numerical_instability_observed")
    return ("rejected" if reasons else "screen_pass"), reasons


def _relative_delta(candidate: float, baseline: float) -> float | None:
    if baseline == 0.0:
        return None
    return (candidate - baseline) / baseline


def compile_project_application(
    *,
    repository_root: Path = REPO_ROOT,
    output_root: Path | None = None,
    config_path: Path = CONFIG_PATH,
    freeze_path: Path = FREEZE_PATH,
) -> dict[str, Any]:
    root = repository_root.resolve()
    config = _load_json(config_path)
    freeze = _load_json(freeze_path)
    if config.get("schema_version") != "sim2claw.sail_project_application_campaign.v1":
        raise ProjectApplicationError("project application config schema drifted")
    if freeze.get("schema_version") != "sim2claw.sail_project_application_candidate_freeze.v1":
        raise ProjectApplicationError("candidate freeze schema drifted")
    if freeze["campaign_id"] != config["campaign_id"]:
        raise ProjectApplicationError("candidate freeze campaign id drifted")

    verified_sources = {
        name: _verify_binding(root, binding, name)
        for name, binding in config["source_bindings"].items()
    }
    baseline_path = _resolve(
        root, config["source_bindings"]["accepted_v3_group_receipt"]["path"]
    )
    baseline = _load_json(baseline_path)
    expected_actions = config["action_sha256_by_recording_id"]
    baseline_actions = {
        str(row["recording_id"]): str(row["action_sha256"])
        for row in baseline["episodes"]
    }
    if baseline_actions != expected_actions:
        raise ProjectApplicationError("accepted baseline action identities drifted")
    if not all(bool(row["action_byte_identical"]) for row in baseline["episodes"]):
        raise ProjectApplicationError("accepted baseline contains action mutation")

    sentinel_directory = _resolve(root, "outputs/sail/project-application-v1/sentinels")
    candidate_rows: list[dict[str, Any]] = []
    baseline_sentinel_summary: dict[str, Any] | None = None
    for path in sorted(sentinel_directory.glob("*.json")):
        payload = _load_json(path)
        observed = {
            str(row["recording_id"]): str(row["action_sha256"])
            for row in payload["episodes"]
        }
        expected = {
            recording_id: expected_actions[recording_id]
            for recording_id in config["episode_roles"]["adaptive_sentinels"]
        }
        if observed != expected or not payload["summary"]["action_invariance"]:
            raise ProjectApplicationError(f"sentinel action identity drifted: {path}")
        name = path.stem
        if name == "baseline":
            baseline_sentinel_summary = payload["summary"]
            break
    if baseline_sentinel_summary is None:
        raise ProjectApplicationError("sentinel baseline is missing")
    for path in sorted(sentinel_directory.glob("*.json")):
        payload = _load_json(path)
        status, reasons = _candidate_status(
            name=path.stem,
            summary=payload["summary"],
            baseline=baseline_sentinel_summary,
            config=config,
        )
        candidate_rows.append(
            {
                "candidate_id": path.stem,
                "path": str(path),
                "sha256": sha256_file(path),
                "parameter_digest": payload["parameter_digest"],
                "status": status,
                "reasons": reasons,
                "summary": payload["summary"],
            }
        )
    if len(candidate_rows) != int(freeze["adaptive_candidate_count_including_baseline"]):
        raise ProjectApplicationError("adaptive candidate inventory drifted")

    _verify_binding(root, freeze["baseline_sentinel_receipt"], "frozen sentinel baseline")
    selected_binding = freeze["selected_family"]["sentinel_receipt"]
    _verify_binding(root, selected_binding, "frozen selected sentinel candidate")
    evaluation_path = _resolve(root, freeze["evaluation_output"])
    evaluation = _load_json(evaluation_path)
    if evaluation["parameter_digest"] != selected_binding["parameter_digest"]:
        raise ProjectApplicationError("evaluation parameter digest drifted from freeze")
    expected_evaluation_ids = freeze["evaluation_recording_ids"]
    if evaluation["recording_ids"] != expected_evaluation_ids:
        raise ProjectApplicationError("evaluation episode order drifted from freeze")
    sentinel_selected = _load_json(_resolve(root, selected_binding["path"]))
    candidate_episodes = sentinel_selected["episodes"] + evaluation["episodes"]
    candidate_actions = {
        str(row["recording_id"]): str(row["action_sha256"])
        for row in candidate_episodes
    }
    if candidate_actions != expected_actions:
        raise ProjectApplicationError("full candidate action identities drifted")
    candidate_summary = _summary(candidate_episodes)

    baseline_metric_path = _resolve(
        root, "outputs/sail/project-application-v1/baseline-task-metrics-v2.json"
    )
    baseline_metric = _load_json(baseline_metric_path)
    if {
        str(row["recording_id"]): str(row["action_sha256"])
        for row in baseline_metric["episodes"]
    } != expected_actions:
        raise ProjectApplicationError("secondary task metric action identities drifted")

    failure_episodes = []
    failure_counts: Counter[str] = Counter()
    for row in baseline_metric["episodes"]:
        flags = _failure_flags(row)
        failure_counts.update(flags)
        failure_episodes.append(
            {
                "recording_id": row["recording_id"],
                "folder_label": row["folder_label"],
                "action_sha256": row["action_sha256"],
                "failure_flags": flags,
                "piece_lifted": row["piece_lifted"],
                "lift_and_transport": row["lift_and_transport"],
                "final_target_distance_m": row["final_target_distance_m"],
                "maximum_other_piece_displacement_m": row[
                    "maximum_other_piece_displacement_m"
                ],
                "post_first_lift_task_diagnostic": row.get(
                    "post_first_lift_task_diagnostic"
                ),
            }
        )

    baseline_wrong = set().union(
        *(_wrong_contact_keys(row) for row in baseline["episodes"])
    )
    candidate_wrong = set().union(
        *(_wrong_contact_keys(row) for row in candidate_episodes)
    )
    guards = config["frozen_metrics"]["trace_guardrails"]
    candidate_max_collateral = max(
        float(row["maximum_other_piece_displacement_m"])
        for row in candidate_episodes
    )
    baseline_max_collateral = max(
        float(row["maximum_other_piece_displacement_m"])
        for row in baseline["episodes"]
    )
    task_gates = {
        "minimum_two_lift_and_transport": candidate_summary["lift_and_transport"]
        >= int(
            config["acceptance"]["diagnostic_task_advancement_requires"][
                "minimum_all_episode_lift_and_transport"
            ]
        ),
        "joint_trace_guard": candidate_summary["trace_metrics"][
            "overall_joint_rms_degrees"
        ]
        <= guards["maximum_joint_rms_degrees"],
        "ee_trace_guard": candidate_summary["trace_metrics"]["ee_rms_m"]
        <= guards["maximum_ee_rms_m"],
        "no_new_wrong_piece_contact": candidate_wrong <= baseline_wrong,
        "no_worse_maximum_collateral": candidate_max_collateral
        <= baseline_max_collateral,
        "action_invariance": bool(candidate_summary["action_invariance"]),
    }
    task_advancement_admitted = all(task_gates.values())

    baseline_trace_path = _resolve(
        root, "outputs/sail/project-application-v1/c2-v3-surface-witness.json"
    )
    candidate_trace_path = _resolve(
        root, "outputs/sail/project-application-v1/c2-condim4-surface-witness.json"
    )
    baseline_trace = _load_json(baseline_trace_path)["episode"]
    candidate_trace = _load_json(candidate_trace_path)["episode"]
    baseline_loss = int(
        baseline_trace["retention_event_summary"][
            "first_bilateral_contact_loss_after_lift"
        ]["source_index"]
    )
    candidate_loss = int(
        candidate_trace["retention_event_summary"][
            "first_bilateral_contact_loss_after_lift"
        ]["source_index"]
    )
    slip_reduction = 1.0 - (
        float(candidate_trace["maximum_post_grasp_slip_m"])
        / float(baseline_trace["maximum_post_grasp_slip_m"])
    )
    mechanism_gates = {
        "contact_loss_delayed_ten_source_frames": candidate_loss - baseline_loss
        >= int(
            config["acceptance"]["mechanism_advancement_requires"][
                "diagnosis_anchor_contact_loss_delayed_source_frames"
            ]
        ),
        "post_grasp_slip_reduced_ten_percent": slip_reduction
        >= float(
            config["acceptance"]["mechanism_advancement_requires"][
                "diagnosis_anchor_post_grasp_slip_relative_reduction"
            ]
        ),
        "no_task_count_regression": candidate_summary["lifted"]
        >= baseline["summary"]["lifted"]
        and candidate_summary["lift_and_transport"]
        >= baseline["summary"]["lift_and_transport"],
        "trace_guardrails": task_gates["joint_trace_guard"]
        and task_gates["ee_trace_guard"],
    }
    mechanism_advancement_admitted = all(mechanism_gates.values())

    evidence_receipt = _load_json(
        _resolve(root, config["source_bindings"]["retained_evidence_receipt"]["path"])
    )
    residual_receipt = _load_json(
        _resolve(
            root,
            config["source_bindings"]["phase_aligned_residual_receipt"]["path"],
        )
    )
    phase_1_graph_receipt = _load_json(
        _resolve(
            root,
            config["source_bindings"]["deterministic_belief_graph_receipt"][
                "path"
            ],
        )
    )
    inventory = {
        "schema_version": "sim2claw.sail_project_failure_inventory.v1",
        "proof_class": config["proof_boundary"]["proof_class"],
        "phase_1_application_surface": {
            "phase_1_milestones_completed": 18,
            "retained_evidence_count": evidence_receipt["counts"]["evidence_count"],
            "physical_episode_count": evidence_receipt["counts"][
                "physical_episode_count"
            ],
            "action_frozen_development_episode_count": evidence_receipt["counts"][
                "action_frozen_development_episode_count"
            ],
            "residual_sample_count": residual_receipt["counts"][
                "residual_sample_count"
            ],
            "belief_graph_node_count": phase_1_graph_receipt["counts"]["nodes"],
            "belief_graph_edge_count": phase_1_graph_receipt["counts"]["edges"],
            "policy_training_admitted": False,
            "physical_authority": False,
        },
        "baseline_task_summary": baseline["summary"],
        "failure_counts": dict(sorted(failure_counts.items())),
        "episodes": failure_episodes,
        "resolved_inconsistencies": [
            {
                "id": "metric_post_first_lift_blind_spot",
                "status": "resolved_observability_only",
                "finding": (
                    "C2, D2, and F2 enter the whole-base center-distance region "
                    "after first lift; D2 and F2 do so below the instantaneous "
                    "40 mm lift gate while bilateral contact remains."
                ),
                "evaluator_changed": False,
            },
            {
                "id": "rubber_mirroring_geometry",
                "status": "localized_not_physically_resolved",
                "finding": (
                    "The baseline load-bearing pair is moving-rubber to fixed-rigid, "
                    "because the fixed sleeve is displaced distally and never enters "
                    "the C2 contact witness. Corrected fixed-sleeve placements regress "
                    "the sentinel consequence vector."
                ),
                "physical_geometry_identified": False,
            },
            {
                "id": "c2_premature_drop",
                "status": "localized_terminal_negative_for_bounded_contact_models",
                "finding": (
                    "The closed gripper loses opposing load as contact migrates from "
                    "the upper collar/head transition onto the head sphere; the selected "
                    "contact-dimensionality candidate loses contact nine frames earlier."
                ),
                "physical_cause_identified": False,
            },
        ],
        "unresolved_requirements": [
            "metric vertical registration between retained physical frames and simulator",
            "per-episode pawn centers and exact pawn dimensions and mass",
            "measured two-sided rubber collision profile and jaw registration",
            "a new independently sealed physical replay set for validation",
        ],
        "authority": config["proof_boundary"],
    }
    inventory["inventory_digest"] = canonical_digest(inventory)

    belief_graph = {
        "schema_version": "sim2claw.sail_project_application_belief_graph.v1",
        "nodes": [
            {"id": "O1", "type": "observation", "label": "C2 drops before release"},
            {"id": "O2", "type": "observation", "label": "gripper remains closed"},
            {"id": "O3", "type": "observation", "label": "fixed side uses rigid primitive"},
            {"id": "R1", "type": "residual", "label": "opposition and load collapse on head sphere"},
            {"id": "H1", "type": "hypothesis", "label": "solver creep"},
            {"id": "H2", "type": "hypothesis", "label": "friction constraint formulation"},
            {"id": "H4", "type": "hypothesis", "label": "surface migration and pad geometry"},
            {"id": "I1", "type": "intervention", "label": "no-slip and solver probes"},
            {"id": "I2", "type": "intervention", "label": "cone and condim probes"},
            {"id": "I3", "type": "intervention", "label": "fixed sleeve placement probes"},
            {"id": "V1", "type": "verdict", "label": "bounded contact-model terminal negative"},
            {"id": "M1", "type": "metric_revision", "label": "post-first-lift destination diagnostic"},
        ],
        "edges": [
            ["O1", "R1"],
            ["O2", "R1"],
            ["O3", "R1"],
            ["R1", "H1"],
            ["R1", "H2"],
            ["R1", "H4"],
            ["H1", "I1"],
            ["H2", "I2"],
            ["H4", "I3"],
            ["I1", "V1"],
            ["I2", "V1"],
            ["I3", "V1"],
            ["O1", "M1"],
        ],
        "candidate_screen_count": len(candidate_rows),
        "physical_causal_graph": False,
        "graph_digest": "",
    }
    belief_graph["graph_digest"] = canonical_digest(
        {key: value for key, value in belief_graph.items() if key != "graph_digest"}
    )

    verdict = {
        "schema_version": "sim2claw.sail_project_application_verdict.v1",
        "baseline": baseline["summary"],
        "candidate": candidate_summary,
        "diagnostic_deltas": {
            "qualified_bilateral_contact_count": candidate_summary[
                "qualified_bilateral_contact"
            ]
            - baseline["summary"]["qualified_bilateral_contact"],
            "whole_base_inside_destination_count": candidate_summary[
                "whole_base_inside_destination"
            ]
            - baseline["summary"]["whole_base_inside_destination"],
            "mean_final_target_distance_relative": _relative_delta(
                candidate_summary["mean_final_target_distance_m"],
                baseline["summary"]["mean_final_target_distance_m"],
            ),
            "mean_post_grasp_slip_relative": _relative_delta(
                candidate_summary["mean_post_grasp_slip_m"],
                baseline["summary"]["mean_post_grasp_slip_m"],
            ),
            "c2_bilateral_contact_loss_source_frame_delta": candidate_loss
            - baseline_loss,
            "c2_post_grasp_slip_relative_reduction": slip_reduction,
        },
        "task_advancement_gates": task_gates,
        "task_advancement_admitted": task_advancement_admitted,
        "mechanism_advancement_gates": mechanism_gates,
        "mechanism_advancement_admitted": mechanism_advancement_admitted,
        "simulator_promotion_admitted": False,
        "terminal_verdict": (
            "terminal_negative_for_bounded_contact_model_promotion_with_"
            "observability_and_diagnostic_metric_gains"
        ),
        "claim_boundary": config["proof_boundary"]["claim"],
    }
    verdict["verdict_digest"] = canonical_digest(verdict)

    output = (output_root or _resolve(root, config["output_root"])).resolve()
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "failure_inventory.json": inventory,
        "candidate_screen.json": {
            "schema_version": "sim2claw.sail_project_candidate_screen.v1",
            "candidates": candidate_rows,
            "selected_candidate": freeze["selected_family"]["candidate_id"],
            "selection_frozen_before_evaluation": True,
            "evaluation_is_fresh_holdout": False,
        },
        "belief_graph.json": belief_graph,
        "verdict.json": verdict,
    }
    for name, payload in artifacts.items():
        atomic_write_json(output / name, payload)
    artifact_bindings = {
        name: {"path": str(output / name), "sha256": sha256_file(output / name)}
        for name in sorted(artifacts)
    }
    receipt = {
        "schema_version": "sim2claw.sail_project_application_receipt.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "campaign_id": config["campaign_id"],
        "config": {"path": str(config_path.resolve()), "sha256": sha256_file(config_path)},
        "implementation": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "candidate_freeze": {
            "path": str(freeze_path.resolve()),
            "sha256": sha256_file(freeze_path),
            "frozen_before_evaluation": True,
        },
        "verified_sources": verified_sources,
        "additional_evidence": {
            "evaluation": {"path": str(evaluation_path), "sha256": sha256_file(evaluation_path)},
            "baseline_task_metrics_v2": {
                "path": str(baseline_metric_path),
                "sha256": sha256_file(baseline_metric_path),
            },
            "baseline_surface_witness": {
                "path": str(baseline_trace_path),
                "sha256": sha256_file(baseline_trace_path),
            },
            "candidate_surface_witness": {
                "path": str(candidate_trace_path),
                "sha256": sha256_file(candidate_trace_path),
            },
        },
        "artifacts": artifact_bindings,
        "counts": {
            "phase_1_milestones_applied": 18,
            "project_evidence_items_reconciled": inventory[
                "phase_1_application_surface"
            ]["retained_evidence_count"],
            "action_frozen_episodes": 11,
            "adaptive_candidate_composites_including_baseline": len(candidate_rows),
            "evaluation_episode_count": 8,
            "failure_classes": len(failure_counts),
        },
        "outcome": {
            "task_advancement_admitted": task_advancement_admitted,
            "mechanism_advancement_admitted": mechanism_advancement_admitted,
            "simulator_promotion_admitted": False,
            "training_admitted": False,
            "physical_authority": False,
            "terminal_verdict": verdict["terminal_verdict"],
        },
        "deterministic_tree_digest": canonical_digest(artifact_bindings),
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    atomic_write_json(output / "receipt.json", receipt)
    return receipt


def load_project_application_view(
    *, repository_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Load the compiled result for Studio without exposing mutable paths."""

    root = repository_root.resolve()
    output = root / "outputs" / "sail" / "project-application-v1"
    receipt_path = output / "receipt.json"
    receipt = _load_json(receipt_path)
    if receipt.get("schema_version") != "sim2claw.sail_project_application_receipt.v1":
        raise ProjectApplicationError("project application receipt schema drifted")
    loaded: dict[str, dict[str, Any]] = {}
    for name, binding in receipt["artifacts"].items():
        verified = _verify_binding(root, binding, f"project application {name}")
        loaded[name] = _load_json(Path(verified["path"]))
    verdict = loaded["verdict.json"]
    inventory = loaded["failure_inventory.json"]
    return {
        "available": True,
        "schema_version": "sim2claw.studio_project_application.v1",
        "read_only": True,
        "receipt_sha256": sha256_file(receipt_path),
        "receipt_digest": receipt["receipt_digest"],
        "terminal_verdict": verdict["terminal_verdict"],
        "task_advancement_admitted": verdict["task_advancement_admitted"],
        "mechanism_advancement_admitted": verdict["mechanism_advancement_admitted"],
        "diagnostic_deltas": verdict["diagnostic_deltas"],
        "failure_counts": inventory["failure_counts"],
        "resolved_inconsistencies": inventory["resolved_inconsistencies"],
        "unresolved_requirements": inventory["unresolved_requirements"],
        "authority": {
            "simulator_promotion": False,
            "training_admission": False,
            "physical_authority": False,
        },
    }
