"""Independent CPU/fp32 consequence evaluation for trusted C2 adapter output."""

from __future__ import annotations

import copy
from typing import Any, Mapping, Sequence

import numpy as np

from ..learning_factory_artifacts import canonical_digest
from .grasp_retention_resolution import _anchor_result
from .live_types import LiveOperatorError


EVALUATION_SCHEMA = "sim2claw.sail_c2_consequence_evaluation.v1"


def _score_candidate(
    *,
    anchor: Mapping[str, Any],
    baseline_slip_m: float,
    thresholds: Mapping[str, Any],
) -> float:
    weights = thresholds["mechanism_score_weights"]
    retention = min(
        1.0,
        float(anchor["bilateral_lift_retention_seconds"])
        / float(thresholds["retention_seconds_normalization"]),
    )
    aperture = max(
        0.0,
        1.0
        - float(anchor["absolute_loaded_aperture_bias_degrees"])
        / float(thresholds["maximum_absolute_loaded_aperture_bias_degrees"]),
    )
    slip = (
        0.0
        if baseline_slip_m <= 0.0
        else max(
            -1.0,
            min(
                1.0,
                (
                    baseline_slip_m - float(anchor["post_grasp_slip_m"])
                )
                / baseline_slip_m,
            ),
        )
    )
    ee = max(
        0.0,
        1.0
        - float(anchor["trace_metrics"]["ee_rms_m"])
        / float(thresholds["maximum_ee_rms_m"]),
    )
    values = {
        "retention": retention,
        "loaded_aperture": aperture,
        "slip_reduction": slip,
        "task_consequence": float(bool(anchor["lift_and_transport"])),
        "ee_consequence": ee,
    }
    return float(
        np.float32(
            sum(
                np.float32(float(weights[name]))
                * np.float32(float(values[name]))
                for name in sorted(weights)
            )
        )
    )


def _main_effects(
    rows: Sequence[Mapping[str, Any]],
    *,
    axes: Sequence[str],
) -> dict[str, float]:
    effects: dict[str, float] = {}
    for axis in axes:
        enabled = [
            np.float32(float(row["mechanism_score"]))
            for row in rows
            if bool(row["axis_levels"][axis])
        ]
        disabled = [
            np.float32(float(row["mechanism_score"]))
            for row in rows
            if not bool(row["axis_levels"][axis])
        ]
        if len(enabled) != len(disabled) or not enabled:
            raise LiveOperatorError(
                "C2 adapter family is not a balanced frozen factorial"
            )
        effects[axis] = float(
            np.float32(np.mean(enabled, dtype=np.float32))
            - np.float32(np.mean(disabled, dtype=np.float32))
        )
    return effects


