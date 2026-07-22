"""Governed Inspect campaign contracts for the seeded SAIL benchmark.

The agent-facing session intentionally mirrors GapBench's host-tool pattern:
public packets and bounded state live outside the model, while the sealed row
is owned exclusively by the deterministic evaluator.  Provider execution is
optional; an unavailable or unequal provider route is preserved as a scored
attempt instead of being retried or silently dropped.
"""

from __future__ import annotations

import copy
import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ..learning_factory_artifacts import atomic_write_json, canonical_digest, load_json_object, sha256_file
from .benchmark import build_benchmark
from .contracts import REPO_ROOT, SailContractError, assert_provider_identity_stable

CONFIG_SCHEMA = "sim2claw.sail_inspect_campaign.v1"
PACKET_SCHEMA = "sim2claw.sail_agent_packet.v1"
ATTEMPT_SCHEMA = "sim2claw.sail_agent_attempt.v1"
SUMMARY_SCHEMA = "sim2claw.sail_inspect_campaign_summary.v1"
RECEIPT_SCHEMA = "sim2claw.sail_inspect_campaign_receipt.v1"
CLAIM_BOUNDARY = "synthetic_structural_benchmark_only"

SAIL_TOOL_NAMES = (
    "case_status",
    "read_evidence",
    "inspect_residuals",
    "inspect_belief_graph",
    "submit_hypotheses",
    "request_probe",
    "run_public_evaluation",
    "submit_candidate",
)

FORBIDDEN_PUBLIC_FIELDS = {
    "case_type",
    "coefficient",
    "family",
    "hidden_mechanisms",
    "oracle_influence_set",
    "sealed_row",
}


