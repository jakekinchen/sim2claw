"""Deterministic synthetic benchmark for bounded corrective proposals.

The benchmark measures diagnosis and proposal quality.  It deliberately does
not execute the canonical data-admission path, train a policy, promote a
checkpoint, or touch hardware.  Public development perturbations and sealed
terminal perturbations are disjoint and the terminal evaluator is single-use.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .corrective_intervention import (
    FAILURE_PACKET_SCHEMA,
    PROPOSAL_SCHEMA,
    CorrectiveInterventionError,
    validate_failure_packet,
    validate_intervention_proposal,
)
from .learning_factory_artifacts import atomic_write_json, canonical_digest, load_json_object
from .paths import REPO_ROOT


CASE_SCHEMA = "sim2claw.corrective_repair_case.v1"
RECEIPT_SCHEMA = "sim2claw.corrective_repair_score_receipt.v1"
SUMMARY_SCHEMA = "sim2claw.corrective_repair_control_summary.v1"
CLAIM_BOUNDARY = "synthetic_benchmark_only"
BENCHMARK_CONTRACT_SCHEMA = "sim2claw.corrective_repair_benchmark_contract.v1"
BENCHMARK_CONTRACT_PATH = REPO_ROOT / "configs" / "evaluations" / "sim2claw_corrective_repair_benchmark_v1.json"
TOOL_NAMES = (
    "repair_status",
    "read_repair_evidence",
    "submit_repair_hypothesis",
    "request_repair_probe",
    "run_public_repair_evaluation",
    "submit_repair",
)

MAX_PUBLIC_EVALUATIONS = 8
SIMULATOR_CALLS_PER_EVALUATION = 17
MAX_SIMULATOR_CALLS = 136
MAX_PROBES = 2
SEALED_SAMPLE_COUNT = 16
SUCCESS_RESIDUAL_M = 0.003
SAFETY_TOTAL_DELTA_M = 0.012
SCORE_WEIGHTS = {
    "sealed_robustness": 0.35,
    "correction_accuracy": 0.25,
    "gain_over_unchanged": 0.15,
    "intervention_efficiency": 0.10,
    "evidence_discipline": 0.10,
    "safety_compliance": 0.05,
}

_DIGESTS = tuple(character * 64 for character in "abcdef1234567890")

# These targets are evaluator-only fixture facts. They are never written to a
# public packet or injected into an agent sandbox.
_SEALED_TARGETS: dict[str, tuple[float, float, float]] = {
    "center_x_pos": (0.0055, -0.0025, 0.0015),
    "center_y_pos": (-0.0035, 0.0055, 0.0005),
    "center_z_pos": (0.0025, 0.0015, 0.0065),
    "center_xy_neg": (-0.0055, -0.0035, 0.0025),
}

_OBSERVATION_NOISE = (
    (-0.0010, 0.0005, -0.0005),
    (0.0005, -0.0010, 0.0005),
    (0.0010, 0.0005, 0.0000),
    (-0.0005, 0.0000, 0.0000),
)


class CorrectiveBenchmarkError(CorrectiveInterventionError):
    """Raised when a repair benchmark attempt crosses its frozen contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CorrectiveBenchmarkError(message)


def case_ids() -> tuple[str, ...]:
    return tuple(sorted(_SEALED_TARGETS))