def evaluate_c2_family(
    *,
    contract: Mapping[str, Any],
    raw_receipts: Mapping[str, Mapping[str, Any]],
    affected_factor_ids: Sequence[str],
) -> dict[str, Any]:
    """Independently derive mechanism and strict task/EE consequences."""

    if sorted(str(value) for value in affected_factor_ids) != sorted(
        str(value) for value in contract["affected_factor_scope"]
    ):
        raise LiveOperatorError("C2 adapter affected-factor scope changed")
    candidates = contract["frozen_candidate_family"]
    expected_ids = [str(row["candidate_id"]) for row in candidates]
    if set(raw_receipts) != set(expected_ids):
        raise LiveOperatorError("C2 adapter raw candidate inventory changed")
    baseline_id = str(contract["factorial_design"]["baseline_candidate_id"])
    if baseline_id != expected_ids[0]:
        raise LiveOperatorError("C2 adapter baseline identity changed")
    expected_action = str(contract["diagnosis_anchor"]["action_array_sha256"])
    recording_id = str(contract["diagnosis_anchor"]["recording_id"])
    baseline_receipt = raw_receipts[baseline_id]
    baseline_episode = baseline_receipt["episode"]
    baseline_slip_m = float(baseline_episode["maximum_post_grasp_slip_m"])
    thresholds = contract["consequence_thresholds"]
    axes = [str(value) for value in contract["factorial_design"]["axes"]]

    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = str(candidate["candidate_id"])
        receipt = raw_receipts[candidate_id]
        unsigned_receipt = copy.deepcopy(dict(receipt))
        observed_receipt_digest = unsigned_receipt.pop("receipt_digest", None)
        parameters = copy.deepcopy(dict(contract["base_parameters"]))
        parameters.update(candidate["overrides"])
        episode = receipt.get("episode") or {}
        if (
            receipt.get("schema_version")
            != "sim2claw.pawn_bg_grasp_episode_probe.v1"
            or receipt.get("recording_id") != recording_id
            or receipt.get("parameters") != parameters
            or receipt.get("parameter_digest") != canonical_digest(parameters)
            or observed_receipt_digest != canonical_digest(unsigned_receipt)
            or episode.get("action_array_sha256") != expected_action
            or episode.get("action_byte_identical") is not True
        ):
            raise LiveOperatorError(
                f"C2 adapter raw simulator identity changed: {candidate_id}"
            )
        anchor = _anchor_result(
            episode=episode,
            contract=dict(contract),
            baseline_slip_m=baseline_slip_m,
        )
        ee_rms = float(anchor["trace_metrics"]["ee_rms_m"])
        joint_rms = float(anchor["trace_metrics"]["overall_joint_rms_degrees"])
        ee_consequence_passed = (
            np.isfinite(ee_rms)
            and np.isfinite(joint_rms)
            and ee_rms <= float(thresholds["maximum_ee_rms_m"])
            and joint_rms
            <= float(thresholds["maximum_joint_rms_degrees"])
        )
        task_consequence_passed = (
            anchor["status"] == "anchor_pass"
            and anchor["lift_and_transport"] is True
            and anchor["piece_lifted"] is True
            and anchor["bilateral_lift_retention"] is True
            and anchor["contact_retained_through_release_onset"] is True
        )
        strict_passed = task_consequence_passed and ee_consequence_passed
        rows.append(
            {
                "candidate_id": candidate_id,
                "axis_levels": copy.deepcopy(candidate["axis_levels"]),
                "action_sha256": anchor["action_sha256"],
                "action_byte_identical": True,
                "mechanism_score": _score_candidate(
                    anchor=anchor,
                    baseline_slip_m=baseline_slip_m,
                    thresholds=thresholds,
                ),
                "task_consequence_passed": task_consequence_passed,
                "ee_consequence_passed": ee_consequence_passed,
                "strict_task_and_ee_passed": strict_passed,
                "diagnostic_only": ee_consequence_passed
                and not task_consequence_passed,
                "anchor_evaluation": anchor,
            }
        )

    main_effects = _main_effects(rows, axes=axes)
    minimum_effect = float(
        contract["posterior_update_rule"][
            "minimum_absolute_main_effect_for_mechanism_evidence"
        ]
    )
    effect_evidence = {
        axis: abs(value) >= minimum_effect
        for axis, value in main_effects.items()
    }
    mechanism_evidence_present = any(effect_evidence.values())
    strict_candidates = [
        row for row in rows if row["strict_task_and_ee_passed"]
    ]
    admitted = bool(strict_candidates) and mechanism_evidence_present
    selected = (
        max(
            strict_candidates,
            key=lambda row: (
                float(row["mechanism_score"]),
                -float(
                    row["anchor_evaluation"]["trace_metrics"]["ee_rms_m"]
                ),
                str(row["candidate_id"]),
            ),
        )
        if admitted
        else None
    )

    hypothesis_axes = contract["posterior_update_rule"]["hypothesis_axis"]
    if admitted:
        total_effect = sum(abs(value) for value in main_effects.values())
        likelihoods = {
            str(hypothesis): float(
                np.float32(0.5)
                + np.float32(0.5)
                * np.float32(abs(main_effects[str(axis)]) / total_effect)
            )
            for hypothesis, axis in hypothesis_axes.items()
        }
    else:
        likelihoods = {
            str(hypothesis): 1.0 for hypothesis in hypothesis_axes
        }
    factor_updates = (
        {
            str(factor_id): float(selected["mechanism_score"])
            for factor_id in affected_factor_ids
        }
        if selected is not None
        else {}
    )
    consequence = {
        "status": (
            "strict_task_ee_and_mechanism_evidence_admitted"
            if admitted
            else "rejected_no_joint_mechanism_and_strict_task_ee_evidence"
        ),
        "evaluator_passed": admitted,
        "admitted_evaluator_owned_evidence": admitted,
        "selected_candidate_id": (
            None if selected is None else selected["candidate_id"]
        ),
        "candidate_count": len(rows),
        "strict_task_and_ee_pass_count": len(strict_candidates),
        "mechanism_evidence_present": mechanism_evidence_present,
        "posterior_movement_permitted": admitted,
        "lower_rms_alone_is_diagnostic": True,
        "evaluator_arithmetic": "numpy_cpu_float32",
        "promotion": False,
        "simulator_promotion": False,
        "training_admitted": False,
        "physical_authority": False,
        "robot_motion": False,
    }
    unsigned = {
        "schema_version": EVALUATION_SCHEMA,
        "proof_class": "retained_action_frozen_simulator_family_evidence",
        "recording_id": recording_id,
        "action_sha256": expected_action,
        "action_bytes_unchanged": all(
            row["action_sha256"] == expected_action
            and row["action_byte_identical"] is True
            for row in rows
        ),
        "candidate_results": rows,
        "main_effects": main_effects,
        "effect_evidence": effect_evidence,
        "hypothesis_likelihoods": likelihoods,
        "factor_updates": factor_updates,
        "consequence": consequence,
        "authority": copy.deepcopy(contract["authority"]),
    }
    return {**unsigned, "evaluation_digest": canonical_digest(unsigned)}


__all__ = ["EVALUATION_SCHEMA", "evaluate_c2_family"]
