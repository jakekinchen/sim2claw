"""Deterministic runtime helpers for corrective-intervention evaluation.

These helpers stop at branch execution and proposal scoring.  They do not claim
the required full-prefix replay, adapt rows, admit training data, or promote a
policy; those remain owned by the existing LF-12/LF-09 evaluator path.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import mujoco
import numpy as np

from .corrective_intervention import (
    POSTERIOR_SCHEMA,
    PROPOSAL_SCORE_SCHEMA,
    SAMPLE_HZ,
    CorrectiveInterventionError,
    seal_artifact,
    validate_compiled_trajectory,
    validate_proposal_score,
    validate_robustness_posterior,
    verify_sealed_artifact,
)
from .learning_factory_artifacts import canonical_digest
from .scene import ROBOT_JOINTS


BRANCH_STATE_SCHEMA = "sim2claw.corrective_branch_state.v1"
BRANCH_REPLAY_SCHEMA = "sim2claw.corrective_branch_replay.v1"
ROBUSTNESS_RECEIPT_SCHEMA = "sim2claw.corrective_robustness_receipt.v1"
PHYSICS_STEPS_PER_ACTION = 10


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CorrectiveInterventionError(message)


def _integration_state(model: mujoco.MjModel, data: mujoco.MjData) -> list[float]:
    size = mujoco.mj_stateSize(model, mujoco.mjtState.mjSTATE_INTEGRATION)
    state = np.empty(size, dtype=np.float64)
    mujoco.mj_getState(model, data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
    _require(np.isfinite(state).all(), "MuJoCo integration state is non-finite")
    return state.astype(float).tolist()


def _actuator_ids(model: mujoco.MjModel, arm: str) -> list[int]:
    ids: list[int] = []
    for joint in ROBOT_JOINTS:
        actuator_id = mujoco.mj_name2id(
            model,
            mujoco.mjtObj.mjOBJ_ACTUATOR,
            f"{arm}_{joint}",
        )
        _require(actuator_id >= 0, f"missing {arm} actuator: {joint}")
        ids.append(actuator_id)
    return ids


def capture_branch_state(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    *,
    scene_id: str,
    initial_action_rad: Sequence[float],
) -> dict[str, Any]:
    """Seal evaluator-only state without making it proposer-visible."""

    action = np.asarray(initial_action_rad, dtype=np.float64)
    _require(action.shape == (6,) and np.isfinite(action).all(), "initial action must be a finite six-vector")
    payload = {
        "schema_version": BRANCH_STATE_SCHEMA,
        "scene_id": scene_id,
        "mj_state_spec": "mjSTATE_INTEGRATION",
        "integration_state_float64": _integration_state(model, data),
        "initial_action_rad": action.astype(float).tolist(),
        "authority": {
            "evaluator_only": True,
            "policy_adapter_access": False,
            "proposer_access": False,
            "physical_authority": False,
        },
    }
    return seal_artifact(payload)


def restore_branch_state(
    model: mujoco.MjModel,
    branch_state: Mapping[str, Any],
) -> mujoco.MjData:
    """Restore and byte-for-byte verify one sealed MuJoCo integration state."""

    state = verify_sealed_artifact(branch_state)
    expected_keys = {
        "schema_version",
        "scene_id",
        "mj_state_spec",
        "integration_state_float64",
        "initial_action_rad",
        "authority",
        "artifact_sha256",
    }
    _require(set(state) == expected_keys, "branch state keys differ")
    _require(state["schema_version"] == BRANCH_STATE_SCHEMA, "unsupported branch state schema")
    _require(state["mj_state_spec"] == "mjSTATE_INTEGRATION", "branch state uses another MuJoCo state spec")
    authority = state["authority"]
    _require(
        authority
        == {
            "evaluator_only": True,
            "policy_adapter_access": False,
            "proposer_access": False,
            "physical_authority": False,
        },
        "branch state authority changed",
    )
    expected_size = mujoco.mj_stateSize(model, mujoco.mjtState.mjSTATE_INTEGRATION)
    values = np.asarray(state["integration_state_float64"], dtype=np.float64)
    _require(values.shape == (expected_size,) and np.isfinite(values).all(), "branch integration state shape or values changed")
    data = mujoco.MjData(model)
    mujoco.mj_setState(model, data, values, mujoco.mjtState.mjSTATE_INTEGRATION)
    mujoco.mj_forward(model, data)
    restored = np.asarray(_integration_state(model, data), dtype=np.float64)
    _require(np.array_equal(restored, values), "MuJoCo branch state did not restore exactly")
    return data


def run_compiled_branch(
    model: mujoco.MjModel,
    *,
    branch_state: Mapping[str, Any],
    compiled_trajectory: Mapping[str, Any],
    scene_id: str,
    arm: str = "left",
    consequence_observer: Callable[[mujoco.MjModel, mujoco.MjData, int], Mapping[str, float | bool]] | None = None,
) -> dict[str, Any]:
    """Execute one suffix branch while preserving its narrow proof boundary."""

    state = verify_sealed_artifact(branch_state)
    compiled = validate_compiled_trajectory(compiled_trajectory)
    _require(state["scene_id"] == scene_id, "branch state scene identity mismatch")
    _require(compiled["branch_state_sha256"] == state["artifact_sha256"], "compiled trajectory references another branch state")
    _require(
        np.array_equal(
            np.asarray(compiled["initial_action_rad"], dtype=np.float64),
            np.asarray(state["initial_action_rad"], dtype=np.float64),
        ),
        "compiled trajectory initial action differs from branch state",
    )
    data = restore_branch_state(model, state)
    actuator_ids = _actuator_ids(model, arm)
    data.ctrl[actuator_ids] = np.asarray(state["initial_action_rad"], dtype=np.float64)
    action_trace: list[dict[str, Any]] = []
    consequence_rows: list[dict[str, float | bool]] = []
    for sample_index, action_value in enumerate(compiled["actions_rad"]):
        action = np.asarray(action_value, dtype=np.float32)
        data.ctrl[actuator_ids] = action.astype(np.float64)
        for _ in range(PHYSICS_STEPS_PER_ACTION):
            mujoco.mj_step(model, data)
        state_after = _integration_state(model, data)
        action_trace.append(
            {
                "sample_index": sample_index,
                "action_float32": action.astype(float).tolist(),
                "integration_state_sha256": canonical_digest(
                    {
                        "mj_state_spec": "mjSTATE_INTEGRATION",
                        "integration_state_float64": state_after,
                    }
                ),
            }
        )
        observed = (
            dict(consequence_observer(model, data, sample_index))
            if consequence_observer is not None
            else {}
        )
        for name, value in observed.items():
            _require(isinstance(name, str) and name, "consequence name is invalid")
            _require(type(value) is bool or (type(value) in {int, float} and math.isfinite(float(value))), "consequence value is invalid")
        consequence_rows.append(observed)

    final_state = _integration_state(model, data)
    receipt_unsigned = {
        "schema_version": BRANCH_REPLAY_SCHEMA,
        "scene_id": scene_id,
        "branch_state_sha256": state["artifact_sha256"],
        "compiled_trajectory_sha256": canonical_digest(compiled),
        "exact_branch_state_restored": True,
        "sample_hold_hz": SAMPLE_HZ,
        "physics_steps_per_action": PHYSICS_STEPS_PER_ACTION,
        "action_count": len(action_trace),
        "action_trace_sha256": canonical_digest(action_trace),
        "consequence_trace_sha256": canonical_digest(consequence_rows),
        "final_integration_state_sha256": canonical_digest(
            {
                "mj_state_spec": "mjSTATE_INTEGRATION",
                "integration_state_float64": final_state,
            }
        ),
        "authority": {
            "branch_only_diagnostic": True,
            "full_prefix_plus_suffix_replay_passed": False,
            "training_admitted": False,
            "promotion_authority": False,
            "physical_authority": False,
        },
    }
    receipt = seal_artifact(receipt_unsigned)
    return {
        "receipt": receipt,
        "action_trace": action_trace,
        "consequence_trace": consequence_rows,
        "final_integration_state_float64": final_state,
    }


def sample_robustness_posterior(
    posterior: Mapping[str, Any],
    *,
    split: str = "development",
) -> list[dict[str, Any]]:
    """Sample deterministically by seed; no global RNG or adaptive leakage."""

    normalized = validate_robustness_posterior(posterior)
    _require(split in {"development", "sealed"}, "posterior split must be development or sealed")
    seeds = normalized[f"{split}_seeds"]
    rows: list[dict[str, Any]] = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        parameters: dict[str, float] = {}
        for parameter in sorted(normalized["parameters"], key=lambda row: row["name"]):
            if parameter["distribution"] == "uniform":
                value = rng.uniform(parameter["lower"], parameter["upper"])
            else:
                value = np.clip(
                    rng.normal(parameter["nominal"], parameter["stddev"]),
                    parameter["lower"],
                    parameter["upper"],
                )
            parameters[parameter["name"]] = float(value)
        rows.append(
            {
                "seed": seed,
                "split": split,
                "posterior_sha256": canonical_digest(normalized),
                "parameters": parameters,
            }
        )
    return rows


def run_posterior_robustness(
    posterior: Mapping[str, Any],
    *,
    trial_runner: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    split: str = "development",
) -> dict[str, Any]:
    """Run an injected simulator/evaluator trial for every frozen posterior row.

    Parameter application remains explicit in ``trial_runner`` so unsupported
    MuJoCo mutations cannot be silently invented by this orchestration layer.
    """

    normalized = validate_robustness_posterior(posterior)
    samples = sample_robustness_posterior(normalized, split=split)
    results: list[dict[str, Any]] = []
    for sample in samples:
        raw = trial_runner(copy.deepcopy(sample))
        _require(isinstance(raw, Mapping), "posterior trial result must be an object")
        expected_keys = {
            "strict_success",
            "safety_violations",
            "policy_consequence_reward",
            "consequence_sha256",
        }
        _require(set(raw) == expected_keys, "posterior trial result keys differ")
        _require(type(raw["strict_success"]) is bool, "posterior trial strict_success must be boolean")
        _require(type(raw["safety_violations"]) is int and raw["safety_violations"] >= 0, "posterior trial safety count is invalid")
        _require(type(raw["policy_consequence_reward"]) in {int, float} and math.isfinite(float(raw["policy_consequence_reward"])), "posterior trial reward is invalid")
        digest = raw["consequence_sha256"]
        _require(isinstance(digest, str) and len(digest) == 64, "posterior trial consequence digest is invalid")
        try:
            int(digest, 16)
        except ValueError as error:
            raise CorrectiveInterventionError("posterior trial consequence digest is not hexadecimal") from error
        results.append(
            {
                **sample,
                "strict_success": raw["strict_success"],
                "safety_violations": raw["safety_violations"],
                "policy_consequence_reward": float(raw["policy_consequence_reward"]),
                "consequence_sha256": digest.lower(),
            }
        )
    success_count = sum(int(row["strict_success"]) for row in results)
    safety_violations = sum(int(row["safety_violations"]) for row in results)
    unsigned = {
        "schema_version": ROBUSTNESS_RECEIPT_SCHEMA,
        "posterior_id": normalized["posterior_id"],
        "posterior_sha256": canonical_digest(normalized),
        "scene_id": normalized["scene_id"],
        "evaluator_id": normalized["evaluator_id"],
        "split": split,
        "sample_count": len(results),
        "success_count": success_count,
        "success_rate": success_count / len(results),
        "safety_violations": safety_violations,
        "seed_set_sha256": canonical_digest([row["seed"] for row in results]),
        "results_sha256": canonical_digest(results),
        "selection_eligible": split == "development",
        "authority": {
            "physical_transfer_proof": False,
            "calibration_proof": False,
            "training_admitted": False,
            "promotion_authority": False,
        },
    }
    return {"receipt": seal_artifact(unsigned), "results": results}


def score_intervention_proposal(
    *,
    proposal_sha256: str,
    counterexample_id: str,
    evaluator_id: str,
    nominal_strict_success: bool,
    nominal_safety_violations: int,
    policy_consequence_reward: float,
    baseline_strict_success: bool,
    robustness_results: Sequence[Mapping[str, Any]],
    development_seed_set_sha256: str,
    intervention_cost: float,
    ik_failure_count: int,
    non_regression: bool,
) -> dict[str, Any]:
    """Create a non-admitting score from nominal and development outcomes."""

    _require(bool(robustness_results), "robustness results must not be empty")
    success_count = 0
    robustness_safety = 0
    for row in robustness_results:
        _require(row.get("split") == "development", "sealed results may not select repair data")
        _require(type(row.get("strict_success")) is bool, "robustness strict_success must be boolean")
        safety = row.get("safety_violations")
        _require(type(safety) is int and safety >= 0, "robustness safety violations are invalid")
        success_count += int(row["strict_success"])
        robustness_safety += safety
    sample_count = len(robustness_results)
    robustness_rate = success_count / sample_count
    threshold_met = robustness_rate >= 0.75 and robustness_safety == 0
    suffix_candidate = (
        nominal_strict_success
        and nominal_safety_violations == 0
        and threshold_met
        and non_regression
        and ik_failure_count == 0
    )
    score = {
        "schema_version": PROPOSAL_SCORE_SCHEMA,
        "proposal_sha256": proposal_sha256,
        "counterexample_id": counterexample_id,
        "evaluator_id": evaluator_id,
        "nominal": {
            "strict_success": nominal_strict_success,
            "safety_violations": nominal_safety_violations,
            "policy_consequence_reward": policy_consequence_reward,
        },
        "robustness": {
            "sample_count": sample_count,
            "success_count": success_count,
            "safety_violations": robustness_safety,
            "threshold_met": threshold_met,
            "development_seed_set_sha256": development_seed_set_sha256,
        },
        "components": {
            "success_uplift": float(nominal_strict_success) - float(baseline_strict_success),
            "robustness_rate": robustness_rate,
            "intervention_cost": intervention_cost,
            "ik_failure_penalty": float(ik_failure_count),
            "safety_penalty": float(nominal_safety_violations + robustness_safety),
            "non_regression": non_regression,
        },
        "decision": {
            "suffix_candidate": suffix_candidate,
            "requires_independent_full_replay": True,
            "training_admitted": False,
            "promoted": False,
        },
        "authority": {
            "policy_reward_is_proposal_score": False,
            "evaluator_owns_admission": True,
            "promotion_authority": False,
            "physical_transfer_proof": False,
        },
    }
    return validate_proposal_score(score)