def load_corrective_repair_contract(path: Path = BENCHMARK_CONTRACT_PATH) -> dict[str, Any]:
    """Load the benchmark campaign boundary and reject silent budget drift."""

    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), "corrective repair benchmark contract must be an object")
    _require(value.get("schema_version") == BENCHMARK_CONTRACT_SCHEMA, "unsupported corrective repair benchmark contract")
    _require(value.get("benchmark_id") == "sim2claw-corrective-repair-four-case-v1", "corrective repair benchmark identity changed")
    _require(value.get("cases") == list(case_ids()), "corrective repair case inventory changed")
    _require(value.get("harnesses") == ["codex_cli", "claude_code"], "corrective repair harness inventory changed")
    _require(value.get("proposal_schema") == PROPOSAL_SCHEMA, "corrective repair proposal schema changed")
    budgets = value.get("budgets", {})
    expected_budgets = {
        "candidate_proposals": MAX_PUBLIC_EVALUATIONS,
        "public_evaluations": MAX_PUBLIC_EVALUATIONS,
        "simulator_calls": MAX_SIMULATOR_CALLS,
        "simulator_calls_per_public_evaluation": SIMULATOR_CALLS_PER_EVALUATION,
        "probes": MAX_PROBES,
        "terminal_submissions": 1,
        "messages": 60,
        "turns": 30,
        "tokens": 80_000,
        "seconds": 1_200,
        "maximum_cost_usd": 20.0,
    }
    _require(budgets == expected_budgets, "corrective repair benchmark budgets changed")
    splits = value.get("splits", {})
    _require(
        splits == {"development_perturbations": 16, "sealed_perturbations": 16, "disjoint": True},
        "corrective repair split contract changed",
    )
    _require(value.get("controls") == ["unchanged", "random_nudge", "bounded_search", "oracle"], "corrective repair controls changed")
    _require(value.get("score_weights") == SCORE_WEIGHTS, "corrective repair score weights changed")
    _require(value.get("claim_boundary") == CLAIM_BOUNDARY, "corrective repair claim boundary changed")
    _require(value.get("model_judge") is False, "model judge became enabled")
    authority = value.get("authority", {})
    _require(authority and all(item is False for item in authority.values()), "corrective repair authority boundary changed")
    return value


def _seed(case_id: str, split: str) -> int:
    return int(canonical_digest({"case_id": case_id, "split": split})[:8], 16)


def _perturbations(case_id: str, split: str, count: int) -> list[list[float]]:
    rng = np.random.default_rng(_seed(case_id, split))
    rows = rng.normal(0.0, 0.00055, size=(count, 3))
    rows = np.clip(rows, -0.0012, 0.0012)
    return [[float(np.float64(value)) for value in row] for row in rows]


def _failure_packet(case_id: str) -> dict[str, Any]:
    packet = {
        "schema_version": FAILURE_PACKET_SCHEMA,
        "counterexample_id": f"repair-{case_id}",
        "source_role": "development",
        "proof_class": "simulation",
        "identities": {
            "dataset_sha256": _DIGESTS[0],
            "policy_id": "synthetic-centering-policy-v1",
            "scene_id": f"synthetic-{case_id}-scene-v1",
            "evaluator_id": "corrective-repair-sealed-evaluator-v1",
            "action_trace_sha256": canonical_digest({"case_id": case_id, "trace": "failed-prefix"}),
        },
        "branch": {
            "step": 80,
            "integration_state_sha256": canonical_digest({"case_id": case_id, "state": "opaque"}),
        },
        "observations": [
            {
                "kind": "end_effector_pose",
                "artifact_sha256": canonical_digest({"case_id": case_id, "artifact": "pose-residuals"}),
                "description": "transfer-observable pregrasp residual estimates",
            },
            {
                "kind": "requested_applied_control_summary",
                "artifact_sha256": canonical_digest({"case_id": case_id, "artifact": "control-summary"}),
                "description": "requested/applied control agreement summary",
            },
        ],
        "failure": {
            "code": "pregrasp_lateral_offset",
            "phase": "pregrasp",
            "first_divergence_step": 84,
            "consequences": {"selected_piece_contact": False, "strict_success": False},
        },
        "budgets": {"candidate_proposals": MAX_PUBLIC_EVALUATIONS, "simulator_calls": MAX_SIMULATOR_CALLS},
        "authority": {
            "held_out": False,
            "policy_adapter_privileged_state": False,
            "physical_authority": False,
            "promotion_authority": False,
        },
    }
    return validate_failure_packet(packet)