class AgentCampaignError(SailContractError):
    """A campaign condition, packet, attempt, or authority boundary changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AgentCampaignError(message)


def _repo_path(repo_root: Path, value: str, label: str) -> Path:
    root = repo_root.resolve()
    path = (root / value).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise AgentCampaignError(f"{label} escapes the repository") from error
    return path


def _command_identity(command: str) -> dict[str, Any]:
    path_text = shutil.which(command)
    if not path_text:
        return {"binary": command, "available": False, "path": None, "sha256": None, "version": None}
    path = Path(path_text).resolve()
    completed = subprocess.run(
        [str(path), "--version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    version = (completed.stdout or completed.stderr).strip()
    return {
        "binary": command,
        "available": completed.returncode == 0,
        "path": str(path),
        "sha256": sha256_file(path),
        "version": version,
    }


def load_campaign_config(path: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    value = load_json_object(resolved, label="SAIL Inspect campaign")
    _require(value.get("schema_version") == CONFIG_SCHEMA, "unsupported SAIL Inspect campaign schema")
    authority = value.get("authority")
    _require(isinstance(authority, dict) and authority and not any(authority.values()), "campaign authority widened")
    _require(value.get("case_order") and len(value["development_cases"]) == 3, "exactly three development cases are required")
    _require(set(value["development_cases"]).issubset(value["case_order"]), "development case is not in the frozen order")
    budgets = value.get("budgets")
    _require(
        budgets == {
            "probes_per_case": 1,
            "public_evaluations_per_case": 1,
            "terminal_submissions_per_case": 1,
            "provider_retries": 0,
            "provider_cost_ceiling_usd": 0.0,
            "message_limit": 80,
            "token_limit": 120000,
            "turn_limit": 40,
            "time_limit_seconds": 1800,
            "working_limit_seconds": 1500,
        },
        "campaign budgets changed",
    )
    conditions = value.get("conditions")
    _require(isinstance(conditions, list) and len(conditions) == 3, "three frozen conditions are required")
    ids = [row.get("condition_id") for row in conditions]
    _require(ids == ["deterministic-sail", "codex-cli-runtime", "claude-code-runtime"], "condition order changed")
    semantic = {row.get("semantic_surface_sha256") for row in conditions}
    _require(len(semantic) == 1 and None not in semantic, "agent conditions do not share one semantic surface")
    for condition in conditions:
        _require(condition.get("retry_count") == 0, "selective retry became enabled")
        _require(condition.get("case_order") == value["case_order"], "condition case order differs")
        _require(condition.get("tool_names") == list(SAIL_TOOL_NAMES), "condition tool surface differs")
    for name, binding in value.get("source_bindings", {}).items():
        source = _repo_path(repo_root, str(binding.get("path", "")), name)
        _require(source.is_file() and sha256_file(source) == binding.get("sha256"), f"campaign source changed: {name}")
    return value


def _candidate_families(config: Mapping[str, Any], *, repo_root: Path = REPO_ROOT) -> list[str]:
    benchmark = load_json_object(_repo_path(repo_root, config["source_bindings"]["benchmark_config"]["path"], "benchmark config"), label="seeded benchmark config")
    return sorted({str(row["family"]) for row in benchmark["fault_cases"]})


def build_packets(config: Mapping[str, Any], *, repo_root: Path = REPO_ROOT) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    benchmark = load_json_object(
        _repo_path(repo_root, config["source_bindings"]["benchmark_config"]["path"], "benchmark config"),
        label="seeded benchmark config",
    )
    registry = load_json_object(
        _repo_path(repo_root, config["source_bindings"]["golden_registry"]["path"], "golden registry"),
        label="golden registry",
    )
    compiled = build_benchmark(benchmark, registry, repo_root=repo_root)
    public_source = compiled["public"]
    sealed_source = compiled["sealed"]
    public_rows = public_source.get("rows")
    sealed_rows = sealed_source.get("rows")
    cases = benchmark.get("fault_cases")
    _require(isinstance(public_rows, list) and isinstance(sealed_rows, list) and isinstance(cases, list), "benchmark rows are missing")
    _require(len(public_rows) == len(sealed_rows) == len(cases) == len(config["case_order"]), "benchmark inventories differ")
    families = _candidate_families(config, repo_root=repo_root)
    packets: dict[str, dict[str, Any]] = {}
    sealed: dict[str, dict[str, Any]] = {}
    for public, private, case in zip(public_rows, sealed_rows, cases, strict=True):
        case_id = str(case["case_id"])
        _require(case_id == private.get("case_id"), "sealed case order changed")
        evidence = {
            "schema_version": "sim2claw.sail_agent_evidence.v1",
            "row_id": public["row_id"],
            "feature": copy.deepcopy(public["feature"]),
            "observation": copy.deepcopy(public["observation"]),
            "action_sha256": public["action_sha256"],
        }
        baseline_rmse = float(np.sqrt(np.mean(np.square(np.asarray(public["observation"], dtype=np.float64)))))
        packet = {
            "schema_version": PACKET_SCHEMA,
            "case_id": case_id,
            "proof_class": "synthetic_benchmark",
            "candidate_families": families,
            "parameter_envelope": copy.deepcopy(public["parameter_envelope"]),
            "allowed_probes": copy.deepcopy(public["allowed_probes"]),
            "budgets": {
                "probes": int(config["budgets"]["probes_per_case"]),
                "public_evaluations": int(config["budgets"]["public_evaluations_per_case"]),
                "terminal_submissions": int(config["budgets"]["terminal_submissions_per_case"]),
            },
            "evidence": evidence,
            "residual_summary": {"baseline_rmse": baseline_rmse, "phase_aware": True, "action_sha256": public["action_sha256"]},
            "belief_graph": {
                "candidate_nodes": [f"mechanism:{name}" for name in families],
                "observation_node": f"observation:{public['row_id']}",
                "edge_state": "candidate_unresolved",
            },
            "sealed_access": False,
            "promotion_authority": False,
            "physical_authority": False,
        }
        public_text = json.dumps(packet, sort_keys=True)
        _require(not any(f'"{field}"' in public_text for field in FORBIDDEN_PUBLIC_FIELDS), "sealed field leaked into agent packet")
        packets[case_id] = {**packet, "packet_sha256": canonical_digest(packet)}
        sealed[case_id] = copy.deepcopy(private)
    _require(list(packets) == config["case_order"], "materialized packet order changed")
    return packets, sealed


def _parameter_to_coefficient(parameter: float, envelope: Sequence[float]) -> float:
    low, high = (float(value) for value in envelope)
    _require(low <= parameter <= high, "candidate parameter is out of bounds")
    return 0.2 + 1.5 * (parameter - low) / (high - low)


def _public_score(packet: Mapping[str, Any], parameter: float) -> dict[str, Any]:
    coefficient = _parameter_to_coefficient(parameter, packet["parameter_envelope"])
    feature = np.asarray(packet["evidence"]["feature"], dtype=np.float64)
    observation = np.asarray(packet["evidence"]["observation"], dtype=np.float64)
    rmse = float(np.sqrt(np.mean(np.square(observation - coefficient * feature))))
    return {"candidate_rmse": rmse, "coefficient": coefficient, "promotion_authority": False}


class StructuralCampaignSession:
    """Stateful bounded tool surface for one structural case."""

    def __init__(self, packet: Mapping[str, Any], sealed_row: Mapping[str, Any]):
        self.packet = copy.deepcopy(dict(packet))
        self._sealed = copy.deepcopy(dict(sealed_row))
        _require(self.packet["case_id"] == self._sealed["case_id"], "public/sealed case mismatch")
        self.state: dict[str, Any] = {
            "used": {"probes": 0, "public_evaluations": 0, "terminal_submissions": 0},
            "hypotheses": None,
            "terminal": None,
            "events": [],
        }

    def _active(self) -> None:
        _require(self.state["terminal"] is None, "attempt is terminal")

    def _charge(self, name: str) -> None:
        _require(self.state["used"][name] < self.packet["budgets"][name], f"{name} budget exhausted")
        self.state["used"][name] += 1

    def status(self) -> dict[str, Any]:
        result = {
            "case_id": self.packet["case_id"],
            "packet_sha256": self.packet["packet_sha256"],
            "proof_class": self.packet["proof_class"],
            "candidate_families": copy.deepcopy(self.packet["candidate_families"]),
            "parameter_envelope": copy.deepcopy(self.packet["parameter_envelope"]),
            "allowed_probes": copy.deepcopy(self.packet["allowed_probes"]),
            "remaining_budgets": {name: self.packet["budgets"][name] - used for name, used in self.state["used"].items()},
            "terminal": self.state["terminal"] is not None,
            "sealed_access": False,
            "promotion_authority": False,
        }
        self.state["events"].append({"tool": "case_status", "sha256": canonical_digest(result)})
        return result

    def read_evidence(self, start: int = 0, limit: int = 100) -> dict[str, Any]:
        _require(start >= 0 and 0 < limit <= 200, "evidence slice is outside bounds")
        evidence = copy.deepcopy(self.packet["evidence"])
        for name in ("feature", "observation"):
            values = evidence[name]
            evidence[name] = values[start : start + limit]
        evidence["slice"] = {"start": start, "limit": limit, "total": len(self.packet["evidence"]["feature"])}
        self.state["events"].append({"tool": "read_evidence", "sha256": canonical_digest(evidence)})
        return evidence

    def inspect_residuals(self) -> dict[str, Any]:
        result = copy.deepcopy(self.packet["residual_summary"])
        self.state["events"].append({"tool": "inspect_residuals", "sha256": canonical_digest(result)})
        return result

    def inspect_belief_graph(self) -> dict[str, Any]:
        result = copy.deepcopy(self.packet["belief_graph"])
        self.state["events"].append({"tool": "inspect_belief_graph", "sha256": canonical_digest(result)})
        return result

    def submit_hypotheses(self, hypotheses: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        self._active()
        normalized = []
        for rank, row in enumerate(hypotheses, start=1):
            family = str(row.get("family", ""))
            uncertainty = float(row.get("uncertainty", math.nan))
            _require(family in self.packet["candidate_families"], "hypothesis family is not allowed")
            _require(row.get("rank") == rank and math.isfinite(uncertainty) and 0.0 <= uncertainty <= 1.0, "hypothesis rank or uncertainty is invalid")
            normalized.append({"rank": rank, "family": family, "uncertainty": uncertainty, "evidence_ids": list(row.get("evidence_ids", []))})
        _require(normalized, "at least one structured hypothesis is required")
        self.state["hypotheses"] = normalized
        self.state["events"].append({"tool": "submit_hypotheses", "sha256": canonical_digest(normalized)})
        return {"accepted": True, "count": len(normalized), "hypotheses_sha256": canonical_digest(normalized)}

    def request_probe(self, probe_id: str) -> dict[str, Any]:
        self._active()
        _require(probe_id in self.packet["allowed_probes"], "probe is undeclared or forbidden")
        self._charge("probes")
        feature = np.asarray(self.packet["evidence"]["feature"], dtype=np.float64)
        observation = np.asarray(self.packet["evidence"]["observation"], dtype=np.float64)
        result = {"probe_id": probe_id, "public_slope": float(np.dot(feature, observation) / np.dot(feature, feature)), "physical_action": False}
        self.state["events"].append({"tool": "request_probe", "sha256": canonical_digest(result)})
        return result

    def public_evaluate(self, parameter: float) -> dict[str, Any]:
        self._active()
        self._charge("public_evaluations")
        score = _public_score(self.packet, float(parameter))
        self.state["events"].append({"tool": "run_public_evaluation", "sha256": canonical_digest(score)})
        return score

    def submit_candidate(self, *, family: str, parameter: float, uncertainty: float, claim_boundary: str) -> dict[str, Any]:
        self._active()
        _require(self.state["hypotheses"] is not None, "structured hypotheses are required before sealed scoring")
        _require(family in self.packet["candidate_families"], "candidate family is not allowed")
        _require(math.isfinite(float(uncertainty)) and 0.0 <= float(uncertainty) <= 1.0, "candidate uncertainty is invalid")
        _require(claim_boundary == CLAIM_BOUNDARY, "claim boundary changed")
        self._charge("terminal_submissions")
        _parameter_to_coefficient(float(parameter), self.packet["parameter_envelope"])
        feature = np.asarray(self._sealed["feature"], dtype=np.float64)
        observation = np.asarray(self._sealed["observation"], dtype=np.float64)
        candidate_coefficient = _parameter_to_coefficient(float(parameter), self.packet["parameter_envelope"])
        candidate_rmse = float(np.sqrt(np.mean(np.square(observation - candidate_coefficient * feature))))
        baseline_rmse = float(np.sqrt(np.mean(np.square(observation))))
        family_correct = family == self._sealed["family"]
        confidence = 1.0 - float(uncertainty)
        calibration = 1.0 - abs(confidence - float(family_correct))
        score = 0.5 * float(family_correct) + 0.35 * max(0.0, 1.0 - candidate_rmse / max(baseline_rmse, 1e-12)) + 0.15 * calibration
        unsigned = {
            "schema_version": "sim2claw.sail_agent_score.v1",
            "case_id": self.packet["case_id"],
            "proof_class": "synthetic_benchmark",
            "aggregate_score": score,
            "scores": {"family_top1": float(family_correct), "sealed_residual_gain": max(0.0, 1.0 - candidate_rmse / max(baseline_rmse, 1e-12)), "prediction_calibration": calibration},
            "hidden_values_disclosed": False,
            "evaluator_owner": "deterministic_sail_evaluator",
            "promotion_authority": False,
            "physical_authority": False,
        }
        receipt = {**unsigned, "receipt_sha256": canonical_digest(unsigned)}
        self.state["terminal"] = receipt
        self.state["events"].append({"tool": "submit_candidate", "sha256": receipt["receipt_sha256"]})
        return copy.deepcopy(receipt)


def _family_from_probe(probe: str) -> str:
    mapping = {
        "command_frequency": "timing_delay",
        "reset_reference": "reset_reference",
        "small_amplitude_sweep": "deadband_hysteresis",
        "simulated_load": "load_compliance",
        "camera_motion": "camera_timing_extrinsics",
        "aperture": "gripper_contact_geometry",
        "sliding_friction": "contact_friction_compliance",
        "object_mass": "object_dynamics_support_height",
    }
    return mapping[probe]


def run_deterministic_attempt(packet: Mapping[str, Any], sealed: Mapping[str, Any]) -> dict[str, Any]:
    session = StructuralCampaignSession(packet, sealed)
    feature = np.asarray(packet["evidence"]["feature"], dtype=np.float64)
    observation = np.asarray(packet["evidence"]["observation"], dtype=np.float64)
    slope = float(np.dot(feature, observation) / np.dot(feature, feature))
    low, high = (float(value) for value in packet["parameter_envelope"])
    parameter = low + (slope - 0.2) * (high - low) / 1.5
    parameter = min(high, max(low, parameter))
    family = _family_from_probe(packet["allowed_probes"][0])
    session.status()
    session.read_evidence()
    session.inspect_residuals()
    session.inspect_belief_graph()
    session.submit_hypotheses([{"rank": 1, "family": family, "uncertainty": 0.1, "evidence_ids": [packet["evidence"]["row_id"]]}])
    session.request_probe(packet["allowed_probes"][0])
    session.public_evaluate(parameter)
    score = session.submit_candidate(family=family, parameter=parameter, uncertainty=0.1, claim_boundary=CLAIM_BOUNDARY)
    unsigned = {
        "schema_version": ATTEMPT_SCHEMA,
        "condition_id": "deterministic-sail",
        "case_id": packet["case_id"],
        "status": "completed",
        "runtime_identity": {"provider": "local", "model": "none", "model_revision": "deterministic", "harness_sha256": canonical_digest(SAIL_TOOL_NAMES)},
        "usage": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "duration_seconds": 0.0, "duration_basis": "deterministic_logical_runtime"},
        "retry_count": 0,
        "tool_events": copy.deepcopy(session.state["events"]),
        "terminal_score_receipt": score,
        "scored_failure": False,
        "promotion_authority": False,
        "physical_authority": False,
    }
    return {**unsigned, "attempt_sha256": canonical_digest(unsigned)}


def _blocked_provider_attempt(condition: Mapping[str, Any], case_id: str, runtime: Mapping[str, Any]) -> dict[str, Any]:
    unsigned = {
        "schema_version": ATTEMPT_SCHEMA,
        "condition_id": condition["condition_id"],
        "case_id": case_id,
        "status": "blocked_before_model_call",
        "failure_class": "inspect_subscription_transport_unavailable",
        "failure_detail": "Inspect SWE proxies provider traffic and cannot reuse the authenticated native CLI subscription; paid API spend ceiling is zero.",
        "runtime_identity": {
            "provider": condition["provider"],
            "model": None,
            "model_revision": runtime.get("version"),
            "harness_sha256": condition["harness_sha256"],
            "binary_sha256": runtime.get("sha256"),
            "identity_complete": False,
        },
        "usage": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "duration_seconds": 0.0, "duration_basis": "blocked_before_model_call"},
        "retry_count": 0,
        "terminal_score_receipt": {"aggregate_score": 0.0, "reason": "blocked attempt remains in denominator"},
        "scored_failure": True,
        "promotion_authority": False,
        "physical_authority": False,
    }
    return {**unsigned, "attempt_sha256": canonical_digest(unsigned)}


def compile_campaign(config_path: Path, *, output_root: Path, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    resolved = config_path if config_path.is_absolute() else repo_root / config_path
    config = load_campaign_config(resolved, repo_root=repo_root)
    packets, sealed = build_packets(config, repo_root=repo_root)
    output_root.mkdir(parents=True, exist_ok=True)
    packet_root = output_root / "public_packets"
    packet_root.mkdir(parents=True, exist_ok=True)
    for case_id, packet in packets.items():
        atomic_write_json(packet_root / f"{case_id}.json", packet)

    attempts = [run_deterministic_attempt(packets[case_id], sealed[case_id]) for case_id in config["development_cases"]]
    runtimes = {"codex_cli": _command_identity("codex"), "claude_code": _command_identity("claude")}
    for condition in config["conditions"][1:]:
        runtime = runtimes[condition["harness"]]
        attempts.extend(_blocked_provider_attempt(condition, case_id, runtime) for case_id in config["development_cases"])
    for condition_id in {row["condition_id"] for row in attempts}:
        rows = [row["runtime_identity"] for row in attempts if row["condition_id"] == condition_id]
        assert_provider_identity_stable(rows)

    completed = [row for row in attempts if row["status"] == "completed"]
    blocked = [row for row in attempts if row["status"] != "completed"]
    summary_unsigned = {
        "schema_version": SUMMARY_SCHEMA,
        "campaign_id": config["campaign_id"],
        "proof_class": "synthetic_benchmark",
        "development_scenarios_completed_before_provider_attempts": True,
        "development_case_ids": list(config["development_cases"]),
        "case_order": list(config["case_order"]),
        "conditions": copy.deepcopy(config["conditions"]),
        "runtime_inventory": runtimes,
        "attempts": attempts,
        "counts": {"attempts": len(attempts), "completed": len(completed), "scored_failures": len(blocked), "provider_calls": 0},
        "usage_totals": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
        "condition_evidence_and_budgets_equivalent": True,
        "provider_results_pooled": False,
        "agent_prose_scoring_authority": False,
        "sealed_access_by_agent": False,
        "resources_remaining": {"provider_sessions": 0, "docker_containers": 0, "devices": 0, "brev_instances_created": 0},
        "verdict": "deterministic_development_complete_provider_comparison_blocked",
        "promotion_authority": False,
        "physical_authority": False,
    }
    summary = {**summary_unsigned, "summary_digest": canonical_digest(summary_unsigned)}
    atomic_write_json(output_root / "campaign_summary.json", summary)
    unsigned_receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "campaign_id": config["campaign_id"],
        "config": {"path": resolved.resolve().relative_to(repo_root.resolve()).as_posix(), "sha256": sha256_file(resolved)},
        "outputs": {
            "campaign_summary": {"path": "campaign_summary.json", "sha256": sha256_file(output_root / "campaign_summary.json")},
            "public_packet_manifest": {name: sha256_file(path) for name, path in sorted((p.stem, p) for p in packet_root.glob("*.json"))},
        },
        "golden_cases": {"GOLD-13": True, "GOLD-14": True, "GOLD-24": True},
        "counts": summary["counts"],
        "usage_totals": summary["usage_totals"],
        "authority": copy.deepcopy(config["authority"]),
    }
    receipt = {**unsigned_receipt, "receipt_digest": canonical_digest(unsigned_receipt)}
    atomic_write_json(output_root / "receipt.json", receipt)
    return {
        "schema_version": "sim2claw.sail_inspect_campaign_compile_result.v1",
        "status": "compiled",
        "verdict": summary["verdict"],
        "counts": summary["counts"],
        "receipt_sha256": sha256_file(output_root / "receipt.json"),
        "receipt_digest": receipt["receipt_digest"],
        "output_root": str(output_root),
        "provider_calls": 0,
        "physical_authority": False,
    }


__all__ = [
    "AgentCampaignError",
    "CLAIM_BOUNDARY",
    "SAIL_TOOL_NAMES",
    "StructuralCampaignSession",
    "build_packets",
    "compile_campaign",
    "load_campaign_config",
    "run_deterministic_attempt",
]
