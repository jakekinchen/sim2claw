from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from sim2claw.studio_server import create_server
from sim2claw.studio_twin_fidelity import (
    DOMAIN_ORDER,
    _hil_identifiability_projection,
    _overnight_calibration_projection,
    load_twin_fidelity_projection,
    project_twin_fidelity,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ACTION_SHA256 = "4" * 64


def _episode() -> dict[str, object]:
    return {
        "id": "selected-replay",
        "title": "Selected replay",
        "subtitle": "Action-frozen C2 replay",
        "action_array_sha256": ACTION_SHA256,
        "proof_class": "simulation_partial",
    }


def _observatory() -> dict[str, object]:
    return {
        "episodes": [
            {
                "id": "sail-episode",
                "action_array_sha256": ACTION_SHA256,
                "proof_class": "retained_action_frozen_simulation_partial",
                "proof_label": "Retained simulation · partial",
                "metrics": {
                    "joint_rms_degrees": 1.25,
                    "ee_rms_m": 0.011,
                    "final_target_distance_m": 0.01,
                },
                "availability": [
                    {"id": "pawn", "detail": "Physical pawn motion unavailable."},
                    {"id": "target", "detail": "Physical target unavailable."},
                    {"id": "timing", "detail": "Timing is phase-aligned."},
                    {"id": "contact", "detail": "Simulation contact only."},
                    {"id": "consequence", "detail": "Simulation consequence only."},
                ],
                "residual_cells": [
                    {
                        "channel": "selected_event_timing:near_closed_crossing",
                        "rmse": 1.45,
                    },
                    {
                        "channel": "selected_event_timing:release_onset",
                        "rmse": 0.152,
                    },
                ],
            }
        ],
        "twin_worthiness": {
            "level": "TW-REPLAY",
            "allowed_capabilities": ["diagnostics"],
            "denied_capabilities": ["training", "physical_authority"],
        },
    }


def _live_projection() -> dict[str, object]:
    receipt = {
        "action_sha256": ACTION_SHA256,
        "verdict": "evaluator_reject",
        "selected_intervention": "trusted_action_frozen_c2_factorial",
        "action_bytes_unchanged": True,
        "receipt_digest": "d" * 64,
        "budget": {"used_anchor_replays": 4},
    }
    outputs = {
        "residual_evidence": {"residuals": [{}, {}]},
        "mechanism_status": {
            "mechanisms": [
                {
                    "mechanism_id": "flexural_contact",
                    "family": "flexural contact",
                    "missing_observables": [
                        "jaw_force",
                        "rubber_cap_deformation_profile",
                    ],
                },
                {
                    "mechanism_id": "actuator_load_path",
                    "family": "actuator load path",
                    "missing_observables": ["jaw_force"],
                },
            ]
        },
        "acquisition_ranking": {
            "rows": [
                {
                    "kind": "measurement_acquisition",
                    "availability": "missing",
                    "intervention_id": "measurement_synchronized_force_deformation_probe",
                }
            ]
        },
        "posterior": {
            "before": {"flexural_contact": 0.5, "actuator_load_path": 0.5},
            "after": {"flexural_contact": 0.5, "actuator_load_path": 0.5},
            "observed_information_gain_bits": 0.0,
        },
        "consequence": {
            "status": "rejected_no_joint_mechanism_and_strict_task_ee_evidence",
            "strict_task_and_ee_pass_count": 0,
            "candidate_count": 4,
            "admitted_evaluator_owned_evidence": 0,
            "posterior_movement_permitted": False,
        },
    }
    evaluation = {
        "candidate_results": [
            {
                "candidate_id": "baseline",
                "anchor_evaluation": {
                    "trace_metrics": {
                        "overall_joint_rms_degrees": 1.2,
                        "ee_rms_m": 0.011,
                    }
                },
            }
        ],
        "main_effects": {
            "flexural_contact": 0.118,
            "actuator_load_path": -0.089,
        },
        "effect_evidence": {
            "flexural_contact": True,
            "actuator_load_path": True,
        },
    }
    return project_twin_fidelity(
        _episode(),
        _observatory(),
        live_receipt=receipt,
        live_outputs=outputs,
        live_verification={
            "receipt_sha256": "a" * 64,
            "campaign_state_sha256": "b" * 64,
        },
        adapter_evaluation=evaluation,
        adapter_thresholds={
            "maximum_joint_rms_degrees": 2.0,
            "maximum_ee_rms_m": 0.02,
        },
    )


def _overnight_bundle() -> dict[str, object]:
    authority = {
        "provider_advice_is_evaluator_evidence": False,
        "simulator_parameter_promotion": False,
        "task_score_change": False,
        "training": False,
        "physical_capture": False,
        "physical_motion": False,
    }
    return {
        "publication": {
            "source_recording_id": "recording-empty-gripper",
            "proof_classes": [
                "derived_empty_gripper_cycle_diagnostic",
                "action_frozen_simulator_joint_range_diagnostic",
            ],
            "diagnostic": {"receipt_sha256": "1" * 64},
            "comparison": {"receipt_sha256": "2" * 64},
        },
        "publication_sha256": "3" * 64,
        "diagnostic": {
            "sample_count": 911,
            "segmentation": {
                "observed_excursion_count": 6,
                "owner_intended_excursion_count": 5,
            },
            "owner_intended_five_cycle_sensitivity": {
                "summary": {
                    "median_best_gripper_lag_seconds": 0.15,
                    "median_lag_aligned_gripper_rmse_degrees": 1.02,
                }
            },
            "current_telemetry": {
                "maximum_raw_current_by_joint": [2, 1, 23, 4, 3, 8]
            },
            "authority": authority,
        },
        "diagnostic_receipt": {"receipt_sha256": "4" * 64},
        "raw_comparison": {
            "variants": [
                {
                    "variant_id": "current_declared_ranges",
                    "metrics": {
                        "aggregate_body_joint_rmse_degrees": 3.428,
                    },
                },
                {
                    "variant_id": "follower_calibrated_ranges_v1",
                    "metrics": {
                        "aggregate_body_joint_rmse_degrees": 2.280,
                    },
                },
            ]
        },
        "evaluation": {
            "evaluator_owner": "independent_cpu_fp32_joint_response_evaluator",
            "action_tensor_byte_identical": True,
            "aggregate_body_joint_rmse_improvement_fraction": 0.3349,
            "per_joint_rmse_regression_degrees": [
                0.002,
                -5.701,
                0.870,
                -0.758,
                0.0,
            ],
            "gates": {
                "action_identity": True,
                "aggregate_body_improvement": True,
                "per_joint_nonregression": False,
                "gripper_nonregression": False,
                "strict_task_consequence": False,
            },
            "verdict": "diagnostic_joint_range_tie_or_loss_no_promotion",
        },
        "identifiability": {
            "shoulder_lift_hypothesis": {
                "observed_command_span_degrees": 0.0,
                "joint_specific_range_scale_identified": False,
            },
            "elbow_hypothesis": {
                "observed_command_span_degrees": 10.02,
                "joint_specific_range_scale_identified": False,
            },
        },
        "comparison_receipt": {
            "receipt_sha256": "5" * 64,
            "exact_action_sha256": "6" * 64,
        },
        "identifiability_receipt": {"receipt_sha256": "7" * 64},
    }


def _physical_episode() -> dict[str, object]:
    return {
        "id": "physical-episode",
        "title": "Physical episode",
        "subtitle": "Empty gripper diagnostic",
        "source_recording_id": "recording-empty-gripper",
        "proof_class": "physical_teleoperation_source_unqualified",
        "proof_label": "Physical source · recorded, not admitted",
        "action_array_sha256": None,
    }


def _hil_episode(packet_id: str, action_sha256: str = ACTION_SHA256) -> dict[str, object]:
    return {
        "id": f"hil-{packet_id}",
        "title": packet_id,
        "subtitle": "Bounded HIL packet",
        "source_recording_id": packet_id,
        "proof_class": "physical_hil_unloaded_joint_observation",
        "proof_label": "Physical HIL",
        "action_array_sha256": action_sha256,
        "recording_feeds": [{"id": "overhead"}, {"id": "wrist"}],
    }


def _hil_bundle(
    packet_id: str,
    *,
    admitted: bool,
    failures: list[str] | None = None,
) -> dict[str, object]:
    failures = failures or []
    return {
        "publication": {
            "proof_classes": [
                "physical_hil_unloaded_joint_observation",
                "derived_hil_joint_identifiability_evaluation",
                "action_frozen_hil_simulator_comparison",
                "offline_hil_trace_identifiability_diagnostic",
            ],
            "physical": {
                "receipt_sha256": "1" * 64,
            },
            "simulator": {
                "receipt_sha256": "2" * 64,
            },
            "offline_analysis": {
                "receipt_sha256": "7" * 64,
            },
            "offline_decomposition": {
                "receipt_sha256": "9" * 64,
            },
        },
        "publication_sha256": "3" * 64,
        "evidence_receipt": {"receipt_digest": "4" * 64},
        "offline_analysis": {
            "report": {
                "packets": [
                    {
                        "packet_id": packet_id,
                        "action_tensor_sha256": ACTION_SHA256,
                        "sample_quantized_lag": {
                            "seconds": 0.15,
                            "is_not_command_application_latency": True,
                        },
                        "directional_tracking": {
                            "mean_residual_gap_degrees": 0.14,
                            "is_not_backlash_or_compliance_proof": True,
                        },
                        "plateau_scale_offset_diagnostic": {
                            "admissible_for_scale_offset_claim": False,
                        },
                        "reset_return_audit": {
                            "final_minus_initial_degrees": 0.59,
                            "is_single_packet_return_residual_not_reset_drift_proof": True,
                        },
                        "fresh_current_association": {
                            "correlation_absolute_current_to_absolute_error": 0.47,
                            "is_diagnostic_not_force_or_torque": True,
                        },
                        "safety": {
                            "stall_warning_sample_count": (
                                6
                                if packet_id == "HIL-ELBOW-FLEX-22"
                                else 0
                            ),
                        },
                    }
                ],
                "remaining_prerequisites": [
                    "independent_command_created_sent_and_actuator_ack_timestamps",
                    "strict_task_and_end_effector_consequence",
                ],
            },
            "receipt": {"receipt_digest": "8" * 64},
        },
        "offline_decomposition": {
            "report": {
                "packets": [
                    {
                        "packet_id": packet_id,
                        "action_identity": {
                            "requested_action_sha256": ACTION_SHA256,
                            "applied_action_byte_identical": (
                                packet_id == "HIL-SHOULDER-LIFT-22"
                            ),
                            "byte_modified_sample_count": (
                                0
                                if packet_id == "HIL-SHOULDER-LIFT-22"
                                else 11
                                if packet_id == "HIL-ELBOW-FLEX-22"
                                else 6
                                if packet_id == "HIL-WRIST-FLEX-30"
                                else 13
                            ),
                            "gateway_rate_limited_sample_count": (
                                11
                                if packet_id == "HIL-ELBOW-FLEX-22"
                                else 4
                                if packet_id == "HIL-WRIST-FLEX-30"
                                else 0
                            ),
                            "first_gateway_modified_sample": (
                                59
                                if packet_id == "HIL-ELBOW-FLEX-22"
                                else 101
                                if packet_id == "HIL-WRIST-FLEX-30"
                                else None
                            ),
                        },
                        "fault_chronology": {
                            "events": (
                                [
                                    {
                                        "event": "first_gateway_rate_limit",
                                        "sample_index": 59,
                                    },
                                    {
                                        "event": "first_stall_warning",
                                        "sample_index": 99,
                                    },
                                ]
                                if packet_id == "HIL-ELBOW-FLEX-22"
                                else []
                            ),
                            "pre_fault_best_lag": {
                                "lag_samples": (
                                    7
                                    if packet_id == "HIL-ELBOW-FLEX-22"
                                    else 3
                                ),
                            },
                        },
                    }
                ],
                "remaining_prerequisites": [
                    "device_or_actuator_application_ack_timestamp",
                    "controller_configuration_and_threshold_hashes",
                ],
            },
            "receipt": {"receipt_digest": "a" * 64},
        },
        "packets": [
            {
                "packet_id": packet_id,
                "event": {"evaluation_sha256": "5" * 64},
                "raw": {"action_tensor_sha256": ACTION_SHA256},
                "evaluation": {
                    "admitted": admitted,
                    "verdict": (
                        "admit_unloaded_joint_measurement"
                        if admitted
                        else "reject_packet"
                    ),
                    "failures": failures,
                    "evaluator_owner": "independent_hil_packet_evaluator",
                },
                "summary": {
                    "packet_id": packet_id,
                    "target_joint": (
                        "shoulder_lift"
                        if packet_id == "HIL-SHOULDER-LIFT-22"
                        else "elbow_flex"
                        if packet_id == "HIL-ELBOW-FLEX-22"
                        else "wrist_flex"
                        if packet_id == "HIL-WRIST-FLEX-30"
                        else "gripper"
                    ),
                    "sample_count": 201,
                    "requested_span_degrees": 22.0,
                    "actual_span_degrees": 21.6,
                    "failures": failures,
                    "tracking": {
                        "requested_to_actual_rmse": 1.3,
                        "requested_to_actual_best_lag": {
                            "lag_seconds": 0.15,
                            "lag_aligned_rmse": 0.64,
                        },
                    },
                    "current_raw": {"p95_absolute": 2.0, "maximum": 3.0},
                    "safety": {"stall_warning_sample_count": 0},
                    "cameras": {"wrist": {"status": "completed"}},
                },
            }
        ],
        "simulator": {
            "raw_comparison": {
                "baseline": {
                    "metrics": {
                        "aggregate_body_joint_rmse_degrees": 3.02,
                    }
                },
                "candidate": {
                    "metrics": {
                        "aggregate_body_joint_rmse_degrees": 2.63,
                    }
                },
            },
            "evaluation": {
                "evaluator_owner": "independent_cpu_fp32_hil_joint_response_evaluator",
                "verdict": "diagnostic_shoulder_range_external_tie_or_loss_no_promotion",
                "action_tensor_byte_identical": True,
                "baseline_target_joint_rmse_degrees": 4.289,
                "candidate_target_joint_rmse_degrees": 1.281,
                "body_joint_rmse_regression_degrees": [0, -3.008, 0.511, 0, 0],
                "target_improvement_gate_passed": True,
                "non_target_regression_gate_passed": False,
                "gripper_nonregression_gate_passed": True,
            },
            "receipt": {"receipt_digest": "6" * 64},
        },
    }


def test_projection_orders_domains_and_keeps_missing_distinct_from_failed() -> None:
    projection = _live_projection()
    assert projection["available"] is True
    assert projection["evidence_status"] == "terminal_negative"
    assert projection["summary"]["verdict"] == "evaluator_reject"
    assert [row["id"] for row in projection["domains"]] == [
        row[0] for row in DOMAIN_ORDER
    ]
    statuses = {row["id"]: row["status"] for row in projection["domains"]}
    assert statuses["geometry_scale"] == "missing"
    assert statuses["contact_compliance"] == "missing"
    assert statuses["task_ee_consequence"] == "failed"
    strict = projection["domains"][-1]["measurements"][0]
    assert strict["value"] == 0
    assert strict["observed"] is True
    assert "percentage" not in json.dumps(projection).lower()
    assert "score" not in projection


def test_hil_gripper_projection_admits_only_unloaded_measurement() -> None:
    projection = _hil_identifiability_projection(
        _hil_episode("HIL-GRIPPER-05"),
        _hil_bundle("HIL-GRIPPER-05", admitted=True),
    )
    assert projection["available"] is True
    assert projection["evidence_status"] == (
        "physical_measurement_admitted_no_task_authority"
    )
    assert (
        projection["episode"]["action_binding"]
        == "hash_bound_requested_physical_packet"
    )
    statuses = {row["id"]: row["status"] for row in projection["domains"]}
    assert statuses["kinematics"] == "observed"
    assert statuses["contact_compliance"] == "missing"
    assert statuses["task_ee_consequence"] == "missing"
    assert projection["authority"]["simulator_promotion"] is False
    assert "0/11" in projection["domains"][-1]["detail"]
    assert any(
        row["label"] == "Directional residual gap"
        for row in projection["domains"][1]["measurements"]
    )
    assert any(
        row["label"] == "Current ↔ absolute error correlation"
        for row in projection["domains"][4]["measurements"]
    )
    assert (
        "independent_command_created_sent_and_actuator_ack_timestamps"
        in projection["next_evidence"]["measurements"]
    )
    assert projection["receipt"]["offline_analysis_receipt_digest"] == "8" * 64
    assert projection["receipt"]["offline_decomposition_receipt_digest"] == (
        "a" * 64
    )
    assert projection["domains"][2]["status"] == "failed"
    assert "applied action differed" in projection["domains"][2][
        "summary"
    ].lower()
    assert "perfect simulation" not in json.dumps(projection).lower()


def test_hil_shoulder_projection_reports_gain_and_failed_elbow_gate() -> None:
    projection = _hil_identifiability_projection(
        _hil_episode("HIL-SHOULDER-LIFT-22"),
        _hil_bundle("HIL-SHOULDER-LIFT-22", admitted=True),
    )
    assert projection["domains"][1]["status"] == "failed"
    assert projection["evaluator"]["gates"]["target_improvement"] is True
    assert projection["evaluator"]["gates"]["non_target_nonregression"] is False
    assert "candidate rejected" in projection["summary"]["label"].lower()
    assert projection["intervention"]["action_bytes_unchanged"] is True
    assert projection["evaluator"]["posterior_movement_permitted"] is False


def test_hil_rejected_packet_and_action_mismatch_fail_closed() -> None:
    rejected = _hil_identifiability_projection(
        _hil_episode("HIL-ELBOW-FLEX-22"),
        _hil_bundle(
            "HIL-ELBOW-FLEX-22",
            admitted=False,
            failures=["stall_observed"],
        ),
    )
    assert rejected["evidence_status"] == "physical_packet_rejected"
    assert rejected["domains"][1]["status"] == "failed"
    assert "first gateway rate limit @ 59" in rejected["domains"][4][
        "detail"
    ]
    assert "correlation, not causality" in rejected["domains"][4]["detail"]
    assert rejected["evaluator"]["admitted_evaluator_owned_evidence"] == 0
    mismatch = _hil_identifiability_projection(
        _hil_episode("HIL-GRIPPER-05", action_sha256="9" * 64),
        _hil_bundle("HIL-GRIPPER-05", admitted=True),
    )
    assert mismatch["available"] is False
    assert mismatch["reason"] == "hil_action_hash_mismatch"
    assert mismatch["chain"] == []
    missing_analysis = _hil_bundle("HIL-GRIPPER-05", admitted=True)
    missing_analysis["offline_analysis"]["report"]["packets"] = []
    unavailable = _hil_identifiability_projection(
        _hil_episode("HIL-GRIPPER-05"),
        missing_analysis,
    )
    assert unavailable["available"] is False
    assert unavailable["reason"] == "hil_offline_analysis_packet_missing"
    missing_decomposition = _hil_bundle("HIL-GRIPPER-05", admitted=True)
    missing_decomposition["offline_decomposition"]["report"]["packets"] = []
    unavailable = _hil_identifiability_projection(
        _hil_episode("HIL-GRIPPER-05"),
        missing_decomposition,
    )
    assert unavailable["available"] is False
    assert unavailable["reason"] == "hil_offline_decomposition_packet_missing"


def test_terminal_negative_keeps_posterior_and_authority_closed() -> None:
    projection = _live_projection()
    assert "Posterior belief remained unchanged" in projection["summary"]["detail"]
    assert projection["evaluator"]["observed_information_gain_bits"] == 0.0
    assert {row["status"] for row in projection["hypotheses"]} == {"unchanged"}
    assert projection["next_evidence"]["status"] == "missing"
    assert projection["authority"] == {
        "read_only": True,
        "training_admitted": False,
        "simulator_promotion": False,
        "physical_capture": False,
        "physical_authority": False,
        "robot_motion": False,
    }


def test_action_mismatch_does_not_attach_terminal_campaign_claims() -> None:
    projection = _live_projection()
    mismatched = project_twin_fidelity(
        {**_episode(), "action_array_sha256": "5" * 64},
        {
            **_observatory(),
            "episodes": [
                {
                    **_observatory()["episodes"][0],
                    "action_array_sha256": "5" * 64,
                }
            ],
        },
        live_receipt={"action_sha256": ACTION_SHA256},
        live_outputs={"posterior": {"before": {}, "after": {}}},
        live_verification={"receipt_sha256": "a" * 64},
        adapter_evaluation={"candidate_results": []},
    )
    assert projection["episode"]["action_binding"] == "byte_identical_campaign_match"
    assert mismatched["evidence_status"] == "episode_evidence_only"
    assert mismatched["receipt"]["verification"] == "unavailable"
    assert mismatched["evaluator"]["verdict"] is None


def test_same_episode_id_with_different_action_hash_is_unavailable() -> None:
    selected = {**_episode(), "id": "shared-episode", "action_array_sha256": "5" * 64}
    observatory = {
        **_observatory(),
        "episodes": [
            {
                **_observatory()["episodes"][0],
                "id": "shared-episode",
                "action_array_sha256": "6" * 64,
            }
        ],
    }
    projection = project_twin_fidelity(selected, observatory)
    assert projection["available"] is False
    assert projection["reason"] == "action_hash_not_in_receipt_bound_observatory"
    assert "episode-ID fallback is prohibited" in projection["detail"]
    assert projection["chain"] == []
    assert projection["hypotheses"] == []
    assert {row["status"] for row in projection["domains"]} == {"missing"}


def test_episode_id_fallback_is_explicit_when_selected_action_hash_is_absent() -> None:
    selected = {**_episode(), "action_array_sha256": None, "id": "sail-episode"}
    projection = project_twin_fidelity(selected, _observatory())
    assert projection["available"] is True
    assert (
        projection["episode"]["action_binding"]
        == "episode_id_only_action_hash_unavailable"
    )
    assert "episode ID only; action hash unavailable" in projection["episode"][
        "proof_label"
    ]


def test_invalid_observatory_receipt_fails_projection_closed() -> None:
    with patch(
        "sim2claw.studio_twin_fidelity.load_studio_observatory",
        side_effect=ValueError("observatory receipt digest changed"),
    ):
        projection = load_twin_fidelity_projection(_episode(), repo_root=REPO_ROOT)
    assert projection["available"] is False
    assert projection["reason"] == "sail_observatory_unavailable"
    assert {row["status"] for row in projection["domains"]} == {"missing"}
    assert "summary" not in projection


def test_invalid_live_receipt_never_synthesizes_terminal_claims() -> None:
    with (
        patch(
            "sim2claw.studio_twin_fidelity.load_studio_observatory",
            return_value=_observatory(),
        ),
        patch(
            "sim2claw.studio_twin_fidelity._load_live_bundle",
            side_effect=ValueError("live receipt output changed"),
        ),
    ):
        projection = load_twin_fidelity_projection(_episode(), repo_root=REPO_ROOT)
    assert projection["available"] is True
    assert projection["evidence_status"] == "episode_evidence_only"
    assert projection["summary"]["verdict"] == "no_action_matched_terminal_campaign"
    assert "live receipt output changed" in projection["summary"]["detail"]
    assert projection["evaluator"]["verdict"] is None
    assert projection["hypotheses"] == []


def test_overnight_calibration_projection_is_explicitly_rejected_and_partial() -> None:
    projection = _overnight_calibration_projection(
        _physical_episode(), _overnight_bundle()
    )
    assert projection["available"] is True
    assert projection["evidence_status"] == "terminal_diagnostic_no_promotion"
    assert "candidate rejected" in projection["summary"]["label"].lower()
    assert "33.5%" in projection["summary"]["detail"]
    assert projection["episode"]["action_sha256"] == "6" * 64
    assert (
        projection["episode"]["action_binding"]
        == "source_recording_plus_hash_bound_command_tensor"
    )
    statuses = {row["id"]: row["status"] for row in projection["domains"]}
    assert statuses == {
        "geometry_scale": "missing",
        "kinematics": "failed",
        "action_timing": "observed",
        "contact_compliance": "missing",
        "actuator_load_path": "missing",
        "task_ee_consequence": "missing",
    }
    assert projection["evaluator"]["gates"]["aggregate_body_improvement"] is True
    assert projection["evaluator"]["gates"]["per_joint_nonregression"] is False
    assert projection["evaluator"]["posterior_movement_permitted"] is False
    kinematics = next(
        row for row in projection["domains"] if row["id"] == "kinematics"
    )
    shoulder_span = next(
        row
        for row in kinematics["measurements"]
        if row["label"] == "Shoulder-lift command span"
    )
    assert shoulder_span["value"] == 0
    assert shoulder_span["threshold"] == 15
    assert projection["authority"]["simulator_promotion"] is False
    assert "perfect simulation" not in json.dumps(projection).lower()


def test_matching_physical_episode_with_invalid_publication_fails_closed() -> None:
    with (
        patch(
            "sim2claw.studio_twin_fidelity.load_overnight_calibration_binding",
            return_value={"source_recording_id": "recording-empty-gripper"},
        ),
        patch(
            "sim2claw.studio_twin_fidelity.verify_overnight_calibration_publication",
            side_effect=ValueError("comparison evaluation hash changed"),
        ),
    ):
        projection = load_twin_fidelity_projection(
            _physical_episode(), repo_root=REPO_ROOT
        )
    assert projection["available"] is False
    assert projection["reason"] == "overnight_calibration_publication_unavailable"
    assert "comparison evaluation hash changed" in projection["detail"]
    assert {row["status"] for row in projection["domains"]} == {"missing"}
    assert projection["chain"] == []
    assert projection["hypotheses"] == []


def test_server_projects_selected_episode_through_read_only_endpoint(
    tmp_path: Path,
) -> None:
    expected = _live_projection()
    with (
        patch(
            "sim2claw.studio_server.build_catalog",
            return_value={"episodes": [_episode()]},
        ),
        patch(
            "sim2claw.studio_server.load_twin_fidelity_projection",
            return_value=expected,
        ) as loader,
        patch(
            "sim2claw.studio_server.evaluate_twin_fidelity_closure",
            return_value={
                "schema_version": "sim2claw.twin_fidelity_closure_report.v1",
                "available": True,
                "status": "not_perfect",
                "perfect": False,
                "closure": {
                    "passed_required_domains": 0,
                    "required_domain_count": 6,
                    "weighted_percentage": None,
                    "unknown_counted_as_zero": False,
                },
                "domains": [],
            },
        ) as closure_loader,
    ):
        server = create_server("127.0.0.1", 0, repo_root=tmp_path, read_only=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urlopen(
                f"{base}/api/twin-fidelity?episode_id=selected-replay"
            ) as response:
                observed = json.load(response)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
    assert observed["closure"]["closure"]["required_domain_count"] == 6
    assert observed["closure"]["perfect"] is False
    loader.assert_called_once()
    closure_loader.assert_called_once()


def test_replay_owns_twin_fidelity_navigation_and_read_only_drawer() -> None:
    html = (REPO_ROOT / "src/sim2claw/studio_web/index.html").read_text()
    css = (REPO_ROOT / "src/sim2claw/studio_web/studio.css").read_text()
    js = (REPO_ROOT / "src/sim2claw/studio_web/studio.js").read_text()

    nav = html.split('<nav class="view-switch"', 1)[1].split("</nav>", 1)[0]
    drawer = html.split('id="twin-fidelity-drawer"', 1)[1].split("</aside>", 1)[0]
    assert "/learning-factory.html" not in nav
    assert (REPO_ROOT / "src/sim2claw/studio_web/learning-factory.html").is_file()
    assert 'id="twin-fidelity-trigger"' in html
    assert 'aria-controls="twin-fidelity-drawer"' in html
    assert 'id="twin-fidelity-content"' in html
    assert "<form" not in drawer
    assert "fetch(`/api/twin-fidelity?episode_id=" in js
    assert '"Requested action hash bound"' in js
    assert '"Evaluator closure"' in js
    assert "Explicit denominator · no weighted percentage" in js
    assert "projection.closure" in js
    assert ".twin-closure-list" in css
    assert 'event.key === "Escape" && state.drawer' in js
    assert "trigger?.focus({ preventScroll: true })" in js
    assert "@media (max-width: 620px)" in css
    assert ".twin-domain.is-missing" in css
    assert ".twin-domain.is-failed" in css