def _observations(case_id: str) -> dict[str, Any]:
    target = np.asarray(_SEALED_TARGETS[case_id], dtype=np.float64)
    rows = []
    for index, noise in enumerate(_OBSERVATION_NOISE):
        estimate = target + np.asarray(noise, dtype=np.float64)
        rows.append(
            {
                "observation_id": f"pose-{index + 1}",
                "desired_pregrasp_translation_delta_m": [float(value) for value in estimate],
                "measurement_sigma_m": 0.0012,
                "selected_piece_contact": False,
                "source": "transfer_observable_pose_residual",
            }
        )
    return {
        "schema_version": "sim2claw.corrective_repair_observations.v1",
        "case_id": case_id,
        "rows": rows,
        "interpretation": "Each row estimates the bounded translation that would recenter the pregrasp.",
        "physical_calibration_proof": False,
    }


def _control_summary(case_id: str) -> dict[str, Any]:
    return {
        "schema_version": "sim2claw.corrective_repair_control_summary.v1",
        "case_id": case_id,
        "requested_applied_rms_rad": 0.0004,
        "maximum_requested_applied_error_rad": 0.0011,
        "control_saturation_observed": False,
        "interpretation": "The synthetic control trace does not support a joint-tracking fault hypothesis.",
        "physical_calibration_proof": False,
    }


def materialize_public_case(case_id: str, packet_root: Path, harness: str) -> dict[str, Any]:
    """Write only public bytes and one legal unchanged proposal."""

    load_corrective_repair_contract()
    _require(case_id in _SEALED_TARGETS, "unknown corrective repair case")
    _require(harness in {"codex_cli", "claude_code", "control"}, "unsupported harness")
    packet_root.mkdir(parents=True, exist_ok=True)
    evidence_root = packet_root / "evidence"
    candidate_root = packet_root / "candidate"
    evidence_root.mkdir(parents=True, exist_ok=True)
    candidate_root.mkdir(parents=True, exist_ok=True)
    failure = _failure_packet(case_id)
    observations = _observations(case_id)
    controls = _control_summary(case_id)
    atomic_write_json(evidence_root / "failure_packet.json", failure)
    atomic_write_json(evidence_root / "pose_residuals.json", observations)
    atomic_write_json(evidence_root / "control_summary.json", controls)
    public = {
        "schema_version": CASE_SCHEMA,
        "case_id": case_id,
        "proof_class": "synthetic_benchmark",
        "failure_packet_sha256": canonical_digest(failure),
        "evidence_manifest": [
            {"artifact_id": "failure_packet", "path": "evidence/failure_packet.json"},
            {"artifact_id": "pose_residuals", "path": "evidence/pose_residuals.json"},
            {"artifact_id": "control_summary", "path": "evidence/control_summary.json"},
        ],
        "probe_menu": [
            {"probe_id": "repeat_pose_estimate", "mode": "simulated", "cost": 1},
            {"probe_id": "control_consistency_check", "mode": "read_only", "cost": 1},
        ],
        "budgets": {
            "candidate_proposals": MAX_PUBLIC_EVALUATIONS,
            "public_evaluations": MAX_PUBLIC_EVALUATIONS,
            "simulator_calls": MAX_SIMULATOR_CALLS,
            "probes": MAX_PROBES,
            "terminal_submissions": 1,
        },
        "success_residual_m": SUCCESS_RESIDUAL_M,
        "claim_boundary": CLAIM_BOUNDARY,
        "authority": {
            "training_admission": False,
            "promotion_authority": False,
            "physical_authority": False,
            "provider_model_calls_authorized": False,
        },
    }
    public["case_sha256"] = canonical_digest(public)
    atomic_write_json(packet_root / "case.json", public)
    atomic_write_json(candidate_root / "baseline.json", build_proposal(case_id, (0.0, 0.0, 0.0), harness=harness, proposal_id="unchanged"))
    return copy.deepcopy(public)


def load_public_case(packet_root: Path) -> dict[str, Any]:
    case = load_json_object(packet_root / "case.json", label="corrective repair case")
    digest = case.pop("case_sha256", None)
    _require(isinstance(digest, str) and digest == canonical_digest(case), "corrective repair case digest mismatch")
    case["case_sha256"] = digest
    _require(case.get("schema_version") == CASE_SCHEMA, "unsupported corrective repair case")
    _require(case.get("case_id") in _SEALED_TARGETS, "unknown corrective repair case")
    return case


