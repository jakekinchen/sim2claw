"""Fail-closed contracts for LLM-proposed corrective interventions.

The language model proposes bounded task-space intent.  It never owns raw joint
targets, simulator state restoration, reward, data admission, promotion, or
robot control.  Deterministic code compiles proposals and a separate evaluator
decides whether a fully replayed suffix is eligible for LF-09.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import mujoco
import numpy as np

from .grasp import _pinch_offset, _pinch_point, _solve_reach
from .learning_factory_artifacts import FactoryArtifactError, canonical_digest
from .paths import REPO_ROOT
from .scene import ROBOT_JOINTS


FAILURE_PACKET_SCHEMA = "sim2claw.corrective_failure_packet.v1"
PROPOSAL_SCHEMA = "sim2claw.corrective_intervention_proposal.v1"
COMPILED_TRAJECTORY_SCHEMA = "sim2claw.compiled_corrective_trajectory.v1"
POSTERIOR_SCHEMA = "sim2claw.corrective_robustness_posterior.v1"
PROPOSAL_SCORE_SCHEMA = "sim2claw.corrective_proposal_score.v1"
LOOP_CONTRACT_SCHEMA = "sim2claw.llm_corrective_intervention_contract.v1"
LOOP_CONTRACT_PATH = REPO_ROOT / "configs" / "evaluations" / "llm_corrective_intervention_v1.json"

SHA256_LENGTH = 64
SAMPLE_HZ = 20
MAX_WAYPOINTS = 3
MAX_ACTIONS = 20
MAX_HORIZON_SECONDS = 1.0
MAX_TRANSLATION_NORM_M = 0.010
MAX_ROTATION_NORM_RAD = 0.15
MAX_GRIPPER_DELTA_RAD = 0.12
MAX_IK_RESIDUAL_M = 0.003
MIN_ROBUSTNESS_RATE = 0.75

JOINT_BOUNDS_RAD = (
    (-1.91986, 1.91986),
    (-1.74533, 1.74533),
    (-1.69, 1.69),
    (-1.65806, 1.65806),
    (-2.74385, 2.84121),
    (-0.17453, 1.74533),
)

ALLOWED_OBSERVATIONS = frozenset(
    {
        "top_rgb",
        "wrist_rgb",
        "robot_joint_state",
        "end_effector_pose",
        "selected_piece_pose",
        "target_pose",
        "contact_summary",
        "requested_applied_control_summary",
    }
)
ALLOWED_REFERENCE_FRAMES = frozenset({"selected_object", "target"})
ALLOWED_SOURCE_ROLES = frozenset({"training", "development"})
ALLOWED_FAILURE_PHASES = frozenset(
    {"pregrasp", "grasp_lift", "transport", "place_release", "retreat"}
)

# These are conservative infrastructure envelopes, not calibrated real-world
# uncertainty.  Each posterior parameter must also cite its own evidence.
POSTERIOR_ENVELOPES: dict[str, tuple[float, float, float]] = {
    "object_pose_x_m": (-0.025, 0.025, 0.030),
    "object_pose_y_m": (-0.025, 0.025, 0.030),
    "object_yaw_rad": (-0.35, 0.35, 0.40),
    "control_latency_s": (0.0, 0.15, 0.10),
    "joint_zero_offset_rad": (-0.15, 0.15, 0.15),
    "contact_friction_scale": (0.5, 1.5, 0.8),
    "camera_xy_offset_m": (-0.02, 0.02, 0.025),
}


class CorrectiveInterventionError(FactoryArtifactError):
    """Raised when a corrective artifact violates an authority or bound."""


def load_corrective_loop_contract(path: Path = LOOP_CONTRACT_PATH) -> dict[str, Any]:
    """Load the frozen v1 campaign boundary and reject weakened gates."""

    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), "corrective loop contract must be an object")
    _require(value.get("schema_version") == LOOP_CONTRACT_SCHEMA, "unsupported corrective loop contract")
    _require(value.get("contract_id") == "llm_corrective_intervention_pregrasp_v1", "corrective loop identity changed")
    _require(value.get("source_roles") == ["training", "development"], "corrective loop source roles changed")
    _require(value.get("held_out_training_rows") == 0, "held-out rows entered corrective training")
    packet = value.get("failure_packet", {})
    _require(packet.get("transfer_observable_only") is True, "failure packet observability weakened")
    _require(packet.get("privileged_integration_state_visible_to_proposer") is False, "privileged state became proposer-visible")
    _require(packet.get("maximum_candidate_proposals") == 8, "candidate proposal budget changed")
    _require(packet.get("maximum_simulator_calls") == 136, "simulator-call budget changed")
    proposal = value.get("proposal", {})
    expected_proposal = {
        "reference_frames": sorted(ALLOWED_REFERENCE_FRAMES),
        "maximum_waypoints": MAX_WAYPOINTS,
        "maximum_translation_norm_m": MAX_TRANSLATION_NORM_M,
        "maximum_rotation_norm_rad": MAX_ROTATION_NORM_RAD,
        "maximum_gripper_delta_rad": MAX_GRIPPER_DELTA_RAD,
        "maximum_horizon_seconds": MAX_HORIZON_SECONDS,
        "raw_joint_proposals_forbidden": True,
    }
    _require({**proposal, "reference_frames": sorted(proposal.get("reference_frames", []))} == expected_proposal, "proposal contract changed")
    compiler = value.get("compiler", {})
    _require(compiler.get("profile_id") == "bounded_pregrasp_cartesian_v1", "compiler profile changed")
    _require(compiler.get("supported_phase") == "pregrasp", "compiler phase changed")
    _require(compiler.get("orientation_change_supported") is False, "orientation control is not implemented")
    _require(compiler.get("maximum_ik_residual_m") == MAX_IK_RESIDUAL_M, "IK residual bound changed")
    _require(compiler.get("sample_hold_hz") == SAMPLE_HZ, "compiler cadence changed")
    _require(compiler.get("physics_steps_per_action") == 10, "compiler physics cadence changed")
    _require(compiler.get("maximum_action_count") == MAX_ACTIONS, "compiler action ceiling changed")
    _require(compiler.get("silent_clipping_forbidden") is True, "silent clipping became allowed")
    _require(compiler.get("compiled_action_owner") == "geometric_expert", "compiled action owner changed")
    _require(compiler.get("llm_direct_control") is False, "LLM direct control became enabled")
    acceptance = value.get("proposal_acceptance", {})
    _require(acceptance.get("minimum_development_successes") == 12, "development threshold count changed")
    _require(acceptance.get("development_sample_count") == 16, "development posterior count changed")
    _require(acceptance.get("minimum_robustness_rate") == MIN_ROBUSTNESS_RATE, "robustness threshold changed")
    for field in (
        "require_nominal_strict_success",
        "require_non_regression",
        "requires_independent_full_prefix_plus_suffix_replay",
    ):
        _require(acceptance.get(field) is True, f"acceptance gate disabled: {field}")
    _require(acceptance.get("maximum_safety_violations") == 0, "safety violations became admissible")
    _require(acceptance.get("proposal_score_can_admit_training") is False, "proposal score gained admission authority")
    _require(acceptance.get("proposal_score_can_promote") is False, "proposal score gained promotion authority")
    dataset = value.get("dataset", {})
    _require(dataset.get("failed_prefix_training_rows") == 0, "failed prefix entered training")
    _require(dataset.get("route_target") == "LF-09", "correction route changed")
    authority = value.get("authority", {})
    _require(authority and all(item is False for item in authority.values()), "corrective loop authority boundary changed")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CorrectiveInterventionError(message)


def _exact_keys(value: Mapping[str, Any], keys: Iterable[str], label: str) -> None:
    expected = set(keys)
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    _require(not missing and not unknown, f"{label} keys differ: missing={missing}, unknown={unknown}")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return value


def _finite(value: Any, label: str) -> float:
    _require(type(value) in {int, float}, f"{label} must be numeric")
    result = float(value)
    _require(math.isfinite(result), f"{label} must be finite")
    return result


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    _require(type(value) is int and value >= minimum, f"{label} must be an integer >= {minimum}")
    return value


def _nonempty_string(value: Any, label: str) -> str:
    _require(isinstance(value, str) and value.strip(), f"{label} must be a non-empty string")
    return value.strip()


def _digest(value: Any, label: str) -> str:
    result = _nonempty_string(value, label)
    _require(len(result) == SHA256_LENGTH, f"{label} must be a SHA-256 digest")
    try:
        int(result, 16)
    except ValueError as error:
        raise CorrectiveInterventionError(f"{label} must be hexadecimal") from error
    return result.lower()


def _vector(value: Any, dimension: int, label: str) -> list[float]:
    _require(isinstance(value, list) and len(value) == dimension, f"{label} must be a {dimension}-vector")
    return [_finite(item, f"{label}[{index}]") for index, item in enumerate(value)]


def _bool(value: Any, label: str) -> bool:
    _require(type(value) is bool, f"{label} must be boolean")
    return value


def seal_artifact(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep-copied artifact with a canonical content digest."""

    _require("artifact_sha256" not in value, "artifact is already sealed")
    result = copy.deepcopy(dict(value))
    result["artifact_sha256"] = canonical_digest(result)
    return result