def build_proposal(
    case_id: str,
    delta_m: Sequence[float],
    *,
    harness: str,
    proposal_id: str,
    confidence: float = 0.5,
) -> dict[str, Any]:
    failure = _failure_packet(case_id)
    delta = [float(value) for value in delta_m]
    proposal = {
        "schema_version": PROPOSAL_SCHEMA,
        "proposal_id": proposal_id,
        "counterexample_id": failure["counterexample_id"],
        "branch_state_sha256": failure["branch"]["integration_state_sha256"],
        "bindings": copy.deepcopy(failure["identities"]),
        "proposer": {
            "model_id": harness,
            "harness_id": harness,
            "prompt_sha256": _DIGESTS[1],
            "skill_bundle_sha256": _DIGESTS[2],
            "tool_contract_sha256": canonical_digest(TOOL_NAMES),
        },
        "waypoints": [
            {
                "reference_frame": "selected_object",
                "translation_delta_m": delta,
                "rotation_delta_axis_angle_rad": [0.0, 0.0, 0.0],
                "gripper_delta_rad": 0.0,
                "duration_s": 0.25,
                "expected_effect": "recenter the transfer-observable pregrasp residual",
            }
        ],
        "expected_consequences": {"selected_piece_contact": True, "strict_success": True},
        "confidence": float(confidence),
        "abstain": False,
    }
    return validate_intervention_proposal(proposal, failure_packet=failure)


def _proposal_delta(proposal: Mapping[str, Any], failure: Mapping[str, Any]) -> np.ndarray:
    try:
        normalized = validate_intervention_proposal(proposal, failure_packet=failure)
    except CorrectiveInterventionError as error:
        raise CorrectiveBenchmarkError(str(error)) from error
    _require(normalized["abstain"] is False, "terminal repair may not abstain")
    delta = np.sum(
        np.asarray([waypoint["translation_delta_m"] for waypoint in normalized["waypoints"]], dtype=np.float64),
        axis=0,
    )
    _require(np.isfinite(delta).all(), "compiled repair delta must be finite")
    _require(float(np.linalg.norm(delta)) <= SAFETY_TOTAL_DELTA_M, "total repair delta exceeds the safety envelope")
    return delta


def _evaluate_delta(target: np.ndarray, delta: np.ndarray, perturbations: Sequence[Sequence[float]]) -> dict[str, Any]:
    residuals = [float(np.linalg.norm(target + np.asarray(row, dtype=np.float64) - delta)) for row in perturbations]
    return {
        "sample_count": len(residuals),
        "success_count": sum(value <= SUCCESS_RESIDUAL_M for value in residuals),
        "robustness_rate": sum(value <= SUCCESS_RESIDUAL_M for value in residuals) / len(residuals),
        "mean_residual_m": float(np.mean(residuals)),
        "maximum_residual_m": max(residuals),
        "nominal_residual_m": float(np.linalg.norm(target - delta)),
        "safety_violations": 0,
    }


def _validate_hypothesis(value: Mapping[str, Any], evidence_ids: set[str]) -> dict[str, Any]:
    expected = {"mechanism", "evidence_ids", "predicted_translation_delta_m", "confidence"}
    _require(isinstance(value, Mapping) and set(value) == expected, "repair hypothesis keys differ")
    _require(value["mechanism"] == "pregrasp_centering_offset", "unsupported repair mechanism")
    cited = value["evidence_ids"]
    _require(isinstance(cited, list) and cited and all(item in evidence_ids for item in cited), "hypothesis evidence IDs are invalid")
    predicted = value["predicted_translation_delta_m"]
    _require(isinstance(predicted, list) and len(predicted) == 3, "hypothesis prediction must be a 3-vector")
    predicted_values = [float(item) for item in predicted]
    _require(all(math.isfinite(item) for item in predicted_values), "hypothesis prediction must be finite")
    confidence = float(value["confidence"])
    _require(math.isfinite(confidence) and 0.0 <= confidence <= 1.0, "hypothesis confidence is outside [0, 1]")
    return {
        "mechanism": value["mechanism"],
        "evidence_ids": list(cited),
        "predicted_translation_delta_m": predicted_values,
        "confidence": confidence,
    }


class CorrectiveRepairSession:
    """Stateful public-tool and sealed-terminal interface for one case."""

    def __init__(self, packet_root: Path, state_root: Path, *, reset: bool = False):
        self.packet_root = packet_root.resolve()
        self.state_root = state_root.resolve()
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.case = load_public_case(self.packet_root)
        self.case_id = str(self.case["case_id"])
        self.failure = validate_failure_packet(load_json_object(self.packet_root / "evidence" / "failure_packet.json", label="failure packet"))
        self.state_path = self.state_root / "session_state.json"
        if reset:
            for path in (self.state_path, self.state_root / "attempt.json", self.state_root / "score_receipt.json"):
                path.unlink(missing_ok=True)
        if not self.state_path.exists():
            self._write_state(
                {
                    "case_id": self.case_id,
                    "used": {"public_evaluations": 0, "simulator_calls": 0, "probes": 0, "terminal_submissions": 0},
                    "hypothesis": None,
                    "public_receipts": [],
                    "events": [],
                    "terminal_receipt": None,
                }
            )
        self._state()

    def _state(self) -> dict[str, Any]:
        state = load_json_object(self.state_path, label="corrective repair session")
        _require(state.get("case_id") == self.case_id, "repair session identity mismatch")
        return state

    def _write_state(self, state: Mapping[str, Any]) -> None:
        atomic_write_json(self.state_path, state)

    def _require_case(self, case_id: str) -> None:
        _require(case_id == self.case_id, "case_id does not match the active corrective repair case")

    def _require_open(self, state: Mapping[str, Any]) -> None:
        _require(state.get("terminal_receipt") is None, "corrective repair attempt is terminal")

    def terminal_receipt(self) -> dict[str, Any] | None:
        receipt = self._state().get("terminal_receipt")
        return copy.deepcopy(receipt) if isinstance(receipt, dict) else None

    def repair_status(self, case_id: str) -> dict[str, Any]:
        self._require_case(case_id)
        state = self._state()
        remaining = {
            "public_evaluations": MAX_PUBLIC_EVALUATIONS - int(state["used"]["public_evaluations"]),
            "simulator_calls": MAX_SIMULATOR_CALLS - int(state["used"]["simulator_calls"]),
            "probes": MAX_PROBES - int(state["used"]["probes"]),
            "terminal_submissions": 1 - int(state["used"]["terminal_submissions"]),
        }
        return {
            "case_id": case_id,
            "case_sha256": self.case["case_sha256"],
            "proof_class": self.case["proof_class"],
            "evidence": copy.deepcopy(self.case["evidence_manifest"]),
            "probe_menu": copy.deepcopy(self.case["probe_menu"]),
            "remaining_budgets": remaining,
            "hypothesis_submitted": state["hypothesis"] is not None,
            "terminal": state["terminal_receipt"] is not None,
            "claim_boundary": CLAIM_BOUNDARY,
            "authority": copy.deepcopy(self.case["authority"]),
        }

    def read_repair_evidence(self, case_id: str, artifact_id: str, start: int = 0, limit: int = 100) -> dict[str, Any]:
        self._require_case(case_id)
        _require(type(start) is int and start >= 0 and type(limit) is int and 1 <= limit <= 200, "evidence slice is outside bounds")
        row = next((item for item in self.case["evidence_manifest"] if item["artifact_id"] == artifact_id), None)
        _require(row is not None, "artifact_id is not in the public evidence manifest")
        path = (self.packet_root / row["path"]).resolve()
        _require(self.packet_root in path.parents, "evidence path escaped the packet")
        artifact = load_json_object(path, label="corrective repair evidence")
        rows = artifact.get("rows")
        if isinstance(rows, list):
            artifact = {**artifact, "rows": rows[start : start + limit], "slice": {"start": start, "limit": limit, "total": len(rows)}}
        return artifact

    def submit_repair_hypothesis(self, case_id: str, hypothesis: Mapping[str, Any]) -> dict[str, Any]:
        self._require_case(case_id)
        state = self._state()
        self._require_open(state)
        evidence_ids = {row["artifact_id"] for row in self.case["evidence_manifest"]}
        normalized = _validate_hypothesis(hypothesis, evidence_ids)
        state["hypothesis"] = normalized
        state["events"].append({"tool": "submit_repair_hypothesis", "sha256": canonical_digest(normalized)})
        self._write_state(state)
        return {"accepted": True, "hypothesis_sha256": canonical_digest(normalized)}

    def request_repair_probe(self, case_id: str, probe_id: str) -> dict[str, Any]:
        self._require_case(case_id)
        state = self._state()
        self._require_open(state)
        declared = {row["probe_id"] for row in self.case["probe_menu"]}
        _require(probe_id in declared, "repair probe is undeclared or forbidden")
        _require(int(state["used"]["probes"]) < MAX_PROBES, "repair probe budget exhausted")
        state["used"]["probes"] += 1
        if probe_id == "repeat_pose_estimate":
            target = np.asarray(_SEALED_TARGETS[self.case_id], dtype=np.float64)
            noise = np.asarray((0.00025, -0.00025, 0.00025), dtype=np.float64)
            payload: dict[str, Any] = {
                "probe_id": probe_id,
                "desired_pregrasp_translation_delta_m": [float(value) for value in target + noise],
                "measurement_sigma_m": 0.0008,
            }
        else:
            payload = {"probe_id": probe_id, "control_tracking_consistent": True, "maximum_error_rad": 0.0011}
        payload["receipt_sha256"] = canonical_digest(payload)
        state["events"].append({"tool": "request_repair_probe", "receipt_sha256": payload["receipt_sha256"]})
        self._write_state(state)
        return payload

    def run_public_repair_evaluation(self, case_id: str, proposal: Mapping[str, Any]) -> dict[str, Any]:
        self._require_case(case_id)
        state = self._state()
        self._require_open(state)
        _require(int(state["used"]["public_evaluations"]) < MAX_PUBLIC_EVALUATIONS, "public evaluation budget exhausted")
        _require(int(state["used"]["simulator_calls"]) + SIMULATOR_CALLS_PER_EVALUATION <= MAX_SIMULATOR_CALLS, "simulator-call budget exhausted")
        delta = _proposal_delta(proposal, self.failure)
        state["used"]["public_evaluations"] += 1
        state["used"]["simulator_calls"] += SIMULATOR_CALLS_PER_EVALUATION
        metrics = _evaluate_delta(np.asarray(_SEALED_TARGETS[self.case_id]), delta, _perturbations(self.case_id, "development", 16))
        receipt = {
            "case_id": self.case_id,
            "split": "development",
            "proposal_sha256": canonical_digest(proposal),
            "simulator_calls": SIMULATOR_CALLS_PER_EVALUATION,
            "metrics": metrics,
            "training_admission": False,
            "promotion_authority": False,
        }
        receipt["receipt_sha256"] = canonical_digest(receipt)
        state["public_receipts"].append(receipt)
        state["events"].append({"tool": "run_public_repair_evaluation", "receipt_sha256": receipt["receipt_sha256"]})
        self._write_state(state)
        return copy.deepcopy(receipt)

    def submit_repair(self, case_id: str, proposal: Mapping[str, Any], claim_boundary: str) -> dict[str, Any]:
        self._require_case(case_id)
        state = self._state()
        self._require_open(state)
        _require(state["hypothesis"] is not None, "a repair hypothesis is required before terminal submission")
        _require(bool(state["public_receipts"]), "a public repair evaluation is required before terminal submission")
        _require(claim_boundary == CLAIM_BOUNDARY, f"claim_boundary must be {CLAIM_BOUNDARY}")
        delta = _proposal_delta(proposal, self.failure)
        state["used"]["terminal_submissions"] += 1
        target = np.asarray(_SEALED_TARGETS[self.case_id], dtype=np.float64)
        metrics = _evaluate_delta(target, delta, _perturbations(self.case_id, "sealed", SEALED_SAMPLE_COUNT))
        baseline = _evaluate_delta(target, np.zeros(3), _perturbations(self.case_id, "sealed", SEALED_SAMPLE_COUNT))
        gain = (baseline["mean_residual_m"] - metrics["mean_residual_m"]) / max(baseline["mean_residual_m"], 1e-12)
        hypothesis = state["hypothesis"]
        predicted = np.asarray(hypothesis["predicted_translation_delta_m"], dtype=np.float64)
        evidence_score = 1.0 if float(np.linalg.norm(predicted - delta)) <= 0.002 and "pose_residuals" in hypothesis["evidence_ids"] else 0.0
        correction_score = max(0.0, 1.0 - metrics["mean_residual_m"] / SAFETY_TOTAL_DELTA_M)
        cost = float(np.linalg.norm(delta)) / 0.010
        cost_score = max(0.0, 1.0 - 0.15 * cost)
        components = {
            "sealed_robustness": metrics["robustness_rate"],
            "correction_accuracy": correction_score,
            "gain_over_unchanged": max(0.0, min(1.0, gain)),
            "intervention_efficiency": cost_score,
            "evidence_discipline": evidence_score,
            "safety_compliance": 1.0,
        }
        aggregate = sum(SCORE_WEIGHTS[name] * components[name] for name in SCORE_WEIGHTS)
        attempt = {
            "case_id": self.case_id,
            "case_sha256": self.case["case_sha256"],
            "proposal_sha256": canonical_digest(proposal),
            "hypothesis_sha256": canonical_digest(hypothesis),
            "claim_boundary": claim_boundary,
            "budgets_used": copy.deepcopy(state["used"]),
        }
        attempt["attempt_sha256"] = canonical_digest(attempt)
        receipt = {
            "schema_version": RECEIPT_SCHEMA,
            "case_id": self.case_id,
            "proof_class": "synthetic_benchmark",
            "attempt_sha256": attempt["attempt_sha256"],
            "proposal_sha256": attempt["proposal_sha256"],
            "metrics": {**metrics, "unchanged_mean_residual_m": baseline["mean_residual_m"], "gain_over_unchanged": gain},
            "components": components,
            "aggregate_score": aggregate,
            "authority": {
                "training_admitted": False,
                "promoted": False,
                "physical_transfer_proof": False,
                "provider_model_quality_proof": False,
            },
        }
        receipt["receipt_sha256"] = canonical_digest(receipt)
        atomic_write_json(self.state_root / "attempt.json", attempt)
        atomic_write_json(self.state_root / "score_receipt.json", receipt)
        state["terminal_receipt"] = receipt
        state["events"].append({"tool": "submit_repair", "receipt_sha256": receipt["receipt_sha256"]})
        self._write_state(state)
        return copy.deepcopy(receipt)