def verify_sealed_artifact(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    digest = _digest(result.pop("artifact_sha256", None), "artifact_sha256")
    _require(digest == canonical_digest(result), "artifact digest mismatch")
    return copy.deepcopy(dict(value))


def validate_failure_packet(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the transfer-observable packet shown to an intervention proposer."""

    value = _mapping(value, "failure packet")
    _exact_keys(
        value,
        {
            "schema_version",
            "counterexample_id",
            "source_role",
            "proof_class",
            "identities",
            "branch",
            "observations",
            "failure",
            "budgets",
            "authority",
        },
        "failure packet",
    )
    _require(value["schema_version"] == FAILURE_PACKET_SCHEMA, "unsupported failure packet schema")
    _nonempty_string(value["counterexample_id"], "counterexample_id")
    _require(value["source_role"] in ALLOWED_SOURCE_ROLES, "held-out or physical failure packets are forbidden")
    _require(value["proof_class"] == "simulation", "failure packet must remain simulation evidence")

    identities = _mapping(value["identities"], "failure packet identities")
    _exact_keys(
        identities,
        {"dataset_sha256", "policy_id", "scene_id", "evaluator_id", "action_trace_sha256"},
        "failure packet identities",
    )
    _digest(identities["dataset_sha256"], "dataset_sha256")
    _digest(identities["action_trace_sha256"], "action_trace_sha256")
    for field in ("policy_id", "scene_id", "evaluator_id"):
        _nonempty_string(identities[field], field)

    branch = _mapping(value["branch"], "failure branch")
    _exact_keys(branch, {"step", "integration_state_sha256"}, "failure branch")
    _integer(branch["step"], "branch.step")
    _digest(branch["integration_state_sha256"], "branch.integration_state_sha256")

    observations = value["observations"]
    _require(isinstance(observations, list) and observations, "observations must be a non-empty list")
    kinds: set[str] = set()
    for index, row_value in enumerate(observations):
        row = _mapping(row_value, f"observations[{index}]")
        _exact_keys(row, {"kind", "artifact_sha256", "description"}, f"observations[{index}]")
        kind = _nonempty_string(row["kind"], f"observations[{index}].kind")
        _require(kind in ALLOWED_OBSERVATIONS and kind not in kinds, "unsupported, privileged, or duplicate observation")
        kinds.add(kind)
        _digest(row["artifact_sha256"], f"observations[{index}].artifact_sha256")
        _nonempty_string(row["description"], f"observations[{index}].description")

    failure = _mapping(value["failure"], "failure")
    _exact_keys(failure, {"code", "phase", "first_divergence_step", "consequences"}, "failure")
    _nonempty_string(failure["code"], "failure.code")
    _require(failure["phase"] in ALLOWED_FAILURE_PHASES, "failure phase is unsupported")
    divergence = _integer(failure["first_divergence_step"], "failure.first_divergence_step")
    _require(divergence >= branch["step"], "first divergence precedes the branch state")
    consequences = _mapping(failure["consequences"], "failure consequences")
    _require(bool(consequences), "failure consequences must not be empty")
    for name, consequence in consequences.items():
        _nonempty_string(name, "consequence name")
        if type(consequence) is bool:
            continue
        _finite(consequence, f"consequence {name}")

    budgets = _mapping(value["budgets"], "failure budgets")
    _exact_keys(budgets, {"candidate_proposals", "simulator_calls"}, "failure budgets")
    _integer(budgets["candidate_proposals"], "candidate_proposals", minimum=1)
    _integer(budgets["simulator_calls"], "simulator_calls", minimum=1)

    authority = _mapping(value["authority"], "failure authority")
    _exact_keys(
        authority,
        {"held_out", "policy_adapter_privileged_state", "physical_authority", "promotion_authority"},
        "failure authority",
    )
    for field in authority:
        _require(_bool(authority[field], f"authority.{field}") is False, f"failure packet improperly grants {field}")
    return copy.deepcopy(dict(value))


def validate_intervention_proposal(
    value: Mapping[str, Any],
    *,
    failure_packet: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate bounded task-space intent and bind it to one failure packet."""

    value = _mapping(value, "intervention proposal")
    _exact_keys(
        value,
        {
            "schema_version",
            "proposal_id",
            "counterexample_id",
            "branch_state_sha256",
            "bindings",
            "proposer",
            "waypoints",
            "expected_consequences",
            "confidence",
            "abstain",
        },
        "intervention proposal",
    )
    _require(value["schema_version"] == PROPOSAL_SCHEMA, "unsupported intervention proposal schema")
    _nonempty_string(value["proposal_id"], "proposal_id")
    _nonempty_string(value["counterexample_id"], "counterexample_id")
    _digest(value["branch_state_sha256"], "branch_state_sha256")

    bindings = _mapping(value["bindings"], "proposal bindings")
    _exact_keys(
        bindings,
        {"dataset_sha256", "policy_id", "scene_id", "evaluator_id", "action_trace_sha256"},
        "proposal bindings",
    )
    _digest(bindings["dataset_sha256"], "bindings.dataset_sha256")
    _digest(bindings["action_trace_sha256"], "bindings.action_trace_sha256")
    for field in ("policy_id", "scene_id", "evaluator_id"):
        _nonempty_string(bindings[field], f"bindings.{field}")

    proposer = _mapping(value["proposer"], "proposer")
    _exact_keys(
        proposer,
        {"model_id", "harness_id", "prompt_sha256", "skill_bundle_sha256", "tool_contract_sha256"},
        "proposer",
    )
    for field in ("model_id", "harness_id"):
        _nonempty_string(proposer[field], f"proposer.{field}")
    for field in ("prompt_sha256", "skill_bundle_sha256", "tool_contract_sha256"):
        _digest(proposer[field], f"proposer.{field}")

    confidence = _finite(value["confidence"], "confidence")
    _require(0.0 <= confidence <= 1.0, "confidence must be in [0, 1]")
    abstain = _bool(value["abstain"], "abstain")
    waypoints = value["waypoints"]
    _require(isinstance(waypoints, list), "waypoints must be a list")
    if abstain:
        _require(not waypoints, "abstaining proposals may not contain waypoints")
    else:
        _require(1 <= len(waypoints) <= MAX_WAYPOINTS, "proposal must contain one to three waypoints")

    total_duration = 0.0
    for index, waypoint_value in enumerate(waypoints):
        waypoint = _mapping(waypoint_value, f"waypoints[{index}]")
        _exact_keys(
            waypoint,
            {
                "reference_frame",
                "translation_delta_m",
                "rotation_delta_axis_angle_rad",
                "gripper_delta_rad",
                "duration_s",
                "expected_effect",
            },
            f"waypoints[{index}]",
        )
        _require(waypoint["reference_frame"] in ALLOWED_REFERENCE_FRAMES, "waypoint reference frame is unsupported")
        translation = _vector(waypoint["translation_delta_m"], 3, f"waypoints[{index}].translation_delta_m")
        rotation = _vector(waypoint["rotation_delta_axis_angle_rad"], 3, f"waypoints[{index}].rotation_delta_axis_angle_rad")
        _require(math.dist(translation, [0.0, 0.0, 0.0]) <= MAX_TRANSLATION_NORM_M, "waypoint translation exceeds 10 mm")
        _require(math.dist(rotation, [0.0, 0.0, 0.0]) <= MAX_ROTATION_NORM_RAD, "waypoint rotation exceeds bound")
        gripper_delta = _finite(waypoint["gripper_delta_rad"], f"waypoints[{index}].gripper_delta_rad")
        _require(abs(gripper_delta) <= MAX_GRIPPER_DELTA_RAD, "waypoint gripper delta exceeds bound")
        duration = _finite(waypoint["duration_s"], f"waypoints[{index}].duration_s")
        _require(1.0 / SAMPLE_HZ <= duration <= 0.5, "waypoint duration is outside [0.05, 0.5] seconds")
        samples = duration * SAMPLE_HZ
        _require(math.isclose(samples, round(samples), abs_tol=1e-9), "waypoint duration must align to 20 Hz")
        total_duration += duration
        _nonempty_string(waypoint["expected_effect"], f"waypoints[{index}].expected_effect")
    _require(total_duration <= MAX_HORIZON_SECONDS, "intervention exceeds one second")

    expected = _mapping(value["expected_consequences"], "expected consequences")
    _require(bool(expected), "expected consequences must not be empty")
    for name, consequence in expected.items():
        _nonempty_string(name, "expected consequence name")
        if type(consequence) is bool:
            continue
        _finite(consequence, f"expected consequence {name}")

    if failure_packet is not None:
        packet = validate_failure_packet(failure_packet)
        _require(value["counterexample_id"] == packet["counterexample_id"], "proposal counterexample identity mismatch")
        _require(value["branch_state_sha256"] == packet["branch"]["integration_state_sha256"], "proposal branch state mismatch")
        _require(dict(bindings) == packet["identities"], "proposal scientific bindings mismatch")
    return copy.deepcopy(dict(value))


def validate_compiled_trajectory(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate deterministic joint targets compiled from one sealed proposal."""

    value = _mapping(value, "compiled trajectory")
    _exact_keys(
        value,
        {
            "schema_version",
            "proposal_sha256",
            "counterexample_id",
            "branch_state_sha256",
            "compiler",
            "execution",
            "initial_action_rad",
            "maximum_delta_per_sample_rad",
            "actions_rad",
            "diagnostics",
            "authority",
        },
        "compiled trajectory",
    )
    _require(value["schema_version"] == COMPILED_TRAJECTORY_SCHEMA, "unsupported compiled trajectory schema")
    _digest(value["proposal_sha256"], "proposal_sha256")
    _nonempty_string(value["counterexample_id"], "counterexample_id")
    _digest(value["branch_state_sha256"], "branch_state_sha256")
    compiler = _mapping(value["compiler"], "compiler")
    _exact_keys(compiler, {"compiler_id", "ik_solver_id"}, "compiler")
    _nonempty_string(compiler["compiler_id"], "compiler_id")
    _nonempty_string(compiler["ik_solver_id"], "ik_solver_id")
    execution = _mapping(value["execution"], "execution")
    _exact_keys(
        execution,
        {"sample_hold_hz", "action_representation", "action_dimension", "maximum_action_count", "no_clipping"},
        "execution",
    )
    _require(execution["sample_hold_hz"] == SAMPLE_HZ, "compiled trajectory must run at 20 Hz")
    _require(execution["action_representation"] == "absolute_joint_position_target", "compiled actions must be absolute joint targets")
    _require(execution["action_dimension"] == 6, "compiled actions must have six dimensions")
    _require(execution["maximum_action_count"] == MAX_ACTIONS, "compiled action ceiling changed")
    _require(execution["no_clipping"] is True, "silent clipping is forbidden")

    initial = _vector(value["initial_action_rad"], 6, "initial_action_rad")
    maximum_delta = _vector(value["maximum_delta_per_sample_rad"], 6, "maximum_delta_per_sample_rad")
    _require(all(item > 0.0 for item in maximum_delta), "per-sample delta limits must be positive")
    actions = value["actions_rad"]
    _require(isinstance(actions, list) and 1 <= len(actions) <= MAX_ACTIONS, "compiled trajectory must contain 1-20 actions")
    previous = initial
    for action_index, action_value in enumerate(actions):
        action = _vector(action_value, 6, f"actions_rad[{action_index}]")
        for joint_index, (joint_value, bounds, delta_limit) in enumerate(zip(action, JOINT_BOUNDS_RAD, maximum_delta, strict=True)):
            _require(bounds[0] <= joint_value <= bounds[1], f"compiled joint {joint_index} exceeds bounds")
            _require(abs(joint_value - previous[joint_index]) <= delta_limit + 1e-12, f"compiled joint {joint_index} exceeds rate limit")
        previous = action

    diagnostics = _mapping(value["diagnostics"], "compiler diagnostics")
    _exact_keys(
        diagnostics,
        {"maximum_ik_residual_m", "collision_free", "joint_limits_passed", "rate_limits_passed", "duration_s"},
        "compiler diagnostics",
    )
    residual = _finite(diagnostics["maximum_ik_residual_m"], "maximum_ik_residual_m")
    _require(0.0 <= residual <= MAX_IK_RESIDUAL_M, "compiled IK residual exceeds 3 mm")
    for field in ("collision_free", "joint_limits_passed", "rate_limits_passed"):
        _require(_bool(diagnostics[field], field) is True, f"compiler diagnostic failed: {field}")
    duration = _finite(diagnostics["duration_s"], "compiled duration_s")
    _require(math.isclose(duration, len(actions) / SAMPLE_HZ, abs_tol=1e-12), "compiled duration disagrees with action count")

    authority = _mapping(value["authority"], "compiled authority")
    _exact_keys(authority, {"compiled_action_owner", "llm_direct_control", "physical_authority"}, "compiled authority")
    _require(authority["compiled_action_owner"] == "geometric_expert", "compiled action owner must be geometric_expert")
    _require(authority["llm_direct_control"] is False, "LLM direct control is forbidden")
    _require(authority["physical_authority"] is False, "compiled trajectory cannot grant physical authority")
    return copy.deepcopy(dict(value))


def validate_robustness_posterior(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an evaluator-owned bounded posterior and disjoint seed sets."""

    value = _mapping(value, "robustness posterior")
    _exact_keys(
        value,
        {"schema_version", "posterior_id", "scene_id", "evaluator_id", "source_evidence_sha256", "parameters", "development_seeds", "sealed_seeds", "authority"},
        "robustness posterior",
    )
    _require(value["schema_version"] == POSTERIOR_SCHEMA, "unsupported posterior schema")
    _nonempty_string(value["posterior_id"], "posterior_id")
    _nonempty_string(value["scene_id"], "scene_id")
    _nonempty_string(value["evaluator_id"], "evaluator_id")
    evidence = value["source_evidence_sha256"]
    _require(isinstance(evidence, list) and evidence, "posterior requires source evidence")
    evidence_digests = [_digest(item, "posterior source evidence") for item in evidence]
    _require(len(evidence_digests) == len(set(evidence_digests)), "posterior source evidence is duplicated")

    parameters = value["parameters"]
    _require(isinstance(parameters, list) and parameters, "posterior parameters must be non-empty")
    names: set[str] = set()
    for index, parameter_value in enumerate(parameters):
        parameter = _mapping(parameter_value, f"parameters[{index}]")
        _exact_keys(parameter, {"name", "distribution", "nominal", "lower", "upper", "stddev", "evidence_sha256"}, f"parameters[{index}]")
        name = _nonempty_string(parameter["name"], f"parameters[{index}].name")
        _require(name in POSTERIOR_ENVELOPES and name not in names, "unsupported or duplicate posterior parameter")
        names.add(name)
        distribution = parameter["distribution"]
        _require(distribution in {"uniform", "truncated_normal"}, "unsupported posterior distribution")
        nominal = _finite(parameter["nominal"], f"parameters[{index}].nominal")
        lower = _finite(parameter["lower"], f"parameters[{index}].lower")
        upper = _finite(parameter["upper"], f"parameters[{index}].upper")
        envelope_lower, envelope_upper, maximum_span = POSTERIOR_ENVELOPES[name]
        _require(envelope_lower <= lower < upper <= envelope_upper, "posterior bounds exceed the infrastructure envelope")
        _require(lower <= nominal <= upper, "posterior nominal lies outside its bounds")
        _require(upper - lower <= maximum_span + 1e-12, "posterior span is too broad")
        if distribution == "uniform":
            _require(parameter["stddev"] is None, "uniform posterior stddev must be null")
        else:
            stddev = _finite(parameter["stddev"], f"parameters[{index}].stddev")
            _require(0.0 < stddev <= (upper - lower) / 2.0, "posterior stddev is invalid")
        parameter_evidence = _digest(parameter["evidence_sha256"], f"parameters[{index}].evidence_sha256")
        _require(parameter_evidence in evidence_digests, "posterior parameter lacks declared source evidence")

    seed_sets: dict[str, list[int]] = {}
    for field in ("development_seeds", "sealed_seeds"):
        seeds = value[field]
        _require(isinstance(seeds, list) and seeds, f"{field} must be a non-empty list")
        normalized = [_integer(seed, f"{field} seed", minimum=1) for seed in seeds]
        _require(len(normalized) == len(set(normalized)), f"{field} contains duplicate seeds")
        seed_sets[field] = normalized
    _require(not set(seed_sets["development_seeds"]) & set(seed_sets["sealed_seeds"]), "development and sealed posterior seeds overlap")

    authority = _mapping(value["authority"], "posterior authority")
    _exact_keys(authority, {"calibration_proof", "physical_transfer_proof", "visible_to_proposer", "promotion_authority"}, "posterior authority")
    for field in authority:
        _require(_bool(authority[field], f"posterior authority.{field}") is False, f"posterior improperly grants {field}")
    return copy.deepcopy(dict(value))


def validate_proposal_score(value: Mapping[str, Any]) -> dict[str, Any]:
    """Keep proposal utility separate from reward, admission, and promotion."""

    value = _mapping(value, "proposal score")
    _exact_keys(
        value,
        {"schema_version", "proposal_sha256", "counterexample_id", "evaluator_id", "nominal", "robustness", "components", "decision", "authority"},
        "proposal score",
    )
    _require(value["schema_version"] == PROPOSAL_SCORE_SCHEMA, "unsupported proposal score schema")
    _digest(value["proposal_sha256"], "proposal_sha256")
    _nonempty_string(value["counterexample_id"], "counterexample_id")
    _nonempty_string(value["evaluator_id"], "evaluator_id")

    nominal = _mapping(value["nominal"], "nominal score")
    _exact_keys(nominal, {"strict_success", "safety_violations", "policy_consequence_reward"}, "nominal score")
    nominal_success = _bool(nominal["strict_success"], "nominal.strict_success")
    nominal_safety = _integer(nominal["safety_violations"], "nominal.safety_violations")
    _finite(nominal["policy_consequence_reward"], "policy_consequence_reward")

    robustness = _mapping(value["robustness"], "robustness score")
    _exact_keys(robustness, {"sample_count", "success_count", "safety_violations", "threshold_met", "development_seed_set_sha256"}, "robustness score")
    sample_count = _integer(robustness["sample_count"], "robustness.sample_count", minimum=1)
    success_count = _integer(robustness["success_count"], "robustness.success_count")
    _require(success_count <= sample_count, "robustness successes exceed sample count")
    robustness_safety = _integer(robustness["safety_violations"], "robustness.safety_violations")
    threshold_met = _bool(robustness["threshold_met"], "robustness.threshold_met")
    _digest(robustness["development_seed_set_sha256"], "development_seed_set_sha256")
    computed_threshold = success_count / sample_count >= MIN_ROBUSTNESS_RATE and robustness_safety == 0
    _require(threshold_met == computed_threshold, "robustness threshold flag is inconsistent")

    components = _mapping(value["components"], "proposal score components")
    _exact_keys(
        components,
        {"success_uplift", "robustness_rate", "intervention_cost", "ik_failure_penalty", "safety_penalty", "non_regression"},
        "proposal score components",
    )
    for field in ("success_uplift", "robustness_rate", "intervention_cost", "ik_failure_penalty", "safety_penalty"):
        _finite(components[field], f"components.{field}")
    _require(math.isclose(float(components["robustness_rate"]), success_count / sample_count, abs_tol=1e-12), "robustness component disagrees with trials")
    non_regression = _bool(components["non_regression"], "components.non_regression")

    decision = _mapping(value["decision"], "proposal decision")
    _exact_keys(decision, {"suffix_candidate", "requires_independent_full_replay", "training_admitted", "promoted"}, "proposal decision")
    suffix_candidate = _bool(decision["suffix_candidate"], "decision.suffix_candidate")
    expected_candidate = nominal_success and nominal_safety == 0 and threshold_met and non_regression
    _require(suffix_candidate == expected_candidate, "suffix candidate decision is inconsistent")
    _require(decision["requires_independent_full_replay"] is True, "proposal score cannot bypass independent replay")
    _require(decision["training_admitted"] is False, "proposal score cannot admit training data")
    _require(decision["promoted"] is False, "proposal score cannot promote")

    authority = _mapping(value["authority"], "proposal score authority")
    _exact_keys(authority, {"policy_reward_is_proposal_score", "evaluator_owns_admission", "promotion_authority", "physical_transfer_proof"}, "proposal score authority")
    _require(authority["policy_reward_is_proposal_score"] is False, "policy reward and proposal score must remain separate")
    _require(authority["evaluator_owns_admission"] is True, "independent evaluator must own admission")
    _require(authority["promotion_authority"] is False, "proposal score cannot promote")
    _require(authority["physical_transfer_proof"] is False, "proposal score is not physical transfer proof")
    return copy.deepcopy(dict(value))


def build_failure_packet(
    *,
    counterexample: Mapping[str, Any],
    source_role: str,
    scene_id: str,
    evaluator_id: str,
    branch_step: int,
    branch_state_sha256: str,
    first_divergence_step: int,
    failure_code: str,
    failure_phase: str,
    consequences: Mapping[str, float | bool],
    observations: Sequence[Mapping[str, str]],
    candidate_proposals: int = 8,
    simulator_calls: int = 136,
) -> dict[str, Any]:
    """Build the public proposer packet from one evaluator-owned LF-12 row.

    The caller supplies digests of transfer-observable artifacts.  Raw bytes and
    evaluator integration state deliberately remain outside the packet.
    """

    counterexample = _mapping(counterexample, "counterexample")
    _require(counterexample.get("training_rows_authorized") == 0, "counterexample already authorizes training rows")
    _require("LF-09" in counterexample.get("route_targets", []), "counterexample is not routed to LF-09 repair")
    failure_codes = counterexample.get("failure_codes")
    _require(isinstance(failure_codes, list) and failure_code in failure_codes, "failure code is not evaluator-owned")
    checkpoint_sha256 = _digest(counterexample.get("checkpoint_sha256"), "counterexample.checkpoint_sha256")
    cohort_sha256 = _digest(counterexample.get("cohort_sha256"), "counterexample.cohort_sha256")
    trace_sha256 = _digest(counterexample.get("action_trace_sha256"), "counterexample.action_trace_sha256")
    packet = {
        "schema_version": FAILURE_PACKET_SCHEMA,
        "counterexample_id": _nonempty_string(counterexample.get("counterexample_id"), "counterexample.counterexample_id"),
        "source_role": source_role,
        "proof_class": "simulation",
        "identities": {
            "dataset_sha256": cohort_sha256,
            "policy_id": f"checkpoint-sha256:{checkpoint_sha256}",
            "scene_id": scene_id,
            "evaluator_id": evaluator_id,
            "action_trace_sha256": trace_sha256,
        },
        "branch": {
            "step": branch_step,
            "integration_state_sha256": branch_state_sha256,
        },
        "observations": [dict(row) for row in observations],
        "failure": {
            "code": failure_code,
            "phase": failure_phase,
            "first_divergence_step": first_divergence_step,
            "consequences": dict(consequences),
        },
        "budgets": {
            "candidate_proposals": candidate_proposals,
            "simulator_calls": simulator_calls,
        },
        "authority": {
            "held_out": False,
            "policy_adapter_privileged_state": False,
            "physical_authority": False,
            "promotion_authority": False,
        },
    }
    return validate_failure_packet(packet)


def _joint_qpos_addresses(model: mujoco.MjModel, arm: str) -> list[int]:
    addresses: list[int] = []
    for joint in ROBOT_JOINTS:
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, f"{arm}_{joint}")
        _require(joint_id >= 0, f"missing {arm} joint: {joint}")
        addresses.append(int(model.jnt_qposadr[joint_id]))
    return addresses


def _body_name(model: mujoco.MjModel, body_id: int) -> str:
    return mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or f"body-{body_id}"


def _arm_contact_pairs(model: mujoco.MjModel, data: mujoco.MjData, arm: str) -> set[tuple[str, str]]:
    prefix = f"{arm}_"
    pairs: set[tuple[str, str]] = set()
    for contact_index in range(data.ncon):
        contact = data.contact[contact_index]
        first_body = int(model.geom_bodyid[int(contact.geom1)])
        second_body = int(model.geom_bodyid[int(contact.geom2)])
        first_name = _body_name(model, first_body)
        second_name = _body_name(model, second_body)
        if first_name.startswith(prefix) or second_name.startswith(prefix):
            pairs.add(tuple(sorted((first_name, second_name))))
    return pairs


def _seeded_kinematic_data(
    model: mujoco.MjModel,
    branch_data: mujoco.MjData,
    qpos_addresses: Sequence[int],
    action: Sequence[float],
) -> mujoco.MjData:
    seeded = mujoco.MjData(model)
    seeded.qpos[:] = branch_data.qpos
    seeded.qvel[:] = branch_data.qvel
    if model.na:
        seeded.act[:] = branch_data.act
    seeded.qpos[list(qpos_addresses)] = np.asarray(action, dtype=np.float64)
    mujoco.mj_forward(model, seeded)
    return seeded


def _rotation_matrix(value: Any, label: str) -> np.ndarray:
    matrix = np.asarray(value, dtype=np.float64)
    _require(matrix.shape == (3, 3) and np.isfinite(matrix).all(), f"{label} must be a finite 3x3 matrix")
    _require(np.allclose(matrix.T @ matrix, np.eye(3), atol=1e-6), f"{label} must be orthonormal")
    _require(math.isclose(float(np.linalg.det(matrix)), 1.0, abs_tol=1e-6), f"{label} must be a proper rotation")
    return matrix


def compile_task_space_intervention(
    proposal: Mapping[str, Any],
    *,
    failure_packet: Mapping[str, Any],
    model: mujoco.MjModel,
    branch_data: mujoco.MjData,
    selected_piece_body_name: str,
    target_rotation_world: Sequence[Sequence[float]],
    initial_action_rad: Sequence[float],
    maximum_delta_per_sample_rad: Sequence[float] = (0.08,) * 6,
    arm: str = "left",
) -> dict[str, Any]:
    """Compile the first pre-contact centering profile into bounded actions.

    The current profile intentionally supports translation-only pregrasp
    interventions.  Contact-rich or orientation-changing proposals remain
    contract-valid research hypotheses but fail compilation until a dedicated
    observable contact/orientation controller is implemented.
    """

    packet = validate_failure_packet(failure_packet)
    normalized = validate_intervention_proposal(proposal, failure_packet=packet)
    _require(normalized["abstain"] is False, "an abstaining proposal cannot be compiled")
    _require(packet["failure"]["phase"] == "pregrasp", "v1 compiler supports pregrasp corrections only")
    initial = np.asarray(_vector(list(initial_action_rad), 6, "initial_action_rad"), dtype=np.float64)
    maximum_delta = np.asarray(
        _vector(list(maximum_delta_per_sample_rad), 6, "maximum_delta_per_sample_rad"),
        dtype=np.float64,
    )
    _require(np.all(maximum_delta > 0.0), "per-sample delta limits must be positive")
    for joint_index, (value, bounds) in enumerate(zip(initial, JOINT_BOUNDS_RAD, strict=True)):
        _require(bounds[0] <= value <= bounds[1], f"initial joint {joint_index} exceeds bounds")

    selected_piece_body = mujoco.mj_name2id(
        model,
        mujoco.mjtObj.mjOBJ_BODY,
        selected_piece_body_name,
    )
    _require(selected_piece_body >= 0, "selected piece body is missing")
    object_rotation = np.asarray(branch_data.xmat[selected_piece_body], dtype=np.float64).reshape(3, 3)
    target_rotation = _rotation_matrix(target_rotation_world, "target_rotation_world")
    qpos_addresses = _joint_qpos_addresses(model, arm)
    pinch_local = _pinch_offset(model, branch_data, arm)
    branch_with_initial = _seeded_kinematic_data(model, branch_data, qpos_addresses, initial)
    baseline_contacts = _arm_contact_pairs(model, branch_with_initial, arm)
    current_pinch = _pinch_point(model, branch_with_initial, arm, pinch_local).copy()
    current_action = initial.copy()
    actions: list[list[float]] = []
    maximum_residual = 0.0

    for waypoint_index, waypoint in enumerate(normalized["waypoints"]):
        rotation_delta = np.asarray(waypoint["rotation_delta_axis_angle_rad"], dtype=np.float64)
        _require(np.linalg.norm(rotation_delta) <= 1e-12, "v1 compiler does not support orientation-changing corrections")
        frame_rotation = object_rotation if waypoint["reference_frame"] == "selected_object" else target_rotation
        target_pinch = current_pinch + frame_rotation @ np.asarray(
            waypoint["translation_delta_m"], dtype=np.float64
        )
        seeded = _seeded_kinematic_data(model, branch_data, qpos_addresses, current_action)
        pose, residual = _solve_reach(model, seeded, arm, target_pinch, pinch_local)
        maximum_residual = max(maximum_residual, float(residual))
        _require(residual <= MAX_IK_RESIDUAL_M, f"waypoint {waypoint_index} IK residual exceeds 3 mm")
        goal = np.asarray(
            [
                current_action[-1] + float(waypoint["gripper_delta_rad"])
                if joint == "gripper"
                else pose[joint]
                for joint in ROBOT_JOINTS
            ],
            dtype=np.float64,
        )
        samples = int(round(float(waypoint["duration_s"]) * SAMPLE_HZ))
        for sample_index in range(1, samples + 1):
            blend = sample_index / samples
            action = current_action + blend * (goal - current_action)
            for joint_index, (joint_value, bounds) in enumerate(zip(action, JOINT_BOUNDS_RAD, strict=True)):
                _require(bounds[0] <= joint_value <= bounds[1], f"waypoint {waypoint_index} joint {joint_index} exceeds bounds")
            prior = np.asarray(actions[-1] if actions else current_action, dtype=np.float64)
            _require(np.all(np.abs(action - prior) <= maximum_delta + 1e-12), "compiled trajectory exceeds per-sample rate limit")
            float32_action = action.astype(np.float32).astype(np.float64)
            collision_data = _seeded_kinematic_data(model, branch_data, qpos_addresses, float32_action)
            new_contacts = _arm_contact_pairs(model, collision_data, arm) - baseline_contacts
            _require(not new_contacts, f"compiled trajectory introduces arm collision: {sorted(new_contacts)}")
            actions.append(float32_action.tolist())
        current_action = goal
        current_pinch = target_pinch

    compiled = {
        "schema_version": COMPILED_TRAJECTORY_SCHEMA,
        "proposal_sha256": canonical_digest(normalized),
        "counterexample_id": normalized["counterexample_id"],
        "branch_state_sha256": normalized["branch_state_sha256"],
        "compiler": {
            "compiler_id": "bounded_pregrasp_cartesian_v1",
            "ik_solver_id": "so101_damped_least_squares_position_v1",
        },
        "execution": {
            "sample_hold_hz": SAMPLE_HZ,
            "action_representation": "absolute_joint_position_target",
            "action_dimension": 6,
            "maximum_action_count": MAX_ACTIONS,
            "no_clipping": True,
        },
        "initial_action_rad": initial.astype(float).tolist(),
        "maximum_delta_per_sample_rad": maximum_delta.astype(float).tolist(),
        "actions_rad": actions,
        "diagnostics": {
            "maximum_ik_residual_m": maximum_residual,
            "collision_free": True,
            "joint_limits_passed": True,
            "rate_limits_passed": True,
            "duration_s": len(actions) / SAMPLE_HZ,
        },
        "authority": {
            "compiled_action_owner": "geometric_expert",
            "llm_direct_control": False,
            "physical_authority": False,
        },
    }
    return validate_compiled_trajectory(compiled)