def _mean_observation(case_id: str) -> np.ndarray:
    rows = _observations(case_id)["rows"]
    return np.mean(np.asarray([row["desired_pregrasp_translation_delta_m"] for row in rows], dtype=np.float64), axis=0)


def control_delta(case_id: str, control: str, *, seed: int = 20260720) -> np.ndarray:
    """Return a deterministic, bounded control action using its declared information."""

    _require(case_id in _SEALED_TARGETS, "unknown corrective repair case")
    if control == "unchanged":
        return np.zeros(3, dtype=np.float64)
    if control == "random_nudge":
        case_seed = int(canonical_digest({"seed": seed, "case_id": case_id})[:8], 16)
        rng = np.random.default_rng(case_seed)
        direction = rng.normal(size=3)
        return direction / np.linalg.norm(direction) * 0.006
    if control == "bounded_search":
        # This is a deterministic public-evidence heuristic. The runner still
        # evaluates all eight neighboring grid points and chooses on dev score.
        estimate = _mean_observation(case_id)
        return np.round(estimate / 0.002) * 0.002
    if control == "oracle":
        return np.asarray(_SEALED_TARGETS[case_id], dtype=np.float64)
    raise CorrectiveBenchmarkError(f"unsupported corrective repair control: {control}")


def run_control(control: str, root: Path, *, seed: int = 20260720) -> dict[str, Any]:
    """Run one deterministic control across all cases through the public API."""

    receipts: list[dict[str, Any]] = []
    for case_id in case_ids():
        packet_root = root / control / "packets" / case_id
        state_root = root / control / "state" / case_id
        materialize_public_case(case_id, packet_root, "control")
        session = CorrectiveRepairSession(packet_root, state_root, reset=True)
        delta = control_delta(case_id, control, seed=seed)
        hypothesis = {
            "mechanism": "pregrasp_centering_offset",
            "evidence_ids": ["pose_residuals", "control_summary"],
            "predicted_translation_delta_m": [float(value) for value in delta],
            "confidence": 1.0 if control == "oracle" else 0.7,
        }
        session.submit_repair_hypothesis(case_id, hypothesis)
        if control == "bounded_search":
            center = delta.copy()
            candidates = [
                center,
                center + np.asarray((0.002, 0.0, 0.0)),
                center - np.asarray((0.002, 0.0, 0.0)),
                center + np.asarray((0.0, 0.002, 0.0)),
                center - np.asarray((0.0, 0.002, 0.0)),
                center + np.asarray((0.0, 0.0, 0.002)),
                center - np.asarray((0.0, 0.0, 0.002)),
                center + np.asarray((0.001, 0.001, 0.001)),
            ]
            evaluated: list[tuple[float, np.ndarray, dict[str, Any]]] = []
            for index, candidate in enumerate(candidates):
                if float(np.linalg.norm(candidate)) > 0.010:
                    candidate = candidate / np.linalg.norm(candidate) * 0.0099
                proposal = build_proposal(case_id, candidate, harness=f"control-{control}", proposal_id=f"{control}-{index}")
                public = session.run_public_repair_evaluation(case_id, proposal)
                evaluated.append((public["metrics"]["mean_residual_m"], candidate, proposal))
            _, delta, proposal = min(evaluated, key=lambda row: (row[0], tuple(row[1])))
            hypothesis["predicted_translation_delta_m"] = [float(value) for value in delta]
            session.submit_repair_hypothesis(case_id, hypothesis)
        else:
            proposal = build_proposal(case_id, delta, harness=f"control-{control}", proposal_id=control)
            session.run_public_repair_evaluation(case_id, proposal)
        receipts.append(session.submit_repair(case_id, proposal, CLAIM_BOUNDARY))
    summary = {
        "schema_version": SUMMARY_SCHEMA,
        "control": control,
        "seed": seed,
        "case_count": len(receipts),
        "mean_aggregate_score": float(np.mean([row["aggregate_score"] for row in receipts])),
        "mean_sealed_robustness": float(np.mean([row["metrics"]["robustness_rate"] for row in receipts])),
        "mean_gain_over_unchanged": float(np.mean([row["metrics"]["gain_over_unchanged"] for row in receipts])),
        "receipts": receipts,
        "authority": {"promotion_authority": False, "physical_transfer_proof": False},
    }
    summary["summary_sha256"] = canonical_digest(summary)
    return summary


def run_all_controls(root: Path, *, seed: int = 20260720) -> dict[str, Any]:
    controls = [run_control(name, root, seed=seed) for name in ("unchanged", "random_nudge", "bounded_search", "oracle")]
    result = {
        "schema_version": "sim2claw.corrective_repair_control_comparison.v1",
        "seed": seed,
        "controls": controls,
        "proof_class": "synthetic_benchmark",
        "provider_model_calls": 0,
        "physical_authority": False,
        "promotion_authority": False,
    }
    result["comparison_sha256"] = canonical_digest(result)
    return result


def packet_contains_forbidden_bytes(packet_root: Path) -> list[str]:
    forbidden = (
        "_SEALED_TARGETS",
        "sealed_target",
        "hidden_perturbations",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "/var/run/docker.sock",
        str(Path.home()),
        "serial_port",
        "robot_gateway",
    )
    violations: list[str] = []
    for path in packet_root.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token and token in text:
                violations.append(f"{path.relative_to(packet_root)}:{token}")
    return violations
